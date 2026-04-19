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
from typing import Optional

import requests

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    OpenAI = None
    HAS_OPENAI = False

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
        if not isinstance(data, list):
            return [], []
        sorted_data = sorted(
            data,
            key=lambda x: float(x.get("priceChangePercent", 0)),
            reverse=True
        )
        gainers = [
            {"symbol": d["symbol"], "change": d["priceChangePercent"] + "%"}
            for d in sorted_data[:5]
        ]
        losers = [
            {"symbol": d["symbol"], "change": d["priceChangePercent"] + "%"}
            for d in sorted_data[-5:]
        ]
        return gainers, losers
    except Exception as e:
        print(f"  [Qwen] Error fetching top movers: {e}")
        return [], []


# ─────────────────────────────────────────────────────────────────
#  Safe regex parameter patcher for main.py
# ─────────────────────────────────────────────────────────────────
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

def _apply_parameters(updates):
    """
    Patch numeric constants in main.py.
    Returns dict of {param: "old → new"} for actually changed params.
    """
    if not updates or not isinstance(updates, dict):
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

        try:
            new_val_f = float(new_val)
        except (TypeError, ValueError):
            print(f"  [Qwen] Skipping {key}: non-numeric value '{new_val}'")
            continue

        pattern = rf"({re.escape(key)}\s*=\s*)([0-9]+(?:\.[0-9]+)?)"
        match   = re.search(pattern, code)
        if not match:
            print(f"  [Qwen] Pattern not found for: {key}")
            continue

        old_val_str = match.group(2)
        old_val     = float(old_val_str)

        # Format: keep int if whole number, else float
        if new_val_f == int(new_val_f) and "." not in str(new_val):
            new_val_str = str(int(new_val_f))
        else:
            new_val_str = str(new_val_f)

        code = re.sub(pattern, rf"\g<1>{new_val_str}", code, count=1)
        changed[key] = f"{old_val} -> {new_val_str}"
        print(f"  [Qwen] Patched {key}: {old_val} -> {new_val_str}")

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
def analyze_and_fix():
    # type: () -> Optional[dict]
    """
    Analyze recent trades + market movers using Qwen AI.
    Applies safe parameter updates to main.py if recommended.
    Returns the analysis dict (so main.py can send it to Discord).
    """
    if not os.path.exists(TRADES_FILE):
        print("  [Qwen] No trades file found.")
        return {
            "summary": "No trades file found. Scanner may be starting up.",
            "action":  "No changes needed.",
            "parameter_updates": {},
            "_applied_changes": {},
        }

    try:
        with open(TRADES_FILE, "r") as f:
            trades_data = json.load(f)
    except Exception as e:
        print(f"  [Qwen] Failed to read trades file: {e}")
        return {
            "summary": f"Could not read trades file: {e}",
            "action":  "Check that paper_trades.json is valid JSON.",
            "parameter_updates": {},
            "_applied_changes": {},
        }

    closed_trades = trades_data.get("closed_trades", [])
    now = datetime.now(timezone.utc)

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

    print(f"  [Qwen] Analyzing {len(recent_losses)} losses, {len(recent_wins)} wins "
          f"(last 4h)  |  Total trades: {total_closed}")

    # ── Placeholder if no API key ─────────────────────────────────
    if not QWEN_API_KEY or not HAS_OPENAI:
        reason = "QWEN_API_KEY not set" if not QWEN_API_KEY else "openai library not installed"
        gainer_str = (
            f"{top_gainers[0]['symbol']} ({top_gainers[0]['change']})"
            if top_gainers else "N/A"
        )
        analysis = {
            "summary": (
                f"AI analysis disabled ({reason}). "
                f"Observed {len(recent_losses)} loss(es) and {len(recent_wins)} win(s) "
                f"in the last 4 hours. Total closed trades: {total_closed}. "
                f"rPnL all-time: {total_rpnl:.2f} USDT. "
                f"Top gainer: {gainer_str}."
            ),
            "action": (
                "Set QWEN_API_KEY in Railway environment variables to enable AI analysis. "
                "Get your key from dashscope.aliyuncs.com."
            ),
            "parameter_updates": {},
            "_applied_changes": {},
        }
        _save_analysis(analysis, now)
        return analysis

    # ── Call Qwen API ─────────────────────────────────────────────
    prompt = f"""You are an expert quantitative analyst reviewing a live crypto paper-trading bot.

STRATEGY:
- Bollinger Bands BB(200, 1sigma) on 1-minute candles across 450+ Binance USDT perpetual futures.
- Entry: breakout above/below band then pullback to band then confirmation candle.
- Filters: RSI alignment on 1h and 4h, volume surge >= 1.3x, trend stage (EARLY/MID/LATE).
- Exit: band re-touch after extension, or Stop Loss, or Fibonacci TP.

RECENT PERFORMANCE (last 4 hours):
Wins:   {json.dumps(recent_wins,   indent=2)}
Losses: {json.dumps(recent_losses, indent=2)}

MARKET CONTEXT:
Top 24h Gainers on Binance: {json.dumps(top_gainers)}
Top 24h Losers  on Binance: {json.dumps(top_losers)}

Overall: {total_closed} total closed trades, total rPnL = {total_rpnl:.2f} USDT.

TASK:
1. Identify WHY the losses occurred.
2. Identify why the bot may have MISSED big movers.
3. Recommend up to 3 small, safe parameter adjustments.

IMPORTANT CONSTRAINTS:
- Only suggest adjustments to: TOUCH_TOL, MIN_BREAKOUT_PCT, MIN_BANDWIDTH_PCT,
  RSI_LONG_1H, RSI_LONG_4H, RSI_SHORT_1H, RSI_SHORT_4H, RSI_VELOCITY_MIN,
  VOLUME_SURGE_MULT, BREAKOUT_LOOKBACK, ENTRY_WINDOW.
- Keep changes conservative: plus or minus 10-20% of current value at most.
- Do NOT suggest leverage, risk percentage, or balance changes.

Respond ONLY in raw JSON with no markdown and no code fences:
{{"summary": "One paragraph explaining what went wrong and what we missed.", "action": "One paragraph on what to change and why.", "parameter_updates": {{"PARAM_NAME": new_numeric_value}}}}"""

    analysis = None
    content  = ""

    try:
        client = OpenAI(
            api_key=QWEN_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        response = client.chat.completions.create(
            model="qwen-max",
            messages=[
                {
                    "role": "system",
                    "content": "You are an autonomous quant analyst AI. Always reply with valid raw JSON only. No markdown. No code fences.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        content = response.choices[0].message.content.strip()

        # Strip any accidental markdown fences
        content = re.sub(r"^```[a-z]*\s*\n?", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\n?\s*```\s*$",    "", content, flags=re.IGNORECASE)
        content = content.strip()

        analysis = json.loads(content)

        # Validate expected keys exist
        if "summary" not in analysis:
            analysis["summary"] = "Analysis returned unexpected format."
        if "action" not in analysis:
            analysis["action"] = "Manual review recommended."
        if "parameter_updates" not in analysis or not isinstance(analysis["parameter_updates"], dict):
            analysis["parameter_updates"] = {}

        print("  [Qwen] API response parsed successfully.")

    except json.JSONDecodeError as e:
        print(f"  [Qwen] JSON parse error: {e}. Raw response: {content[:400]}")
        analysis = {
            "summary": f"Qwen returned a non-JSON response. Raw: {content[:300]}",
            "action":  "Manual review required. The model did not follow the JSON format.",
            "parameter_updates": {},
        }
    except Exception as e:
        err_msg = f"{e.__class__.__name__}: {e}"
        print(f"  [Qwen] API error: {err_msg}")
        analysis = {
            "summary": f"Qwen API call failed: {err_msg}",
            "action":  "Check QWEN_API_KEY validity and network connectivity on Railway.",
            "parameter_updates": {},
        }

    # Apply parameter updates safely
    updates = analysis.get("parameter_updates", {})
    if updates and isinstance(updates, dict):
        changed = _apply_parameters(updates)
        analysis["_applied_changes"] = changed
    else:
        analysis["_applied_changes"] = {}

    _save_analysis(analysis, now)
    return analysis


def _save_analysis(analysis, now):
    """Save analysis dict to disk."""
    try:
        out = dict(analysis)
        out["timestamp"] = now.isoformat()
        with open(ANALYSIS_FILE, "w") as f:
            json.dump(out, f, indent=2)
        print(f"  [Qwen] Analysis saved to {ANALYSIS_FILE}")
    except Exception as e:
        print(f"  [Qwen] Could not save analysis file: {e}")


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
