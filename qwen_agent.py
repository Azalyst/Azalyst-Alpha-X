"""
Qwen AI Agent — runs every 4 hours via main.py
Analyzes recent trade performance + market movers,
then autonomously applies parameter tweaks to main.py.
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
import requests

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

TRADES_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trades.json")
ANALYSIS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qwen_analysis.json")
MAIN_PY_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")

QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
FAPI_BASE    = os.environ.get("BINANCE_PROXY_URL", "https://fapi.binance.com")

_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json", "User-Agent": "DiscordBot/1.0"})

# ─────────────────────────────────────────────────────────────────
#  Market data helpers
# ─────────────────────────────────────────────────────────────────
def get_top_movers():
    """Return top 5 gainers and top 5 losers from Binance 24h ticker."""
    try:
        resp = _SESSION.get(f"{FAPI_BASE}/fapi/v1/ticker/24hr", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        sorted_data = sorted(data, key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)
        gainers = [{"symbol": d["symbol"], "change": d["priceChangePercent"] + "%"} for d in sorted_data[:5]]
        losers  = [{"symbol": d["symbol"], "change": d["priceChangePercent"] + "%"} for d in sorted_data[-5:]]
        return gainers, losers
    except Exception as e:
        print(f"  [Qwen] Error fetching top movers: {e}")
        return [], []


# ─────────────────────────────────────────────────────────────────
#  Safe regex parameter patcher for main.py
# ─────────────────────────────────────────────────────────────────
# Only these keys are allowed to be auto-patched for safety.
_PATCHABLE_PARAMS = {
    "TOUCH_TOL",
    "MIN_BREAKOUT_PCT",
    "MIN_BANDWIDTH_PCT",
    "RSI_LONG_1H",
    "RSI_LONG_4H",
    "RSI_SHORT_1H",
    "RSI_SHORT_4H",
    "RSI_VELOCITY_MIN",
    "VOLUME_SURGE_MULT",
    "BREAKOUT_LOOKBACK",
    "ENTRY_WINDOW",
}

def _apply_parameters(updates: dict) -> dict:
    """
    Patch numeric constants in main.py.
    Returns dict of {param: (old_val, new_val)} for actually changed params.
    """
    if not updates:
        return {}

    try:
        with open(MAIN_PY_FILE, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        print(f"  [Qwen] Cannot read main.py: {e}")
        return {}

    changed = {}
    for key, new_val in updates.items():
        if key not in _PATCHABLE_PARAMS:
            print(f"  [Qwen] Skipping non-patchable param: {key}")
            continue

        # Match: KEY   = <number>   (handles spaces, float, int)
        pattern = rf"({re.escape(key)}\s*=\s*)([0-9]+(?:\.[0-9]+)?)"
        match   = re.search(pattern, code)
        if not match:
            print(f"  [Qwen] Pattern not found for: {key}")
            continue

        old_val_str = match.group(2)
        old_val     = float(old_val_str)
        new_val_str = str(new_val)

        code = re.sub(pattern, rf"\g<1>{new_val_str}", code, count=1)
        changed[key] = (old_val, new_val)
        print(f"  [Qwen] Patched {key}: {old_val} → {new_val}")

    if changed:
        try:
            tmp = MAIN_PY_FILE + ".qwen_tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(code)
            os.replace(tmp, MAIN_PY_FILE)
            print(f"  [Qwen] main.py updated with {len(changed)} change(s).")
        except Exception as e:
            print(f"  [Qwen] Failed to write main.py: {e}")
            return {}

    return changed


# ─────────────────────────────────────────────────────────────────
#  Main analysis function — called by main.py every 4h
# ─────────────────────────────────────────────────────────────────
def analyze_and_fix() -> dict | None:
    """
    Analyze recent trades + market movers using Qwen AI.
    Applies safe parameter updates to main.py if recommended.
    Returns the analysis dict (so main.py can send it to Discord).
    """
    if not os.path.exists(TRADES_FILE):
        print("  [Qwen] No trades file found.")
        return None

    with open(TRADES_FILE, "r") as f:
        trades_data = json.load(f)

    closed_trades = trades_data.get("closed_trades", [])
    now = datetime.now(timezone.utc)

    # Only look at trades closed in the last 4 hours
    recent_trades = []
    for t in closed_trades:
        if "close_time" in t:
            try:
                ct = datetime.fromisoformat(t["close_time"].replace("Z", "+00:00"))
                if (now - ct) <= timedelta(hours=4):
                    recent_trades.append(t)
            except Exception:
                pass

    recent_losses = [t for t in recent_trades if t.get("rpnl", 0) <= 0]
    recent_wins   = [t for t in recent_trades if t.get("rpnl", 0) >  0]

    top_gainers, top_losers = get_top_movers()

    total_closed = len(closed_trades)
    total_rpnl   = sum(t.get("rpnl", 0) for t in closed_trades)

    if not recent_trades and not top_gainers:
        print("  [Qwen] No recent trades and no market data — skipping analysis.")
        return None

    print(f"  [Qwen] Analyzing {len(recent_losses)} losses, {len(recent_wins)} wins "
          f"(last 4h)  |  Total trades: {total_closed}")

    prompt = f"""
