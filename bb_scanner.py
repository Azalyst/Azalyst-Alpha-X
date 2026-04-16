"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘   BB SCANNER  â€”  INSTITUTIONAL GRADE                             â•‘
â•‘   Binance Perpetual Futures  |  5m  |  BB(200, SD 1)             â•‘
â•‘   Paper Trading: 30x Leverage  |  Discord Webhook Alerts         â•‘
â•‘   Runs on:  Windows / Linux / macOS / Termux (Android)           â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

STRATEGY
â”€â”€â”€â”€â”€â”€â”€â”€
LONG  â€” Lower Band Recross: price closes below lower BB â†’ next candle closes back above â†’ BUY
SHORT â€” Upper Band Recross: price closes above upper BB â†’ next candle closes back below â†’ SELL
No middle band trades.

EXIT
â”€â”€â”€â”€
Target 1  â†’ Fibonacci Extension 1.272 (primary)
Target 2  â†’ Fibonacci Extension 1.618 (secondary)
Fallback  â†’ Upper / Lower Bollinger Band
Stop Loss â†’ Min (Long) or Max (Short) of signal candle & previous candle

â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
 INSTALL  â€”  PC (Windows / Linux / macOS)
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
   pip install pandas numpy requests matplotlib
   python bb_scanner.py

â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
 INSTALL  â€”  TERMUX (Android, runs 24/7 on phone)
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
 1. Install Termux from F-Droid  (the Play Store one is broken).
 2. Install Termux:API and Termux:Boot from F-Droid (optional but
    Termux:Boot lets the scanner auto-start when phone reboots).
 3. In Termux:

      pkg update && pkg upgrade -y
      pkg install python git -y
      pip install --upgrade pip
      pip install pandas numpy requests
      # matplotlib is OPTIONAL on Termux. Charts auto-disable if
      # not installed â€” Discord alerts still fire as text only.

 4. Put bb_scanner.py somewhere persistent, e.g. ~/scanner/
      mkdir -p ~/scanner && cd ~/scanner
      # copy bb_scanner.py here (via Termux storage / scp / etc.)

 5. Keep the CPU awake so Android does not freeze the process:
      pkg install termux-api -y
      termux-wake-lock          # release with: termux-wake-unlock

 6. Run:
      python bb_scanner.py

 7. Want it to survive Termux being closed? Run inside tmux:
      pkg install tmux -y
      tmux new -s scanner
      python bb_scanner.py
      # detach: Ctrl+B then D     reattach: tmux attach -t scanner

 8. Auto-start on boot (Termux:Boot installed):
      mkdir -p ~/.termux/boot
      cat > ~/.termux/boot/start-scanner <<'EOF'
      #!/data/data/com.termux/files/usr/bin/sh
      termux-wake-lock
      cd ~/scanner
      python bb_scanner.py >> scanner.log 2>&1
      EOF
      chmod +x ~/.termux/boot/start-scanner
"""

# â”€â”€â”€ STDLIB â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
import io, json, os, sys, time
from datetime import datetime, timezone

# Force UTF-8 stdout so emojis / box chars render cleanly on
# Windows cmd, Termux, and SSH sessions.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# â”€â”€â”€ THIRD-PARTY (required) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
import numpy  as np
import pandas as pd
import requests

# â”€â”€â”€ matplotlib is OPTIONAL (skip on Termux if it won't install) â”€
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot    as plt
    import matplotlib.gridspec  as gridspec
    HAS_CHART = True
except Exception as _e:
    HAS_CHART = False
    print(f"  [INFO] matplotlib unavailable ({_e.__class__.__name__}). "
          f"Discord alerts will be sent without chart images.")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘   USER CONFIG  â†  only section you need to edit
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
DISCORD_WEBHOOK  = (
    "https://discord.com/api/webhooks/1494071862609575948/"
    "G04AVF9M0nCp0FYPNDgBwyPzUee-9IMQFxr88uH88euQmaD4JM4LbV1cTofMqGqiz3fX"
)

BB_PERIOD        = 200          # Bollinger Band period
BB_SD            = 1            # Standard deviation multiplier
TIMEFRAME        = "10m"
CANDLE_LIMIT     = 320          # must be > BB_PERIOD + 50
SCAN_INTERVAL    = 900          # seconds between full scans (900 = 15 min)
LOOKBACK_WINDOW  = 600          # look back 10 min (600s) to check if conditions matched
REQUEST_DELAY    = 0.15         # seconds between API calls (rate-limit safe)
SWING_LOOKBACK   = 60           # candles back to find swing high / low
TOUCH_TOL        = 0.0025       # 0.25 % â€” band "touch" tolerance

# Paper trading
INITIAL_BALANCE  = 10_000.0     # starting virtual USDT
LEVERAGE         = 30           # leverage multiplier
RISK_PCT         = 0.02         # 2 % account risk per trade
MAX_MARGIN_PCT   = 0.25         # never use > 25 % of balance as margin per trade
SIGNAL_COOLDOWN  = 300          # seconds before same symbol can fire again
SUMMARY_EVERY    = 3600         # seconds between Discord portfolio summaries

# Anchor data files to the directory containing this script so they
# follow the .py file whether you launch it from Windows, Linux or
# Termux, regardless of the current working directory.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRADES_FILE = os.path.join(_SCRIPT_DIR, "paper_trades.json")

# Create a dedicated charts folder for all generated chart images
CHARTS_DIR = os.path.join(_SCRIPT_DIR, "charts")
if not os.path.exists(CHARTS_DIR):
    try:
        os.makedirs(CHARTS_DIR, exist_ok=True)
    except Exception as e:
        print(f"  [WARN] Could not create charts folder: {e}. Charts will save to script dir.")
        CHARTS_DIR = _SCRIPT_DIR

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘¡  EXCHANGE  â€”  direct REST (bypasses ccxt load_markets which
#                  also hits dapi.binance.com coin-futures and
#                  times-out in regions where that endpoint is blocked)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
FAPI_BASE = "https://fapi.binance.com"      # USDT-margined perpetuals only

_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})
_SESSION.headers.update({"User-Agent": "DiscordBot/1.0"})  # Better Cloudflare handling

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘¢  SIGNAL COOLDOWN & VALIDATION
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
_last_signal: dict[str, float] = {}   # symbol â†’ epoch
_signal_cache: dict[str, dict] = {}  # symbol â†’ {signal, timestamp, entry_price}

def on_cooldown(sym: str) -> bool:
    return (time.time() - _last_signal.get(sym, 0)) < SIGNAL_COOLDOWN

def mark_cooldown(sym: str):
    _last_signal[sym] = time.time()

# Signal validation: only execute if condition is FRESH (within 10 min) AND price hasn't moved >2%
SIGNAL_FRESHNESS = 600  # 10 minutes max age for a signal
SIGNAL_SLIPPAGE_PCT = 0.02  # Allow 2% price movement before rejecting signal

def is_signal_valid(sym: str, current_price: float) -> bool:
    """Check if cached signal is still valid (fresh + price hasn't slipped too much)."""
    if sym not in _signal_cache:
        return False
    
    cached = _signal_cache[sym]
    age = time.time() - cached["timestamp"]
    
    # â‘  Signal must be fresh (< 10 min old)
    if age > SIGNAL_FRESHNESS:
        print(f"    [REJECT] {sym}: Signal too old ({age:.0f}s > {SIGNAL_FRESHNESS}s)")
        return False
    
    # â‘¡ Entry price must not have slipped too far (>2%)
    entry = cached["entry_price"]
    slippage = abs(current_price - entry) / entry
    if slippage > SIGNAL_SLIPPAGE_PCT:
        print(f"    [REJECT] {sym}: Price slipped {slippage*100:.2f}% (> {SIGNAL_SLIPPAGE_PCT*100}%)")
        print(f"             Entry was {entry}, now {current_price}")
        return False
    
    print(f"    [VALID] {sym}: Signal fresh ({age:.0f}s old), price slip {slippage*100:.2f}%")
    return True

def cache_signal(sym: str, sig: dict, current_price: float):
    """Store signal with timestamp & price for later validation."""
    _signal_cache[sym] = {
        "signal": sig,
        "timestamp": time.time(),
        "entry_price": current_price
    }

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘£  DATA
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def get_symbols() -> list[str]:
    """
    Fetch all active USDT-margined perpetual symbols directly from
    fapi.binance.com/fapi/v1/exchangeInfo â€” no dapi.binance.com call,
    no ccxt load_markets() timeout.
    """
    url  = f"{FAPI_BASE}/fapi/v1/exchangeInfo"
    resp = _SESSION.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    syms = []
    for s in data["symbols"]:
        if (s.get("quoteAsset") == "USDT"
                and s.get("status")       == "TRADING"
                and s.get("contractType") == "PERPETUAL"):
            # store in ccxt-style  BTC/USDT  so rest of code is unchanged
            syms.append(s["baseAsset"] + "/USDT")
    return sorted(set(syms))


def _raw_symbol(ccxt_sym: str) -> str:
    """BTC/USDT  â†’  BTCUSDT  (fapi endpoint format)"""
    return ccxt_sym.replace("/", "")


# Map TIMEFRAME string to fapi interval strings (same convention, just confirm)
_TF_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h",
    "12h": "12h", "1d": "1d", "3d": "3d", "1w": "1w", "1M": "1M",
}

