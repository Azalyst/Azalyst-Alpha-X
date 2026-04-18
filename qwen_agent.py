import json
import os
import time
from datetime import datetime, timezone, timedelta
import requests
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

TRADES_FILE = "paper_trades.json"
ANALYSIS_FILE = "qwen_analysis.json"
MAIN_PY_FILE = "main.py"
QWEN_API_KEY = os.environ.get("QWEN_API_KEY")

# Binance proxy override
FAPI_BASE = os.environ.get("BINANCE_PROXY_URL", "https://fapi.binance.com")

def get_top_movers(hours=4):
    try:
        resp = requests.get(f"{FAPI_BASE}/fapi/v1/ticker/24hr", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        # Sort by priceChangePercent descending for gainers
        sorted_data = sorted(data, key=lambda x: float(x.get('priceChangePercent', 0)), reverse=True)
        top_gainers = [{"symbol": d['symbol'], "change": d['priceChangePercent'] + "%"} for d in sorted_data[:5]]
        
        # Sort ascending for losers
        top_losers = [{"symbol": d['symbol'], "change": d['priceChangePercent'] + "%"} for d in sorted_data[-5:]]
        
        return top_gainers, top_losers
    except Exception as e:
        print(f"Error fetching top movers: {e}")
        return [], []

def analyze_and_fix():
    if not os.path.exists(TRADES_FILE):
        print("No trades file found.")
        return

    with open(TRADES_FILE, "r") as f:
        trades_data = json.load(f)

    closed_trades = trades_data.get("closed_trades", [])
    
    # Filter trades in last 4 hours
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
    recent_wins = [t for t in recent_trades if t.get("rpnl", 0) > 0]
    
    top_gainers, top_losers = get_top_movers(4)
    
    if not recent_losses and not top_gainers:
        print("No recent losses and no top movers to analyze. Skipping Qwen analysis.")
        return
        
    print(f"Analyzing {len(recent_losses)} losses, {len(recent_wins)} wins.")
    
    prompt = f"""
    You are an expert crypto trading quantitative analyst and AI agent.
    The current bot runs a Bollinger Band (200, 1) reversion/breakout strategy on 1m timeframe.
    It checks for RSI alignment on 1h and 4h.
    
    Recent losses in the last 4 hours: {json.dumps(recent_losses, indent=2)}
    Recent wins in the last 4 hours: {json.dumps(recent_wins, indent=2)}
    Top Binance Gainers (24h): {json.dumps(top_gainers)}
    Top Binance Losers (24h): {json.dumps(top_losers)}
    
    The bot missed some of the top gainers/losers, potentially because they didn't touch the upper/lower band, or the RSI filter blocked it.
    Analyze why the bot had losses and why it missed the top movers based on its original BB 200, 1 logic.
    
    Provide your response in raw JSON format with NO markdown wrapping, containing:
    {{
        "summary": "Your analysis of what went wrong and what we missed.",
        "action": "A summary of parameter adjustments you recommend (e.g. adjust TOUCH_TOL, RSI_LONG_1H, etc.)",
        "parameter_updates": {{
            "TOUCH_TOL": 0.003,
            "RSI_LONG_1H": 55
        }}
    }}
    """
    
    if not QWEN_API_KEY or OpenAI is None:
        print("QWEN_API_KEY missing or openai library not installed. Generating dummy analysis.")
        analysis = {
            "summary": "Dummy analysis since Qwen API is not configured. Bot missed big moves due to strict RSI filter.",
            "action": "Suggesting to slightly relax RSI and Touch Tolerance.",
            "parameter_updates": {"TOUCH_TOL": 0.0035}
        }
    else:
        try:
            client = OpenAI(
                api_key=QWEN_API_KEY,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            response = client.chat.completions.create(
                model="qwen-max",
                messages=[
                    {"role": "system", "content": "You are an autonomous quant dev AI."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            content = response.choices[0].message.content
            # Cleanup markdown if any
            content = content.replace("```json", "").replace("```", "").strip()
            analysis = json.loads(content)
        except Exception as e:
            print(f"Error querying Qwen API: {e}")
            analysis = {
                "summary": f"Failed to get Qwen analysis: {e}",
                "action": "None"
            }

    with open(ANALYSIS_FILE, "w") as f:
        json.dump(analysis, f, indent=2)
        
    print("Qwen analysis saved.")
    
    # Autonomously update main.py
    updates = analysis.get("parameter_updates", {})
    if updates:
        print("Autonomously applying parameter updates to main.py...")
        with open(MAIN_PY_FILE, "r") as f:
            code = f.read()
            
        for key, val in updates.items():
            import re
            # Match variable assignment like `TOUCH_TOL        = 0.0025`
            pattern = r"(" + key + r"\s*=\s*)([0-9\.]+)"
            code = re.sub(pattern, r"\g<1>" + str(val), code)
            
        with open(MAIN_PY_FILE, "w") as f:
            f.write(code)
        print("Updated main.py parameters.")

if __name__ == "__main__":
    analyze_and_fix()