You are an expert quantitative analyst reviewing a live crypto paper-trading bot.

STRATEGY:
- Bollinger Bands BB(200, 1σ) on 1-minute candles across 450+ Binance USDT perpetual futures.
- Entry: breakout above/below band → pullback to band → confirmation candle.
- Filters: RSI alignment on 1h and 4h, volume surge ≥1.5×, trend stage (EARLY/MID/LATE).
- Exit: band re-touch after extension, or Stop Loss, or Fibonacci TP.

RECENT PERFORMANCE (last 4 hours):
Wins:   {json.dumps(recent_wins,   indent=2)}
Losses: {json.dumps(recent_losses, indent=2)}

MARKET CONTEXT:
Top 24h Gainers on Binance: {json.dumps(top_gainers)}
Top 24h Losers  on Binance: {json.dumps(top_losers)}

Overall: {total_closed} total closed trades, total rPnL = {total_rpnl:.2f} USDT.

TASK:
1. Identify WHY the losses occurred (e.g., stop too tight, false breakout, wrong trend stage).
2. Identify why the bot may have MISSED big movers (RSI filter too strict, TOUCH_TOL too tight, etc.).
3. Recommend up to 3 small, safe parameter adjustments.

IMPORTANT CONSTRAINTS:
- Only suggest adjustments to these parameters: TOUCH_TOL, MIN_BREAKOUT_PCT, MIN_BANDWIDTH_PCT,
  RSI_LONG_1H, RSI_LONG_4H, RSI_SHORT_1H, RSI_SHORT_4H, RSI_VELOCITY_MIN, VOLUME_SURGE_MULT,
  BREAKOUT_LOOKBACK, ENTRY_WINDOW.
- Keep changes conservative: ±10-20% of current value at most.
- Do NOT suggest leverage, risk%, or balance changes.

Respond ONLY in raw JSON (no markdown, no code fences):
{{
    "summary": "One paragraph: what went wrong and what we missed.",
    "action": "One paragraph: what you recommend changing and why.",
    "parameter_updates": {{
        "PARAM_NAME": new_numeric_value
    }}
}}
"""

    analysis = None

    if not QWEN_API_KEY or OpenAI is None:
        print("  [Qwen] QWEN_API_KEY not set or openai library missing. Generating placeholder analysis.")
        analysis = {
            "summary": (
                f"Qwen API not configured. Observed {len(recent_losses)} losses and "
                f"{len(recent_wins)} wins in the last 4 hours. "
                f"Top gainer: {top_gainers[0]['symbol'] if top_gainers else 'N/A'} "
                f"({top_gainers[0]['change'] if top_gainers else 'N/A'})."
            ),
            "action": "Set QWEN_API_KEY environment variable on Railway to enable AI analysis.",
            "parameter_updates": {}
        }
    else:
        try:
            client = OpenAI(
                api_key=QWEN_API_KEY,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            response = client.chat.completions.create(
                model="qwen-max",
                messages=[
                    {"role": "system", "content": "You are an autonomous quant analyst AI. Always reply with valid raw JSON only."},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )
            content = response.choices[0].message.content.strip()
            # Strip accidental markdown fences
            content = re.sub(r"^```[a-z]*\n?", "", content)
            content = re.sub(r"\n?```$",        "", content)
            analysis = json.loads(content)
            print("  [Qwen] API response parsed successfully.")
        except json.JSONDecodeError as e:
            print(f"  [Qwen] JSON parse error: {e}. Raw: {content[:300]}")
            analysis = {
                "summary": f"Qwen returned non-JSON response: {content[:200]}",
                "action":  "Manual review required.",
                "parameter_updates": {}
            }
        except Exception as e:
            print(f"  [Qwen] API error: {e.__class__.__name__}: {e}")
            analysis = {
                "summary": f"Qwen API error: {e}",
                "action":  "Check QWEN_API_KEY and network.",
                "parameter_updates": {}
            }

    # Save analysis to disk
    try:
        with open(ANALYSIS_FILE, "w") as f:
            json.dump({**analysis, "timestamp": now.isoformat()}, f, indent=2)
        print(f"  [Qwen] Analysis saved → {ANALYSIS_FILE}")
    except Exception as e:
        print(f"  [Qwen] Could not save analysis file: {e}")

    # Apply parameter updates
    updates = analysis.get("parameter_updates", {})
    if updates:
        changed = _apply_parameters(updates)
        analysis["_applied_changes"] = {k: f"{v[0]} → {v[1]}" for k, v in changed.items()}
    else:
        print("  [Qwen] No parameter updates recommended.")
        analysis["_applied_changes"] = {}

    return analysis


# ─────────────────────────────────────────────────────────────────
#  Standalone entry point (for testing: python qwen_agent.py)
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    result = analyze_and_fix()
    if result:
        print("\n── Qwen Analysis ──")
        print(json.dumps(result, indent=2))
    else:
        print("No analysis produced.")