def fetch_df(symbol: str) -> pd.DataFrame | None:
    """
    Download klines directly from fapi.binance.com/fapi/v1/klines.
    Returns a DataFrame with columns: time, open, high, low, close, volume.
    """
    try:
        params = {
            "symbol":   _raw_symbol(symbol),
            "interval": _TF_MAP.get(TIMEFRAME, TIMEFRAME),
            "limit":    CANDLE_LIMIT,
        }
        resp = _SESSION.get(f"{FAPI_BASE}/fapi/v1/klines",
                            params=params, timeout=10)
        resp.raise_for_status()
        raw  = resp.json()
        # fapi klines columns:
        # 0=open_time 1=open 2=high 3=low 4=close 5=volume
        # 6=close_time 7=quote_vol 8=trades 9=taker_buy_base
        # 10=taker_buy_quote 11=ignore
        df = pd.DataFrame(raw, columns=[
            "time","open","high","low","close","volume",
            "close_time","quote_vol","trades",
            "taker_buy_base","taker_buy_quote","ignore"
        ])
        df = df[["time","open","high","low","close","volume"]].copy()
        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["time"] = pd.to_datetime(df["time"].astype(np.int64), unit="ms", utc=True)
        return df
    except Exception:
        return None

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘¤  INDICATORS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def add_bb(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["mid"]   = df["close"].rolling(BB_PERIOD).mean()
    df["std"]   = df["close"].rolling(BB_PERIOD).std(ddof=0)
    df["upper"] = df["mid"] + BB_SD * df["std"]
    df["lower"] = df["mid"] - BB_SD * df["std"]
    return df.dropna().reset_index(drop=True)

def sw_high(df: pd.DataFrame) -> float:
    return float(df.iloc[-(SWING_LOOKBACK + 1):-1]["high"].max())

def sw_low(df: pd.DataFrame) -> float:
    return float(df.iloc[-(SWING_LOOKBACK + 1):-1]["low"].min())

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘¥  SIGNAL DETECTION
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def _build(direction, condition, entry, sl):
    return {"direction": direction, "condition": condition,
            "entry": round(float(entry), 8), "sl": round(float(sl), 8)}

def long_c1(df) -> dict | None:
    """Lower Band Recross â†’ Long
    Price closes below lower band, then next candle closes back above it â†’ BUY"""
    s, p, c = df.iloc[-2], df.iloc[-3], df.iloc[-1]
    if (p["close"] <  p["lower"]   # prev candle closed below lower band
            and s["close"] >  s["lower"]   # signal candle closed back above lower band
            and c["close"] >  s["close"]): # current candle confirms move up
        return _build("LONG", "Lower Band Recross",
                      c["close"], min(s["low"], p["low"]))
    return None

def short_c1(df) -> dict | None:
    """Upper Band Recross â†’ Short
    Price closes above upper band, then next candle closes back below it â†’ SELL"""
    s, p, c = df.iloc[-2], df.iloc[-3], df.iloc[-1]
    if (p["close"] >  p["upper"]   # prev candle closed above upper band
            and s["close"] <  s["upper"]   # signal candle closed back below upper band
            and c["close"] <  s["close"]): # current candle confirms move down
        return _build("SHORT", "Upper Band Recross",
                      c["close"], max(s["high"], p["high"]))
    return None

# â”€â”€ Band Touch Momentum Logic (NEW) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def long_band_touch(df) -> dict | None:
    """Upper Band Breakout Pullback → Long
    Step 1: Price breaks ABOVE upper band (previous highs)
    Step 2: Price comes back DOWN to touch upper band
    Step 3: Price starts going UP again → BUY
    SL: Low of the candle that touched upper band"""
    
    # Need at least 3 candles: breakout candle, pullback candle, entry candle
    if len(df) < 3:
        return None
    
    breakout = df.iloc[-3]  # Candle that broke above upper band
    pullback = df.iloc[-2]  # Candle that came back to touch upper band
    entry = df.iloc[-1]     # Current candle showing upward momentum
    
    band_touch_tol = pullback["upper"] * TOUCH_TOL
    
    # Step 1: Breakout candle closed ABOVE upper band
    broke_above = breakout["close"] > breakout["upper"]
    
    # Step 2: Pullback candle touched upper band (low touches or close at band)
    # The pullback should come FROM above TO the band
    touched_on_pullback = (
        pullback["low"] <= pullback["upper"] + band_touch_tol  # low touches band
        and pullback["high"] >= pullback["upper"]  # still reaches band
    )
    
    # Step 3: Entry candle shows upward momentum (close > pullback close)
    momentum_up = entry["close"] > pullback["close"]
    
    # Additional: pullback candle should be coming down (close < open or close < breakout close)
    coming_down = pullback["close"] < breakout["close"]
    
    if broke_above and touched_on_pullback and momentum_up and coming_down:
        return _build("LONG", "Upper Band Breakout Pullback",
                      entry["close"], pullback["low"])
    return None

def short_band_touch(df) -> dict | None:
    """Lower Band Breakdown Pullback → Short
    Step 1: Price breaks BELOW lower band (previous lows)
    Step 2: Price comes back UP to touch lower band
    Step 3: Price starts going DOWN again → SELL
    SL: High of the candle that touched lower band"""
    
    # Need at least 3 candles: breakdown candle, pullback candle, entry candle
    if len(df) < 3:
        return None
    
    breakdown = df.iloc[-3]  # Candle that broke below lower band
    pullback = df.iloc[-2]   # Candle that came back to touch lower band
    entry = df.iloc[-1]      # Current candle showing downward momentum
    
    band_touch_tol = abs(pullback["lower"]) * TOUCH_TOL
    
    # Step 1: Breakdown candle closed BELOW lower band
    broke_below = breakdown["close"] < breakdown["lower"]
    
    # Step 2: Pullback candle touched lower band (high touches or close at band)
    # The pullback should come FROM below TO the band
    touched_on_pullback = (
        pullback["high"] >= pullback["lower"] - band_touch_tol  # high touches band
        and pullback["low"] <= pullback["lower"]  # still reaches band
    )
    
    # Step 3: Entry candle shows downward momentum (close < pullback close)
    momentum_down = entry["close"] < pullback["close"]
    
    # Additional: pullback candle should be coming up (close > open or close > breakdown close)
    coming_up = pullback["close"] > breakdown["close"]
    
    if broke_below and touched_on_pullback and momentum_down and coming_up:
        return _build("SHORT", "Lower Band Breakdown Pullback",
                      entry["close"], pullback["high"])
    return None

CHECKERS = [long_band_touch, short_band_touch]

# â”€â”€ Targets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def build_targets(df: pd.DataFrame, sig: dict) -> dict:
    e  = sig["entry"]
    sl = sig["sl"]
    d  = sig["direction"]
    sh, sl_ = sw_high(df), sw_low(df)
    move = sh - sl_

    if d == "LONG":
        t1 = round(e + move * 1.272, 8)
        t2 = round(e + move * 1.618, 8)
        fb = round(float(df.iloc[-1]["upper"]), 8)
        return {
            "tp1": t1 if t1 > e else None,
            "tp2": t2 if t2 > e else None,
            "fallback": fb,
            "swing_high": round(sh, 8),
            "swing_low":  round(sl_, 8),
        }
    else:
        t1 = round(e - move * 1.272, 8)
        t2 = round(e - move * 1.618, 8)
        fb = round(float(df.iloc[-1]["lower"]), 8)
        return {
            "tp1": t1 if t1 < e else None,
            "tp2": t2 if t2 < e else None,
            "fallback": fb,
            "swing_high": round(sh, 8),
            "swing_low":  round(sl_, 8),
        }

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘¦  PAPER TRADER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class PaperTrader:

    def __init__(self):
        self._load()

    # â”€â”€ persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _load(self):
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE) as f:
                d = json.load(f)
            self.balance       = d["balance"]
            self.open_trades   = d["open_trades"]
            self.closed_trades = d["closed_trades"]
            self.counter       = d["counter"]
        else:
            self.balance, self.open_trades  = INITIAL_BALANCE, []
            self.closed_trades, self.counter = [], 0
            self._save()

    def _save(self):
        with open(TRADES_FILE, "w") as f:
            json.dump({"balance": round(self.balance, 6),
                       "open_trades":   self.open_trades,
                       "closed_trades": self.closed_trades,
                       "counter":       self.counter}, f, indent=2)

    # â”€â”€ open â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def open_trade(self, symbol: str, sig: dict, targets: dict) -> dict | None:
        e  = sig["entry"]
        sl = sig["sl"]
        sl_pct = abs(e - sl) / e
        if sl_pct < 0.0001:
            return None

        risk_usdt = self.balance * RISK_PCT
        notional  = risk_usdt / sl_pct          # full leveraged position size
        margin    = notional / LEVERAGE

        # Cap margin
        if margin > self.balance * MAX_MARGIN_PCT:
            margin   = self.balance * MAX_MARGIN_PCT
            notional = margin * LEVERAGE

        self.counter += 1
        trade = {
            "id":        f"T{self.counter:04d}",
            "symbol":    symbol,
            "direction": sig["direction"],
            "condition": sig["condition"],
            "entry":     e,
            "sl":        sl,
            "tp1":       targets.get("tp1"),
            "tp2":       targets.get("tp2"),
            "fallback":  targets["fallback"],
            "notional":  round(notional, 4),
            "margin":    round(margin,   4),
            "leverage":  LEVERAGE,
            "qty":       round(notional / e, 6),
            "open_time": datetime.now(timezone.utc).isoformat(),
            "status":    "OPEN",
            "upnl":      0.0,
        }
        self.open_trades.append(trade)
        self._save()
        return trade

    # â”€â”€ mark-to-market & auto-close â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def update(self, prices: dict, df_dict: dict = None) -> list[dict]:
        """Update trades and check for band-touch exits.
        
        Args:
            prices: Current prices by symbol
            df_dict: Optional dict of DataFrames by symbol for band-touch exit logic
        """
        still_open, closed = [], []

        for t in self.open_trades:
            px = prices.get(t["symbol"])
            if px is None:
                still_open.append(t)
                continue

            d  = t["direction"]
            cp = cr = None                          # close_price, close_reason

            # Check for band-touch exit first (only if we have OHLC data)
            # LONG exit: price went above upper band, now touching it on pullback
            # SHORT exit: price went below lower band, now touching it on bounce
            if df_dict and t["symbol"] in df_dict:
                df = df_dict[t["symbol"]]
                if len(df) >= 3:
                    upper = df.iloc[-1]["upper"]
                    lower = df.iloc[-1]["lower"]
                    prev = df.iloc[-2]
                    
                    if d == "LONG":
                        # Check if price was above upper band recently and now touching it
                        was_above = any(df.iloc[i]["close"] > df.iloc[i]["upper"] 
                                       for i in range(-4, -1))
                        touching_now = (prev["low"] <= upper + upper*TOUCH_TOL 
                                       and prev["high"] >= upper)
                        if was_above and touching_now:
                            cp, cr = px, "Upper Band Touch Exit ✅"
                    
                    elif d == "SHORT":
                        # Check if price was below lower band recently and now touching it
                        was_below = any(df.iloc[i]["close"] < df.iloc[i]["lower"] 
                                       for i in range(-4, -1))
                        touching_now = (prev["high"] >= lower - abs(lower)*TOUCH_TOL 
                                       and prev["low"] <= lower)
                        if was_below and touching_now:
                            cp, cr = px, "Lower Band Touch Exit ✅"

            # Standard exit checks (only if not already exited via band touch)
            if cp is None:
                if d == "LONG":
                    if   px <= t["sl"]:                           cp, cr = t["sl"],  "SL ❌ Stop Loss"
                    elif t["tp2"] and px >= t["tp2"]:             cp, cr = t["tp2"], "TP2 ✅ Fib 1.618"
                    elif t["tp1"] and px >= t["tp1"]:             cp, cr = t["tp1"], "TP1 ✅ Fib 1.272"
                    else: t["upnl"] = round((px - t["entry"]) / t["entry"] * t["notional"], 4)
                else:
                    if   px >= t["sl"]:                           cp, cr = t["sl"],  "SL ❌ Stop Loss"
                    elif t["tp2"] and px <= t["tp2"]:             cp, cr = t["tp2"], "TP2 ✅ Fib 1.618"
                    elif t["tp1"] and px <= t["tp1"]:             cp, cr = t["tp1"], "TP1 ✅ Fib 1.272"
                    else: t["upnl"] = round((t["entry"] - px) / t["entry"] * t["notional"], 4)

            if cp is not None:
                mult = 1 if d == "LONG" else -1
                pnl  = mult * (cp - t["entry"]) / t["entry"] * t["notional"]
                t.update({"status": "CLOSED", "close_price": round(cp, 8),
                           "close_reason": cr,
                           "close_time":  datetime.now(timezone.utc).isoformat(),
                           "rpnl": round(pnl, 4)})
                self.balance += pnl
                self.closed_trades.append(t)
                closed.append(t)
            else:
                still_open.append(t)

        self.open_trades = still_open
        self._save()
        return closed

    # â”€â”€ stats â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def stats(self) -> dict:
        wins  = [t for t in self.closed_trades if t.get("rpnl", 0) > 0]
        loss  = [t for t in self.closed_trades if t.get("rpnl", 0) <= 0]
        rpnl  = sum(t.get("rpnl",  0) for t in self.closed_trades)
        upnl  = sum(t.get("upnl",  0) for t in self.open_trades)
        wr    = len(wins)/len(self.closed_trades)*100 if self.closed_trades else 0
        return {
            "balance":   round(self.balance, 2),
            "open":      len(self.open_trades),
            "closed":    len(self.closed_trades),
            "wins":      len(wins),
            "losses":    len(loss),
            "win_rate":  round(wr, 1),
            "rpnl":      round(rpnl, 2),
            "upnl":      round(upnl, 2),
            "ret_pct":   round((self.balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100, 2),
        }

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘§  CHART  (dark theme, professional)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
BG      = "#0d1117"
BULL    = "#26a69a"
BEAR    = "#ef5350"
BB_CLR  = "#3b82f6"
MID_CLR = "#f97316"
GRID    = "#1c2333"
FG      = "#8b949e"
WHITE   = "#e6edf3"

def make_chart(df: pd.DataFrame, sig: dict, tgt: dict, symbol: str) -> bytes | None:
    """Render the signal chart. Returns None if matplotlib is unavailable
    (e.g. on Termux where it cannot easily be built)."""
    if not HAS_CHART:
        return None
    plot = df.tail(120).copy().reset_index(drop=True)
    n    = len(plot)
    d    = sig["direction"]
    xs   = np.arange(n)

    fig  = plt.figure(figsize=(15, 8), facecolor=BG)
    gs   = gridspec.GridSpec(2, 1, figure=fig, height_ratios=[4, 1])
    ax   = fig.add_subplot(gs[0])
    axv  = fig.add_subplot(gs[1], sharex=ax)

    for a in (ax, axv):
        a.set_facecolor(BG)
        a.tick_params(colors=FG, labelsize=8)
        for sp in a.spines.values():
            sp.set_color(GRID)
        a.grid(color=GRID, linewidth=0.6, alpha=0.7)
        a.yaxis.set_label_position("right")
        a.yaxis.tick_right()

    # â”€â”€ Bollinger Bands â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ax.fill_between(xs, plot["upper"], plot["lower"],
                    color=BB_CLR, alpha=0.06, zorder=1)
    ax.plot(xs, plot["upper"], color=BB_CLR, lw=1.3, label=f"Upper BB", zorder=2)
    ax.plot(xs, plot["mid"],   color=MID_CLR, lw=1.3, label="SMA 200",   zorder=2)
    ax.plot(xs, plot["lower"], color=BB_CLR, lw=1.0, ls="--",
            label="Lower BB", alpha=0.8, zorder=2)

    # â”€â”€ Candles â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    for i, row in plot.iterrows():
        col = BULL if row["close"] >= row["open"] else BEAR
        ax.plot([i, i], [row["low"], row["high"]], color=col, lw=0.9, zorder=3)
        ax.bar(i, abs(row["close"] - row["open"]),
               bottom=min(row["open"], row["close"]),
               color=col, width=0.7, zorder=4, alpha=0.95)

    # â”€â”€ Volume â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    vcols = [BULL if plot.iloc[i]["close"] >= plot.iloc[i]["open"] else BEAR
             for i in range(n)]
    axv.bar(xs, plot["volume"], color=vcols, alpha=0.65, width=0.7)
    axv.set_ylabel("Volume", color=FG, fontsize=8)

    # â”€â”€ Signal marker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    si = n - 2
    is_long = d == "LONG"
    y0 = plot.iloc[si]["low"]  * 0.9965 if is_long else plot.iloc[si]["high"] * 1.0035
    ytext = y0 * 0.993 if is_long else y0 * 1.007
    lbl   = "â–²  LONG"  if is_long else "â–¼  SHORT"
    mcol  = "#22c55e"  if is_long else "#ef4444"
    ax.annotate(
        lbl, xy=(si, y0), xytext=(si, ytext),
        color=mcol, fontsize=9.5, fontweight="bold", ha="center",
        va="top" if is_long else "bottom",
        arrowprops=dict(arrowstyle="-|>", color=mcol, lw=1.4),
        zorder=10,
    )

    # â”€â”€ Level lines â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def hline(y, color, label, ls="--", lw=1.0):
        if y is None:
            return
        ax.axhline(y, color=color, lw=lw, ls=ls, alpha=0.90, zorder=5)
        ax.text(n + 0.3, y, f" {label}\n {y:.6g}",
                color=color, fontsize=7.5, va="center",
                ha="left", transform=ax.get_yaxis_transform(),
                clip_on=False)

    hline(sig["entry"],    "#facc15", "ENTRY",       lw=1.2)
    hline(sig["sl"],       "#ef4444", "SL",           lw=1.2)
    hline(tgt.get("tp1"), "#22c55e", "TP1 1.272",    lw=1.0)
    hline(tgt.get("tp2"), "#4ade80", "TP2 1.618",    lw=0.9, ls="-.")
    hline(tgt["fallback"], "#60a5fa", "Fallback BB",  lw=0.9, ls=":")

    # â”€â”€ X axis labels â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    step = max(1, n // 10)
    plt.setp(ax.get_xticklabels(), visible=False)
    axv.set_xticks(range(0, n, step))
    axv.set_xticklabels(
        [plot.iloc[i]["time"].strftime("%d %b\n%H:%M") for i in range(0, n, step)],
        fontsize=7, color=FG
    )

    # â”€â”€ Legend & Title â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ax.legend(loc="upper left", facecolor="#161b22", labelcolor=FG,
              fontsize=8.5, framealpha=0.9, edgecolor=GRID)
    fig.suptitle(
        f"  {symbol}   Â·   BB({BB_PERIOD}, {BB_SD})   Â·   {TIMEFRAME}   Â·   {sig['condition']}",
        color=WHITE, fontsize=12, fontweight="bold", x=0.01, ha="left", y=0.99
    )

    # tight_layout is incompatible with GridSpec + sharex axes â€” use subplots_adjust instead
    fig.subplots_adjust(left=0.03, right=0.88, top=0.96, bottom=0.07, hspace=0.03)
    buf = io.BytesIO()
    # Save without bbox_inches to avoid conflicts with subplots_adjust
    plt.savefig(buf, format="png", dpi=75, facecolor=BG, edgecolor="none", pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    return buf.read()

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘¨  DISCORD  â€”  institutional monospace style, no emojis
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
_SEP  = "â”€" * 44        # section divider inside code blocks
_W    = 18              # label column width for alignment

def _kv(label: str, value: str) -> str:
    """Left-aligned key : value row, fixed label width."""
    return f"{label:<{_W}}: {value}"

def _rr(entry, target, sl) -> str:
    risk = abs(entry - sl)
    if not risk or target is None:
        return "â€”"
    return f"{abs(target - entry) / risk:.2f}x R:R"

def _strip_attachment_images(payload: dict) -> dict:
    """Return a payload copy without attachment:// image references."""
    clean = json.loads(json.dumps(payload))
    clean.pop("attachments", None)
    for embed in clean.get("embeds", []):
        image = embed.get("image")
        if isinstance(image, dict) and str(image.get("url", "")).startswith("attachment://"):
            embed.pop("image", None)
    return clean

def _post(payload: dict, chart: bytes | None = None):
    """Post a Discord message (embed + optional chart attachment).

    Discord expects multipart uploads to use files[n] field names, with
    payload_json carrying the non-file JSON body. When an embed references an
    uploaded image via attachment://chart.png, include attachment metadata and
    wait for server confirmation so upload problems surface immediately.
    """
    last_error = None

    for attempt in range(1, 5):  # Increased to 4 attempts
        try:
            if chart:
                # Debug: log chart upload attempt
                chart_size_kb = len(chart) / 1024
                print(f"  [DEBUG] Uploading chart ({chart_size_kb:.1f} KB) to Discord...")
                # Simple multipart upload - Discord webhooks don't need attachments metadata
                # Increased timeout to 60s for chart uploads
                r = _SESSION.post(
                    DISCORD_WEBHOOK,
                    data={"payload_json": json.dumps(payload)},
                    files={"file": ("chart.png", chart, "image/png")},
                    timeout=60,
                )
                print(f"  [DEBUG] Discord response: HTTP {r.status_code}")
            else:
                r = _SESSION.post(
                    DISCORD_WEBHOOK,
                    params={"wait": "true"},
                    json=payload,
                    timeout=25,
                )

            if r.status_code == 429:
                retry_after = 5.0
                try:
                    retry_after = float(r.json().get("retry_after", retry_after))
                except Exception:
                    pass
                print(f"  ! Discord rate limited. Retrying in {retry_after:.2f}s...")
                time.sleep(min(max(retry_after, 1.0), 60.0))
                continue

            if r.status_code >= 500 and attempt < 3:
                print(f"  ! Discord HTTP {r.status_code}. Retrying in {attempt * 2}s...")
                time.sleep(attempt * 2)
                continue

            if not r.ok:
                print(f"  ! Discord HTTP {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
            return

        except requests.HTTPError as ex:
            last_error = ex
            break
        except requests.RequestException as ex:
            last_error = ex
            if attempt >= 3:
                break
            backoff = attempt * 2
            print(f"  ! Discord network error ({ex.__class__.__name__}): {ex}. "
                  f"Retrying in {backoff}s...")
            time.sleep(backoff)
        except Exception as ex:
            last_error = ex
            break

    if chart is not None:
        print("  ! Discord chart upload failed. Retrying once without chart...")
        _post(_strip_attachment_images(payload), None)
        return

    if last_error is not None:
        print(f"  ! Discord error: {last_error}")


def _post_chart_only(symbol: str, sig: dict, chart: bytes):
    """Post the chart exactly like azalyst_trend_following_strategy.py - proven working method."""
    pair = symbol.replace("/USDT", "") + " / USDT"
    
    # Use the exact approach from azalyst that WORKS
    embed = {
        "title": f"ðŸ“Š {sig['direction']} {pair} | {sig['condition']}",
        "color": 2263127 if sig["direction"] == "LONG" else 15728640,  # green or red
        "description": f"Signal: {sig['condition']}\nEntry: {sig['entry']}\nStop Loss: {sig['sl']}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    payload_json = json.dumps({"embeds": [embed]})
    
    try:
        print(f"  [DEBUG] Sending chart to Discord (exact azalyst method)...")
        # Exact method from azalyst_trend_following_strategy.py
        r = _SESSION.post(
            DISCORD_WEBHOOK,
            data={"payload_json": payload_json},
            files={"file": ("chart.png", chart, "image/png")},
            timeout=60,
        )
        print(f"  [DEBUG] Chart upload response: HTTP {r.status_code}")
        if r.status_code == 200 or r.status_code == 204:
            print(f"  âœ… Chart sent successfully to Discord")
        else:
            print(f"  ! Chart upload returned HTTP {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
    except Exception as ex:
        print(f"  ! Chart send error ({ex.__class__.__name__}): {ex}")


def discord_signal_with_chart(symbol: str, sig: dict, tgt: dict,
                               trade: dict, stats: dict, chart_bytes: bytes | None):
    """NEW SIGNAL alert â€” detailed trade card + standalone chart."""
    d        = sig["direction"]
    is_long  = d == "LONG"
    color    = 0x22c55e if is_long else 0xef4444
    e, sl    = sig["entry"], sig["sl"]
    rsk_pct  = abs(e - sl) / e * 100
    tp1_str  = str(tgt.get("tp1") or "â€”")
    tp2_str  = str(tgt.get("tp2") or "â€”")
    ts       = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S UTC")
    pair     = symbol.replace("/USDT", "") + " / USDT"

    # Pre-compute values to avoid backslashes inside f-string expressions (Python 3.11 limitation)
    tp1_rr      = _rr(e, tgt.get("tp1"), sl)
    tp2_rr      = _rr(e, tgt.get("tp2"), sl)
    notional_v  = trade["notional"]
    margin_v    = trade["margin"]
    bal_v       = stats["balance"]
    ret_v       = stats["ret_pct"]
    win_v       = stats["win_rate"]

    body = "\n".join([
        f"  {d}   {pair}",
        f"  {sig['condition']}",
        f"  BB({BB_PERIOD},{BB_SD})  |  {TIMEFRAME}  |  Binance Perp  |  {LEVERAGE}x Paper",
        f"  {_SEP}",
        f"  {_kv('Entry',        str(e))}",
        f"  {_kv('Stop Loss',    f'{sl}   ({rsk_pct:.2f}% risk)')}",
        f"  {_kv('TP1  Fib 1.272', f'{tp1_str}   [{tp1_rr}]')}",
        f"  {_kv('TP2  Fib 1.618', f'{tp2_str}   [{tp2_rr}]')}",
        f"  {_kv('Fallback BB',  str(tgt['fallback']))}",
        f"  {_SEP}",
        f"  {_kv('Swing High',   str(tgt['swing_high']))}",
        f"  {_kv('Swing Low',    str(tgt['swing_low']))}",
        f"  {_SEP}",
        f"  {_kv('Position ID',  trade['id'])}",
        f"  {_kv('Notional',     f'$ {notional_v:>12,.2f}')}",
        f"  {_kv('Margin',       f'$ {margin_v:>12,.2f}')}",
        f"  {_kv('Qty',          str(trade['qty']))}",
        f"  {_SEP}",
        f"  {_kv('Balance',      f'$ {bal_v:>12,.2f}')}",
        f"  {_kv('Return',       f'{ret_v:+.2f}%')}",
        f"  {_kv('Open Trades',  str(stats['open']))}",
        f"  {_kv('Win Rate',     f'{win_v}%')}",
        f"  {_SEP}",
        f"  {ts}",
        f"  BB Scanner  |  For informational use only",
    ])

    embed = {
        "color":       color,
        "description": f"```\n{body}\n```",
    }
    # one-liner notification title in the message content (shows in push notifications)
    payload = {
        "content": f"**BB SCANNER  |  NEW SIGNAL  |  {d}  {pair}  |  {sig['condition'].upper()}**",
        "embeds":  [embed],
    }
    # Send text alert first (guaranteed to work)
    _post(payload)
    # Then send chart separately
    if chart_bytes:
        print(f"  [DEBUG] Sending chart separately after text alert...")
        _post_chart_only(symbol, sig, chart_bytes)


def discord_close(trade: dict, stats: dict):
    """Trade closed â€” WIN or LOSS."""
    rpnl   = trade.get("rpnl", 0)
    color  = 0x22c55e if rpnl > 0 else 0xef4444
    result = "WIN" if rpnl > 0 else "LOSS"
    pct    = (trade["close_price"] - trade["entry"]) / trade["entry"] * 100
    if trade["direction"] == "SHORT":
        pct = -pct
    ts     = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S UTC")
    pair   = trade["symbol"].replace("/USDT", "") + " / USDT"

    # Pre-compute (Python 3.11 disallows backslashes in f-string expressions)
    _bal = stats["balance"]
    _ret = stats["ret_pct"]
    _wr  = stats["win_rate"]
    _w   = stats["wins"]
    _l   = stats["losses"]

    body = "\n".join([
        f"  CLOSED   {pair}   ({trade['direction']})   {result}",
        f"  {trade['close_reason']}",
        f"  {_SEP}",
        f"  {_kv('Trade ID',    trade['id'])}",
        f"  {_kv('Condition',   trade['condition'])}",
        f"  {_SEP}",
        f"  {_kv('Entry',       str(trade['entry']))}",
        f"  {_kv('Exit',        str(trade['close_price']))}",
        f"  {_kv('PnL',         f'$ {rpnl:>+12,.2f}   ({pct:+.2f}%)')}",
        f"  {_SEP}",
        f"  {_kv('Balance',     f'$ {_bal:>12,.2f}')}",
        f"  {_kv('Return',      f'{_ret:+.2f}%')}",
        f"  {_kv('Win Rate',    f'{_wr}%   ({_w}W / {_l}L)')}",
        f"  {_SEP}",
        f"  {ts}",
        f"  BB Scanner  |  For informational use only",
    ])

    payload = {
        "content": f"**BB SCANNER  |  TRADE CLOSED  |  {trade['id']}  {pair}  |  PnL  ${rpnl:+,.2f}**",
        "embeds":  [{"color": color, "description": f"```\n{body}\n```"}],
    }
    _post(payload)


def discord_summary(trader: PaperTrader):
    """Hourly portfolio summary."""
    s  = trader.stats()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S UTC")

    pos_lines = []
    for t in trader.open_trades:
        pair = t["symbol"].replace("/USDT", "")
        pos_lines.append(
            f"  {t['id']}  {pair:<10}  {t['direction']:<5}"
            f"  Entry {t['entry']}   uPnL ${t.get('upnl', 0):>+,.2f}"
        )
    positions_block = "\n".join(pos_lines) if pos_lines else "  No open positions"

    # Pre-compute (Python 3.11 disallows backslashes in f-string expressions)
    _sb   = s["balance"]
    _sr   = s["ret_pct"]
    _srp  = s["rpnl"]
    _sup  = s["upnl"]
    _swr  = s["win_rate"]
    _sw   = s["wins"]
    _sl   = s["losses"]

    body = "\n".join([
        "  BB SCANNER PAPER PORTFOLIO  â€”  HOURLY REPORT",
        f"  {ts}",
        f"  {_SEP}",
        f"  {_kv('Balance',       f'$ {_sb:>12,.2f}')}",
        f"  {_kv('Total Return',  f'{_sr:+.2f}%')}",
        f"  {_kv('Realised PnL',  f'$ {_srp:>+12,.2f}')}",
        f"  {_kv('Unrealised',    f'$ {_sup:>+12,.2f}')}",
        f"  {_SEP}",
        f"  {_kv('Win Rate',      f'{_swr}%   ({_sw}W / {_sl}L)')}",
        f"  {_kv('Open Trades',   str(s['open']))}",
        f"  {_kv('Closed Trades', str(s['closed']))}",
        f"  {_SEP}",
        "  OPEN POSITIONS",
        f"  {'ID':<6}  {'TICKER':<10}  {'DIR':<5}  {'ENTRY':<14}  UNREALISED PnL",
        f"  {_SEP}",
        positions_block,
        f"  {_SEP}",
        f"  BB({BB_PERIOD},{BB_SD})  |  {TIMEFRAME}  |  {LEVERAGE}x Paper  |  Binance Perp",
        "  BB Scanner  |  For informational use only",
    ])

    payload = {
        "content": (f"**BB SCANNER  |  HOURLY SUMMARY  |  "
                    f"PORTFOLIO: ${s['balance']:,.2f}  |  RETURN: {s['ret_pct']:+.2f}%**"),
        "embeds":  [{"color": 0x3b82f6, "description": f"```\n{body}\n```"}],
    }
    _post(payload)


def discord_startup(n_symbols: int, balance: float):
    """System online notification."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S UTC")

    body = "\n".join([
        "  BB SCANNER  â€”  SYSTEM ACTIVE",
        f"  {ts}",
        f"  {_SEP}",
        f"  {_kv('Strategy',       f'BB({BB_PERIOD},{BB_SD})  |  {TIMEFRAME}')}",
        f"  {_kv('Exchange',       'Binance USDT-Margined Perpetuals')}",
        f"  {_kv('Universe',       f'{n_symbols} active USDT perpetuals')}",
        f"  {_kv('Scan interval',  f'Every {SCAN_INTERVAL // 60} min  ({SCAN_INTERVAL}s)')}",
        f"  {_kv('Leverage',       f'{LEVERAGE}x paper trading')}",
        f"  {_kv('Start balance',  f'$ {balance:>12,.2f}')}",
        f"  {_SEP}",
        "  SIGNAL CONDITIONS",
        "  LONG  : Lower Band Recross (closed below â†’ closes back above lower BB)",
        "  SHORT : Upper Band Recross (closed above â†’ closes back below upper BB)",
        f"  {_SEP}",
        "  SIGNAL VALIDATION (NEW)",
        f"  â€¢ Signal freshness: {SIGNAL_FRESHNESS//60} min max age",
        f"  â€¢ Price slippage tolerance: {SIGNAL_SLIPPAGE_PCT*100:.1f}%",
        "  Stale or slipped signals are REJECTED (no trade opens)",
        f"  {_SEP}",
        "  EXIT LOGIC",
        "  Primary    : Fib Extension 1.272",
        "  Secondary  : Fib Extension 1.618",
        "  Fallback   : Bollinger Band",
        "  Stop Loss  : Signal / prev candle extreme",
        f"  {_SEP}",
        "  BB Scanner  |  For informational use only",
    ])

    payload = {
        "content": f"**BB SCANNER  |  SYSTEM ONLINE  |  {n_symbols} SYMBOLS  |  ${balance:,.2f} PAPER  |  VALIDATION ENABLED**",
        "embeds":  [{"color": 0x3b82f6, "description": f"```\n{body}\n```"}],
    }
    _post(payload)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘©  SCAN LOOP
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def scan(symbols: list[str], trader: PaperTrader) -> int:
    found  = 0
    prices = {}   # symbol â†’ last close price

    for i, sym in enumerate(symbols, 1):
        try:
            df = fetch_df(sym)
            if df is None or len(df) < BB_PERIOD + 15:
                time.sleep(REQUEST_DELAY)
                continue

            df = add_bb(df)
            prices[sym] = float(df.iloc[-1]["close"])

            # â”€â”€ Signal check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if not on_cooldown(sym):
                for fn in CHECKERS:
                    sig = fn(df)
                    if sig:
                        tgt   = build_targets(df, sig)
                        trade = trader.open_trade(sym, sig, tgt)
                        if trade is None:
                            break

                        chart = make_chart(df, sig, tgt, sym)
                        if chart is None:
                            print(f"  [WARN] Chart skipped for {sym} â€” matplotlib not available. "
                                  f"Install it with: pip install matplotlib")
                        else:
                            chart_size_kb = len(chart)/1024
                            print(f"  [DEBUG] Chart generated: {chart_size_kb:.1f} KB")
                            # Save chart locally in organized charts folder
                            try:
                                chart_file = os.path.join(CHARTS_DIR, f"chart_{sym.replace('/', '_')}_{int(time.time())}.png")
                                with open(chart_file, "wb") as f:
                                    f.write(chart)
                                print(f"  [DEBUG] Chart saved: {chart_file}")
                            except Exception as ex:
                                print(f"  [WARN] Could not save chart locally: {ex}")
                        
                        stats = trader.stats()
                        discord_signal_with_chart(sym, sig, tgt, trade, stats, chart)
                        mark_cooldown(sym)
                        found += 1

                        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                        print(f"  [{ts}] ðŸ”” {sig['direction']} {sym}  "
                              f"Entry={sig['entry']}  SL={sig['sl']}")
                        break   # one signal per symbol per scan

            if i % 50 == 0 or i == len(symbols):
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                print(f"  [{ts}] Scanned {i}/{len(symbols)}  Â·  signals: {found}")

            time.sleep(REQUEST_DELAY)

        except Exception as ex:
            print(f"  ! {sym}: {ex}")
            time.sleep(REQUEST_DELAY)

    # â”€â”€ Auto-close trades â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Build df_dict for band-touch exit logic (only for symbols with open trades)
    df_dict = {}
    for t in trader.open_trades:
        sym = t["symbol"]
        if sym in prices:  # Only fetch if we have price data
            try:
                df = fetch_df(sym)
                if df is not None and len(df) >= BB_PERIOD + 15:
                    df = add_bb(df)
                    df_dict[sym] = df
            except Exception:
                pass  # Skip if fetch fails, will use standard exit logic
    
    closed = trader.update(prices, df_dict if df_dict else None)
    for t in closed:
        rpnl = t.get("rpnl", 0)
        print(f"  ðŸ’° CLOSED {t['id']} {t['symbol']}  {t['close_reason']}"
              f"  PnL=${rpnl:+.2f}")
        discord_close(t, trader.stats())

    return found

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  â‘ª  ENTRY POINT
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def main():
    print()
    print("â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—")
    print("â•‘   BB SCANNER  â€”  INSTITUTIONAL GRADE                         â•‘")
    print("â•‘   Binance Perpetual  Â·  5m  Â·  BB(200,1)  Â·  30x Paper       â•‘")
    print("â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•")
    print(f"  Platform : {sys.platform}    Python : {sys.version.split()[0]}")
    print(f"  Charts   : {'ON (matplotlib)' if HAS_CHART else 'OFF (text-only Discord alerts)'}")
    print(f"  Trades   : {TRADES_FILE}")

    trader = PaperTrader()
    s      = trader.stats()
    print(f"  Paper Portfolio  â†’  Balance: ${s['balance']:,.2f}  "
          f"Â·  Open: {s['open']}  Â·  Closed: {s['closed']}")

    # Robust symbol fetch â€” Termux / mobile networks can drop the first
    # call. Retry forever with backoff instead of crashing.
    symbols = []
    backoff = 5
    while not symbols:
        try:
            print("  Loading Binance symbols...")
            symbols = get_symbols()
            print(f"  {len(symbols)} USDT perpetuals loaded.")
        except Exception as ex:
            print(f"  ! Symbol fetch failed ({ex.__class__.__name__}: {ex}). "
                  f"Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)
    print()

    try:
        discord_startup(len(symbols), trader.balance)
    except Exception as ex:
        print(f"  ! Startup notification failed: {ex}")

    scan_no      = 0
    last_summary = time.time()

    while True:
        scan_no += 1
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'â”€'*66}")
        print(f"  SCAN #{scan_no:04d}  Â·  {ts} UTC")
        print(f"{'â”€'*66}")

        try:
            n = scan(symbols, trader)
            s = trader.stats()
            print(f"\n  âœ…  Scan #{scan_no:04d} complete  Â·  Signals: {n}")
            print(f"  ðŸ’¼  Balance: ${s['balance']:,.2f}  "
                  f"Return: {s['ret_pct']:+.2f}%  "
                  f"Open: {s['open']}  Closed: {s['closed']}")

        except KeyboardInterrupt:
            raise
        except Exception as ex:
            # Never let a transient error kill 24/7 operation.
            print(f"\n  âŒ Scan error ({ex.__class__.__name__}): {ex}")

        # Hourly summary
        if time.time() - last_summary >= SUMMARY_EVERY:
            try:
                discord_summary(trader)
            except Exception as ex:
                print(f"  ! Summary send failed: {ex}")
            last_summary = time.time()

        mins = SCAN_INTERVAL // 60
        print(f"\n  Waiting {mins} min ({SCAN_INTERVAL}s)  Â·  Ctrl+C to stop")
        try:
            time.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print("\n\n  Shutting down...")
            try:
                discord_summary(trader)
            except Exception:
                pass
            print("  Done. Goodbye.")
            break


if __name__ == "__main__":
    # Outer guard: if anything truly catastrophic escapes main()
    # (e.g. permanent DNS failure), restart after a pause instead
    # of dying â€” important for unattended Termux / boot use.
    while True:
        try:
            main()
            break   # clean exit (Ctrl+C inside main)
        except KeyboardInterrupt:
            break
        except Exception as ex:
            print(f"\n  ðŸ’¥ Fatal error: {ex.__class__.__name__}: {ex}")
            print("  Restarting in 30s...")
            time.sleep(30)
