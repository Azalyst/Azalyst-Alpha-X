"""
╔═══════════════════════════════════════════════════════════════════╗
║   BB SCANNER  –  INSTITUTIONAL GRADE                             ║
║   Binance Perpetual Futures  |  1m  |  BB(200, SD 1)             ║
║   Paper Trading: 30x Leverage  |  Discord Webhook Alerts         ║
║   Runs on:  Windows / Linux / macOS / Termux (Android)           ║
╚═══════════════════════════════════════════════════════════════════╝

STRATEGY
────────
LONG  – Upper Band Breakout Pullback:
          1. Price closes ABOVE upper BB (breakout)
          2. Price pulls back to TOUCH the upper BB
          3. Price starts going UP again → BUY
          SL: Low of the pullback touch candle

SHORT – Lower Band Breakdown Pullback:
          1. Price closes BELOW lower BB (breakdown)
          2. Price bounces back to TOUCH the lower BB
          3. Price starts going DOWN again → SELL
          SL: High of the bounce touch candle

No trades in the middle band zone.

EXIT (per-trade `extended` flag — survives across any number of scan cycles)
────
LONG  exit → price first extends ABOVE upper band, then re-touches upper band → CLOSE
             (Upper Band Recross is EXIT only — never opens a new SHORT)
SHORT exit → price first extends BELOW lower band, then re-touches lower band → CLOSE
             (Lower Band Recross is EXIT only — never opens a new LONG)
Fallback   → Upper / Lower Bollinger Band — DYNAMIC (live band each scan,
             NOT frozen at entry). Exit fires wherever the band is at the
             moment of the touch.
Stop Loss  → Low (Long) or High (Short) of pullback/bounce touch candle

═══════════════════════════════════════════════════════════════════
 INSTALL  –  PC (Windows / Linux / macOS)
═══════════════════════════════════════════════════════════════════
   pip install pandas numpy requests matplotlib
   python main.py

═══════════════════════════════════════════════════════════════════
 INSTALL  –  TERMUX (Android, runs 24/7 on phone)
═══════════════════════════════════════════════════════════════════
 1. Install Termux from F-Droid  (the Play Store one is broken).
 2. Install Termux:API and Termux:Boot from F-Droid (optional but
    Termux:Boot lets the scanner auto-start when phone reboots).
 3. In Termux:

      pkg update && pkg upgrade -y
      pkg install python git -y
      pip install --upgrade pip
      pip install pandas numpy requests
      # matplotlib is OPTIONAL on Termux. Charts auto-disable if
      # not installed – Discord alerts still fire as text only.

 4. Put main.py somewhere persistent, e.g. ~/scanner/
      mkdir -p ~/scanner && cd ~/scanner
      # copy main.py here (via Termux storage / scp / etc.)

 5. Keep the CPU awake so Android does not freeze the process:
      pkg install termux-api -y
      termux-wake-lock          # release with: termux-wake-unlock

 6. Run:
      python main.py

 7. Want it to survive Termux being closed? Run inside tmux:
      pkg install tmux -y
      tmux new -s scanner
      python main.py
      # detach: Ctrl+B then D     reattach: tmux attach -t scanner

 8. Auto-start on boot (Termux:Boot installed):
      mkdir -p ~/.termux/boot
      cat > ~/.termux/boot/start-scanner <<'EOF'
      #!/data/data/com.termux/files/usr/bin/sh
      termux-wake-lock
      cd ~/scanner
      python main.py >> scanner.log 2>&1
      EOF
      chmod +x ~/.termux/boot/start-scanner
"""

# ─── STDLIB ──────────────────────────────────────────────────────────────────
import io, json, os, sys, time
from datetime import datetime, timezone

# Force UTF-8 stdout so emojis / box chars render cleanly on
# Windows cmd, Termux, and SSH sessions.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ─── THIRD-PARTY (required) ──────────────────────────────────────────────────
import numpy  as np
import pandas as pd
import requests

# ─── matplotlib is OPTIONAL (skip on Termux if it won't install) ─
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

# ═══════════════════════════════════════════════════════════════════
#  ①   USER CONFIG  ←  only section you need to edit
# ═══════════════════════════════════════════════════════════════════
DISCORD_WEBHOOK  = (
    "https://discord.com/api/webhooks/1494071862609575948/"
    "G04AVF9M0nCp0FYPNDgBwyPzUee-9IMQFxr88uH88euQmaD4JM4LbV1cTofMqGqiz3fX"
)

BB_PERIOD        = 200          # Bollinger Band period
BB_SD            = 1            # Standard deviation multiplier
TIMEFRAME        = "1m"
CANDLE_LIMIT     = 320          # must be > BB_PERIOD + 50
SCAN_INTERVAL    = 300          # seconds between full scans (300 = 5 min)
LOOKBACK_WINDOW  = 300          # look back 5 min (300s) to check if conditions matched
REQUEST_DELAY    = 0.15         # seconds between API calls (rate-limit safe)
SWING_LOOKBACK   = 60           # candles back to find swing high / low
TOUCH_TOL        = 0.0025       # 0.25 % – band "touch" tolerance

# ── Spike Detection Window ────────────────────────────────────────────────────
# The signal detection is no longer a rigid 3-candle pattern [-3,-2,-1].
# Instead we look BACK up to 30 candles (30 min on 1m) for a valid breakout
# spike, then allow the pullback + entry confirmation to arrive within a
# 10-candle (10 min) window from that spike.
#
# This captures the chart pattern you showed: spike at 21:00, BB expands,
# price pulls back to band at 21:06 — the scanner would have missed that
# with the old fixed-offset logic.
#
#  BREAKOUT_LOOKBACK  – how far back to search for the spike event
#  ENTRY_WINDOW       – pullback + confirmation must complete within this
#                       many candles of the breakout (hard deadline: if price
#                       hasn't re-touched the band in 10 min the move is over)
BREAKOUT_LOOKBACK = 30          # scan 30 candles back for the spike
ENTRY_WINDOW      = 10          # band touch + confirmation ≤ 10 candles after spike

# Anti-sideways filters
MIN_BREAKOUT_PCT = 0.002        # breakout candle must close at least 0.2% beyond the band
                                # tiny pokes above/below don't count as real breakouts
MIN_BANDWIDTH_PCT = 0.008       # ignore setups when BB width < 0.8% of price
                                # narrow bands = sideways / squeeze → no trade

# ── Multi-Timeframe RSI Filter ────────────────────────────────────────────────
# Inspired by CoinGlass RSI Heatmap: only trade symbols where higher-timeframe
# RSI aligns with the signal direction.  When RSI(1h) AND RSI(4h) are both
# overbought/oversold, the momentum is GENUINE across multiple candle periods —
# not just 1m noise triggering the BB band.
#
#  LONG  entry requires: RSI(1h) >= RSI_LONG_1H  AND  RSI(4h) >= RSI_LONG_4H
#  SHORT entry requires: RSI(1h) <= RSI_SHORT_1H AND  RSI(4h) <= RSI_SHORT_4H
#
# These thresholds deliberately sit in the "clearly trending" zone, not the
# borderline 50 area, so we only enter when momentum is unambiguous.
RSI_PERIOD       = 14           # standard Wilder 14-period RSI
RSI_LONG_1H      = 60           # 1h RSI must be ≥ this for LONG  (bullish momentum)
RSI_LONG_4H      = 55           # 4h RSI must be ≥ this for LONG  (confirmed uptrend)
RSI_SHORT_1H     = 40           # 1h RSI must be ≤ this for SHORT (bearish momentum)
RSI_SHORT_4H     = 45           # 4h RSI must be ≤ this for SHORT (confirmed downtrend)

# ── Trend Stage Detection ─────────────────────────────────────────────────────
# Classifies each signal as EARLY / MID / LATE so you can prioritise entries.
#
#  EARLY  →  4h RSI just building (50–68). Price has not run yet. Best R:R.
#  MID    →  4h RSI in momentum zone (68–80). Trend confirmed, still valid.
#  LATE   →  4h RSI extended (> 80). Like SKL at 90+. Trend already ran → skip.
#
# The VOLUME_SURGE_MULT requires the signal candle's volume to be at least
# this multiple of the 20-candle rolling average. Institutions accumulating
# before a trend always leave a volume fingerprint first.
#
# RSI_VELOCITY_MIN is the minimum 3-candle RSI change on the 4h chart to
# qualify as "accelerating". A flat RSI at 60 is very different from one
# that jumped from 50→60 in 3 candles — the latter is a trend starter.
TREND_STAGE_MID_4H   = 68       # 4h RSI above this → MID stage
TREND_STAGE_LATE_4H  = 80       # 4h RSI above this → LATE (skip by default)
SKIP_LATE_STAGE      = True     # set False to trade LATE-stage signals anyway
VOLUME_SURGE_MULT    = 1.5      # signal candle volume ≥ 1.5× 20-candle avg
VOLUME_LOOKBACK      = 20       # candles for volume average
RSI_VELOCITY_MIN     = 4.0      # 4h RSI must have risen ≥ 4 pts in last 3 candles
                                # (LONG) or fallen ≥ 4 pts (SHORT)

# Paper trading
INITIAL_BALANCE  = 10_000.0     # starting virtual USDT
LEVERAGE         = 30           # leverage multiplier
RISK_PCT         = 0.02         # 2 % account risk per trade
MAX_MARGIN_PCT   = 0.25         # never use > 25 % of balance as margin per trade
SIGNAL_COOLDOWN  = 300          # seconds before same symbol can fire again
SUMMARY_EVERY    = 3600         # seconds between Discord portfolio summaries

# Risk / position guards
MAX_OPEN_TRADES  = 5            # never hold more than this many positions at once.
                                # Prevents a bad scan from opening 10 positions that
                                # all hit SL in the same update cycle.

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

# ═══════════════════════════════════════════════════════════════════
#  ②  EXCHANGE  –  direct REST (bypasses ccxt load_markets which
#                  also hits dapi.binance.com coin-futures and
#                  times-out in regions where that endpoint is blocked)
# ═══════════════════════════════════════════════════════════════════
FAPI_BASE = "https://fapi.binance.com"      # USDT-margined perpetuals only

_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})
_SESSION.headers.update({"User-Agent": "DiscordBot/1.0"})  # Better Cloudflare handling

# ═══════════════════════════════════════════════════════════════════
#  ③  SIGNAL COOLDOWN & VALIDATION
# ═══════════════════════════════════════════════════════════════════
_last_signal: dict[str, float] = {}   # symbol → epoch
_signal_cache: dict[str, dict] = {}  # symbol → {signal, timestamp, entry_price}

def on_cooldown(sym: str) -> bool:
    return (time.time() - _last_signal.get(sym, 0)) < SIGNAL_COOLDOWN

def mark_cooldown(sym: str):
    _last_signal[sym] = time.time()

# Signal validation: only execute if condition is FRESH (within 1 min) AND price hasn't moved >2%
SIGNAL_FRESHNESS = 60   # 1 minute max age for a signal
SIGNAL_SLIPPAGE_PCT = 0.02  # Allow 2% price movement before rejecting signal

def is_signal_valid(sym: str, current_price: float) -> bool:
    """Check if cached signal is still valid (fresh + price hasn't slipped too much)."""
    if sym not in _signal_cache:
        return False
    
    cached = _signal_cache[sym]
    age = time.time() - cached["timestamp"]
    
    # ①  Signal must be fresh (< 1 min old)
    if age > SIGNAL_FRESHNESS:
        print(f"    [REJECT] {sym}: Signal too old ({age:.0f}s > {SIGNAL_FRESHNESS}s)")
        return False
    
    # ②  Entry price must not have slipped too far (>2%)
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

# ═══════════════════════════════════════════════════════════════════
#  ④  DATA
# ═══════════════════════════════════════════════════════════════════
def get_symbols() -> list[str]:
    """
    Fetch all active USDT-margined perpetual symbols directly from
    fapi.binance.com/fapi/v1/exchangeInfo – no dapi.binance.com call,
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
    """BTC/USDT  →  BTCUSDT  (fapi endpoint format)"""
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

# ═══════════════════════════════════════════════════════════════════
#  ⑤  INDICATORS
# ═══════════════════════════════════════════════════════════════════
def add_bb(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["mid"]   = df["close"].rolling(BB_PERIOD).mean()
    df["std"]   = df["close"].rolling(BB_PERIOD).std(ddof=0)
    df["upper"] = df["mid"] + BB_SD * df["std"]
    df["lower"] = df["mid"] - BB_SD * df["std"]
    return df.dropna().reset_index(drop=True)

def calc_rsi(closes: pd.Series, period: int = RSI_PERIOD) -> float:
    """
    Wilder's smoothed RSI.  Returns the most recent RSI value (0–100),
    or 50.0 if there is insufficient data (neutral — won't block either way).
    """
    if len(closes) < period + 1:
        return 50.0
    delta  = closes.diff().dropna()
    gain   = delta.clip(lower=0)
    loss   = (-delta).clip(lower=0)
    # Wilder smoothing = exponential with alpha = 1/period
    avg_g  = gain.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    avg_l  = loss.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - (100 / (1 + rs)), 2)

def fetch_mtf_rsi(symbol: str) -> dict:
    """
    Fetch RSI + RSI velocity + volume data for 1h and 4h timeframes.
    Only called AFTER a BB signal fires — 2 extra API calls per real candidate.

    Returns dict with:
      rsi_1h        – current RSI on 1h
      rsi_4h        – current RSI on 4h
      rsi_4h_prev3  – 4h RSI three candles ago  (used for velocity)
      vol_ratio     – signal-candle volume / 20-candle avg (from 1m df passed in)
    Falls back to neutral values (50 / 1.0) on fetch errors.
    """
    result = {"rsi_1h": 50.0, "rsi_4h": 50.0, "rsi_4h_prev3": 50.0}
    for tf, rsi_key, prev_key in [
        ("1h", "rsi_1h",  None),
        ("4h", "rsi_4h",  "rsi_4h_prev3"),
    ]:
        try:
            # Fetch enough candles for RSI + 3 velocity candles
            limit = RSI_PERIOD * 3 + 5
            params = {
                "symbol":   _raw_symbol(symbol),
                "interval": tf,
                "limit":    limit,
            }
            resp = _SESSION.get(f"{FAPI_BASE}/fapi/v1/klines",
                                params=params, timeout=10)
            resp.raise_for_status()
            raw    = resp.json()
            closes = pd.Series([float(c[4]) for c in raw])
            result[rsi_key] = calc_rsi(closes)
            if prev_key:
                # RSI 3 candles ago — drop last 3 closes and recompute
                result[prev_key] = calc_rsi(closes.iloc[:-3])
        except Exception as ex:
            print(f"    [WARN] RSI fetch failed for {symbol} {tf}: {ex}")
    return result


def score_trend(symbol: str, direction: str, df_1m: pd.DataFrame) -> dict:
    """
    Full trend intelligence engine.  Returns a result dict:

      passed   – bool  : whether the signal should be traded at all
      stage    – str   : "EARLY" / "MID" / "LATE"
      score    – int   : 0–100 composite conviction score
      rsi_1h   – float
      rsi_4h   – float
      velocity – float : 4h RSI change over last 3 candles
      vol_ratio– float : signal-candle volume vs 20-candle avg
      reason   – str   : human-readable verdict for Discord / console

    ── STAGE LOGIC ──────────────────────────────────────────────────────
    EARLY  →  4h RSI 50–68  (just building, price hasn't run yet)
              RSI velocity > RSI_VELOCITY_MIN  (momentum accelerating)
              This is "before the trend sets" — the sweet spot.

    MID    →  4h RSI 68–80  (trend confirmed, still room to run)
              Velocity may be slowing but direction is clear.

    LATE   →  4h RSI > 80   (like SKL at 90+ in the heatmap — already ran)
              If SKIP_LATE_STAGE=True these are rejected.

    ── SCORE COMPONENTS (total 100) ─────────────────────────────────────
    RSI alignment  (0–30)  : both 1h and 4h aligned with direction
    Stage bonus    (0–25)  : EARLY=25, MID=15, LATE=0
    RSI velocity   (0–25)  : 4h RSI accelerating → trend just starting
    Volume surge   (0–20)  : big volume on signal candle = institutional move
    """
    mtf = fetch_mtf_rsi(symbol)
    r1h      = mtf["rsi_1h"]
    r4h      = mtf["rsi_4h"]
    r4h_prev = mtf["rsi_4h_prev3"]

    # ── Volume ratio from the 1m df (already fetched, no extra API call) ──────
    try:
        vol_avg   = float(df_1m["volume"].iloc[-VOLUME_LOOKBACK-1:-1].mean())
        vol_now   = float(df_1m["volume"].iloc[-1])
        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0
    except Exception:
        vol_ratio = 1.0

    # ── RSI velocity (how fast 4h RSI changed in last 3 candles) ─────────────
    velocity = r4h - r4h_prev   # positive = rising, negative = falling

    # ── Stage classification ──────────────────────────────────────────────────
    if direction == "LONG":
        rsi_check_pass = (r1h >= RSI_LONG_1H) and (r4h >= RSI_LONG_4H)
        is_late        = r4h > TREND_STAGE_LATE_4H
        is_mid         = r4h > TREND_STAGE_MID_4H
        vel_ok         = velocity >= RSI_VELOCITY_MIN
    else:  # SHORT
        rsi_check_pass = (r1h <= RSI_SHORT_1H) and (r4h <= RSI_SHORT_4H)
        is_late        = r4h < (100 - TREND_STAGE_LATE_4H)   # mirror: < 20
        is_mid         = r4h < (100 - TREND_STAGE_MID_4H)    # mirror: < 32
        vel_ok         = velocity <= -RSI_VELOCITY_MIN        # falling fast

    if is_late:
        stage = "LATE"
    elif is_mid:
        stage = "MID"
    else:
        stage = "EARLY"

    # ── Composite score ───────────────────────────────────────────────────────
    # 1. RSI alignment (0–30)
    if direction == "LONG":
        rsi_pts  = min(30, int((r1h - 50) / 50 * 30) + int((r4h - 50) / 50 * 30)) // 2
    else:
        rsi_pts  = min(30, int((50 - r1h) / 50 * 30) + int((50 - r4h) / 50 * 30)) // 2
    rsi_pts = max(0, rsi_pts)

    # 2. Stage bonus (0–25)
    stage_pts = {"EARLY": 25, "MID": 15, "LATE": 0}[stage]

    # 3. RSI velocity (0–25) — capped at 15-point swing = full marks
    if direction == "LONG":
        vel_pts = min(25, int(max(0, velocity) / 15 * 25))
    else:
        vel_pts = min(25, int(max(0, -velocity) / 15 * 25))

    # 4. Volume surge (0–20)
    vol_pts = min(20, int((vol_ratio - 1.0) / (VOLUME_SURGE_MULT - 1.0) * 20))
    vol_pts = max(0, vol_pts)

    score = rsi_pts + stage_pts + vel_pts + vol_pts

    # ── Decision ─────────────────────────────────────────────────────────────
    passed = (
        rsi_check_pass
        and (not SKIP_LATE_STAGE or stage != "LATE")
        and vol_ratio >= VOLUME_SURGE_MULT
    )

    # ── Human-readable summary ────────────────────────────────────────────────
    vol_flag  = "🔥" if vol_ratio >= VOLUME_SURGE_MULT * 1.5 else ("✅" if vol_ratio >= VOLUME_SURGE_MULT else "❌")
    vel_flag  = "🚀" if abs(velocity) >= RSI_VELOCITY_MIN * 2 else ("✅" if vel_ok else "〰️")
    stage_icon = {"EARLY": "🌱", "MID": "📈", "LATE": "⚠️"}[stage]

    reason = (
        f"{stage_icon}{stage}  Score={score}/100  |  "
        f"RSI 1h={r1h:.1f}  4h={r4h:.1f}  vel={velocity:+.1f}{vel_flag}  |  "
        f"Vol={vol_ratio:.1f}x{vol_flag}"
    )

    verdict = "✅ TRADE" if passed else "❌ SKIP"
    print(f"    [TREND] {symbol} {direction} | {reason}  → {verdict}")

    return {
        "passed":    passed,
        "stage":     stage,
        "score":     score,
        "rsi_1h":    r1h,
        "rsi_4h":    r4h,
        "velocity":  round(velocity, 2),
        "vol_ratio": round(vol_ratio, 2),
        "reason":    reason,
    }


def passes_rsi_filter(symbol: str, direction: str, df_1m: pd.DataFrame = None) -> tuple[bool, dict]:
    """
    Wrapper kept for backwards-compat.  Now delegates to score_trend().
    Returns (passed: bool, trend_info: dict).
    """
    if df_1m is None:
        # Fallback: basic RSI check only (no volume, no stage)
        mtf = fetch_mtf_rsi(symbol)
        r1h, r4h = mtf["rsi_1h"], mtf["rsi_4h"]
        if direction == "LONG":
            ok = (r1h >= RSI_LONG_1H) and (r4h >= RSI_LONG_4H)
        else:
            ok = (r1h <= RSI_SHORT_1H) and (r4h <= RSI_SHORT_4H)
        return ok, {"stage": "UNKNOWN", "score": 0, "rsi_1h": r1h, "rsi_4h": r4h,
                    "velocity": 0, "vol_ratio": 1.0, "reason": "fallback"}
    info = score_trend(symbol, direction, df_1m)
    return info["passed"], info

def sw_high(df: pd.DataFrame) -> float:
    return float(df.iloc[-(SWING_LOOKBACK + 1):-1]["high"].max())

def sw_low(df: pd.DataFrame) -> float:
    return float(df.iloc[-(SWING_LOOKBACK + 1):-1]["low"].min())

# ═══════════════════════════════════════════════════════════════════
#  ⑥  SIGNAL DETECTION
# ═══════════════════════════════════════════════════════════════════
def _build(direction, condition, entry, sl):
    return {"direction": direction, "condition": condition,
            "entry": round(float(entry), 8), "sl": round(float(sl), 8)}

# ── Band Touch Momentum Logic ──────────────────────────────────────────────────
#
#  ⚠️  ENTRY / EXIT SEPARATION — READ CAREFULLY
#  ─────────────────────────────────────────────
#  "Lower Band Recross"  (price dips below lower band → closes back above)
#       → ONLY used to EXIT an open SHORT position.  NEVER opens a new LONG.
#
#  "Upper Band Recross"  (price spikes above upper band → closes back below)
#       → ONLY used to EXIT an open LONG position.   NEVER opens a new SHORT.
#
#  New positions are opened ONLY by:
#       long_band_touch   – upper-band breakout/pullback → BUY
#       short_band_touch  – lower-band breakdown/pullback → SELL
#
#  Exit detection lives in PaperTrader.update() using a per-trade `extended`
#  flag that survives across many scan cycles correctly.
# ──────────────────────────────────────────────────────────────────────────────
def long_band_touch(df) -> dict | None:
    """Upper Band Breakout → Pullback → BUY  (new LONG entry only)
    ─────────────────────────────────────────────────────────────────
    Sliding-window search — no longer a rigid [-3,-2,-1] 3-candle check.

    Step 1 – Spike/Breakout  : scan back up to BREAKOUT_LOOKBACK (30) candles
                               for any candle that closed meaningfully above
                               the upper BB.  Takes the MOST RECENT valid one.

    Step 2 – Entry window    : the breakout must be within ENTRY_WINDOW (10)
                               candles of the current (confirmation) candle.
                               If the spike was >10 min ago the move is over —
                               skip it.  (30-min lookback is for detection only.)

    Step 3 – Pullback touch  : somewhere BETWEEN the breakout and current,
                               there must be a candle whose low wicked into
                               the upper band while its high was still above
                               it (body above, wick touches — classic retest).

    Step 4 – Confirmation    : current candle closes ABOVE the pullback close
                               (momentum resumed upward).

    SL : low of the pullback/touch candle (unchanged from original logic).
    """
    n = len(df)
    if n < BB_PERIOD + BREAKOUT_LOOKBACK + 2:
        return None

    current = df.iloc[-1]

    # ── Anti-sideways filter ① : bandwidth too narrow → skip ──────────
    bandwidth_pct = (current["upper"] - current["lower"]) / current["mid"]
    if bandwidth_pct < MIN_BANDWIDTH_PCT:
        return None

    # ── Anti-sideways filter ③ : current price must be above middle band ─
    if current["close"] < current["mid"]:
        return None

    # ── Step 1+2 : find the most recent valid breakout within window ───────
    breakout     = None
    breakout_pos = None   # how many candles ago (relative to current = iloc[-1])

    for offset in range(2, min(BREAKOUT_LOOKBACK + 1, n - 1)):
        candidate = df.iloc[-1 - offset]

        # Must have closed above the upper band
        if candidate["close"] <= candidate["upper"]:
            continue
        # Breakout must be meaningful (≥ MIN_BREAKOUT_PCT beyond band)
        bd = (candidate["close"] - candidate["upper"]) / candidate["upper"]
        if bd < MIN_BREAKOUT_PCT:
            continue

        # Found the most recent valid breakout
        breakout     = candidate
        breakout_pos = offset
        break   # stop at the most recent one

    if breakout is None:
        return None

    # ── Step 2 : entry-window gate — spike must be ≤ ENTRY_WINDOW candles ago ─
    if breakout_pos > ENTRY_WINDOW:
        # Spike was detected but is stale (> 10 min old).
        # Log it so you can see why it was skipped, then bail.
        return None

    # ── Step 3 : find a valid pullback touch between breakout and current ──────
    # Search from the candle just before current back toward (but not including)
    # the breakout itself.  We want the MOST RECENT valid pullback.
    for pb_offset in range(1, breakout_pos):
        pullback = df.iloc[-1 - pb_offset]
        tol = pullback["upper"] * TOUCH_TOL

        touched = (
            pullback["low"]   <= pullback["upper"] + tol  # wick reaches band
            and pullback["high"] >= pullback["upper"]      # body still above band
            and pullback["close"] < breakout["close"]      # price retracing
        )
        if not touched:
            continue

        # ── Step 4 : confirmation – current closes above pullback ─────────────
        if current["close"] <= pullback["close"]:
            continue   # no momentum yet — wait for a better candle

        # ── All conditions met ────────────────────────────────────────────────
        candles_since = breakout_pos   # for debug logging
        print(f"    [SIGNAL] LONG pattern: breakout={candles_since}c ago  "
              f"pullback={pb_offset}c ago  entry={current['close']:.8g}  "
              f"sl={pullback['low']:.8g}")
        return _build("LONG", "Upper Band Breakout Pullback",
                      current["close"], pullback["low"])

    return None


def short_band_touch(df) -> dict | None:
    """Lower Band Breakdown → Bounce → SELL  (new SHORT entry only)
    ─────────────────────────────────────────────────────────────────
    Mirror of long_band_touch.  Sliding-window search:

    Step 1 – Spike/Breakdown : scan back up to BREAKOUT_LOOKBACK candles for
                               a candle that closed meaningfully BELOW the lower BB.
    Step 2 – Entry window    : breakdown must be ≤ ENTRY_WINDOW (10) candles ago.
    Step 3 – Bounce touch    : a candle between breakdown and current whose HIGH
                               wicked into the lower band while its LOW was still
                               below it (classic retest from below).
    Step 4 – Confirmation    : current closes BELOW the bounce close.

    SL : high of the bounce/touch candle.
    """
    n = len(df)
    if n < BB_PERIOD + BREAKOUT_LOOKBACK + 2:
        return None

    current = df.iloc[-1]

    # ── Anti-sideways filters ─────────────────────────────────────────────────
    bandwidth_pct = (current["upper"] - current["lower"]) / current["mid"]
    if bandwidth_pct < MIN_BANDWIDTH_PCT:
        return None
    if current["close"] > current["mid"]:
        return None   # price bounced back into middle zone → skip

    # ── Step 1+2 : find the most recent valid breakdown within window ──────────
    breakdown     = None
    breakdown_pos = None

    for offset in range(2, min(BREAKOUT_LOOKBACK + 1, n - 1)):
        candidate = df.iloc[-1 - offset]

        if candidate["close"] >= candidate["lower"]:
            continue
        bd = (candidate["lower"] - candidate["close"]) / candidate["lower"]
        if bd < MIN_BREAKOUT_PCT:
            continue

        breakdown     = candidate
        breakdown_pos = offset
        break

    if breakdown is None:
        return None

    if breakdown_pos > ENTRY_WINDOW:
        return None   # spike too old, move is over

    # ── Step 3 : find a valid bounce touch between breakdown and current ────────
    for pb_offset in range(1, breakdown_pos):
        bounce = df.iloc[-1 - pb_offset]
        tol = abs(bounce["lower"]) * TOUCH_TOL

        touched = (
            bounce["high"] >= bounce["lower"] - tol   # wick reaches band
            and bounce["low"] <= bounce["lower"]       # body still below band
            and bounce["close"] > breakdown["close"]   # price retracing upward
        )
        if not touched:
            continue

        # ── Step 4 : confirmation ────────────────────────────────────────────
        if current["close"] >= bounce["close"]:
            continue   # no downward momentum yet

        print(f"    [SIGNAL] SHORT pattern: breakdown={breakdown_pos}c ago  "
              f"bounce={pb_offset}c ago  entry={current['close']:.8g}  "
              f"sl={bounce['high']:.8g}")
        return _build("SHORT", "Lower Band Breakdown Pullback",
                      current["close"], bounce["high"])

    return None

CHECKERS = [long_band_touch, short_band_touch]

# ── Targets ───────────────────────────────────────────────────────────────────
#
#  IMPORTANT — WHAT IS FIXED AT ENTRY vs WHAT IS DYNAMIC
#  ──────────────────────────────────────────────────────
#  FIXED at entry time (these never change after trade is opened):
#     • SL          – low of pullback candle (LONG) / high of bounce candle (SHORT)
#     • TP1 / TP2   – Fibonacci 1.272 / 1.618 extensions of recent swing range
#
#  DYNAMIC (recomputed every scan from the LIVE upper / lower band):
#     • BB-touch exit – handled in PaperTrader.update() using cur["upper"]
#                       / cur["lower"] of the latest candle — never frozen.
#
#  `bb_at_entry` below is only a REFERENCE SNAPSHOT of where the band was when
#  the trade opened. It is NOT used as an exit level. The real exit happens at
#  whatever the band is at the moment of the touch in some future scan cycle.
# ──────────────────────────────────────────────────────────────────────────────
def build_targets(df: pd.DataFrame, sig: dict) -> dict:
    e  = sig["entry"]
    sl = sig["sl"]
    d  = sig["direction"]
    sh, sl_ = sw_high(df), sw_low(df)
    move = sh - sl_

    if d == "LONG":
        t1 = round(e + move * 1.272, 8)
        t2 = round(e + move * 1.618, 8)
        bb_ref = round(float(df.iloc[-1]["upper"]), 8)   # reference only
        return {
            "tp1": t1 if t1 > e else None,
            "tp2": t2 if t2 > e else None,
            "bb_at_entry": bb_ref,       # display reference, NOT an exit level
            "swing_high": round(sh, 8),
            "swing_low":  round(sl_, 8),
            # Timestamp of the entry candle — used to gate the extended flag.
            # Stored as a string; update() converts back to Timestamp for comparison.
            "entry_candle_time": str(df.iloc[-1]["time"]),
        }
    else:
        t1 = round(e - move * 1.272, 8)
        t2 = round(e - move * 1.618, 8)
        bb_ref = round(float(df.iloc[-1]["lower"]), 8)   # reference only
        return {
            "tp1": t1 if t1 < e else None,
            "tp2": t2 if t2 < e else None,
            "bb_at_entry": bb_ref,       # display reference, NOT an exit level
            "swing_high": round(sh, 8),
            "swing_low":  round(sl_, 8),
            # Timestamp of the entry candle — used to gate the extended flag.
            "entry_candle_time": str(df.iloc[-1]["time"]),
        }

# ═══════════════════════════════════════════════════════════════════
#  ⑦  PAPER TRADER
# ═══════════════════════════════════════════════════════════════════
class PaperTrader:

    def __init__(self):
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────
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

    # ── open ─────────────────────────────────────────────────────────────────
    def open_trade(self, symbol: str, sig: dict, targets: dict) -> dict | None:
        e  = sig["entry"]
        sl = sig["sl"]
        sl_pct = abs(e - sl) / e
        if sl_pct < 0.0001:
            return None

        # ── Guard ①: Too many open positions → wait ──────────────────────────
        if len(self.open_trades) >= MAX_OPEN_TRADES:
            print(f"    [SKIP] {symbol}: max open trades reached "
                  f"({len(self.open_trades)}/{MAX_OPEN_TRADES})")
            return None

        # ── Guard ②: Symbol already has an open trade → skip ─────────────────
        existing_syms = {t["symbol"] for t in self.open_trades}
        if symbol in existing_syms:
            print(f"    [SKIP] {symbol}: already has an open trade")
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
            # BB snapshot at entry — REFERENCE ONLY for charts / alerts.
            # The actual BB-touch exit is DYNAMIC, evaluated live every scan
            # cycle against the current upper / lower band in update().
            "bb_at_entry": targets["bb_at_entry"],
            "notional":  round(notional, 4),
            "margin":    round(margin,   4),
            "leverage":  LEVERAGE,
            "qty":       round(notional / e, 6),
            "open_time": datetime.now(timezone.utc).isoformat(),
            # ── entry candle timestamp – gates the `extended` flag in update() ─
            # Prevents the very first post-entry update() call from immediately
            # setting extended=True (and firing an exit on the same candle).
            "entry_candle_time": targets.get("entry_candle_time"),
            "status":    "OPEN",
            "upnl":      0.0,
            # ── Band-touch exit tracking ──────────────────────────────────────
            # `extended` becomes True the FIRST time price moves beyond the
            # Bollinger Band AFTER entry.  The exit fires on the NEXT touch of
            # that same band (Upper for LONG, Lower for SHORT).
            # This flag survives across many scan cycles correctly.
            "extended":     False,
            # Live BB value at the moment the band-touch exit fires.
            # Populated in update(). None means exit did not trigger via band.
            "exit_bb_level": None,
        }
        self.open_trades.append(trade)
        self._save()
        return trade

    # ── mark-to-market & auto-close ──────────────────────────────────────────
    def update(self, prices: dict, df_dict: dict = None) -> list[dict]:
        """Update trades and check for band-touch exits.
        
        Args:
            prices: Current prices by symbol
            df_dict: Optional dict of DataFrames by symbol for band-touch exit logic
        """
        still_open, closed = [], []

        for t in self.open_trades:
            px = prices.get(t["symbol"])
            # BUG FIX: prices[sym] was set ~45s earlier in the signal-scan loop.
            # By the time update() runs, df_dict has a fresher fetch of the same
            # symbol.  Use its last-close as px so SL / band-touch exits fire at
            # the same price that was used for the band check — not a stale one.
            if df_dict and t["symbol"] in df_dict:
                px = float(df_dict[t["symbol"]].iloc[-1]["close"])
            if px is None:
                still_open.append(t)
                continue

            d  = t["direction"]
            cp = cr = None                          # close_price, close_reason

            # ── Band-touch exit (FIRST) ───────────────────────────────────────
            #
            #  LONG  exit rule : price must first EXTEND above the upper band
            #                    (t["extended"] = True), then on the NEXT time
            #                    it touches/crosses back to the upper band → EXIT.
            #
            #  SHORT exit rule : price must first EXTEND below the lower band
            #                    (t["extended"] = True), then on the NEXT time
            #                    it touches/crosses back to the lower band → EXIT.
            #
            if cp is None and df_dict and t["symbol"] in df_dict:
                df  = df_dict[t["symbol"]]
                if len(df) >= 2:
                    cur  = df.iloc[-1]
                    prev = df.iloc[-2]

                    upper = cur["upper"]
                    lower = cur["lower"]
                    tol_u = upper * TOUCH_TOL
                    tol_l = abs(lower) * TOUCH_TOL

                    if d == "LONG":
                        if not t["extended"]:
                            entry_ct = t.get("entry_candle_time")
                            if entry_ct:
                                entry_ts = pd.Timestamp(entry_ct)
                                cur_is_new  = cur["time"]  > entry_ts
                                prev_is_new = prev["time"] > entry_ts
                            else:
                                cur_is_new = prev_is_new = True
                            if (cur_is_new and cur["high"] > upper) or (prev_is_new and prev["high"] > upper):
                                t["extended"] = True
                                print(f"    [EXTEND] {t['id']} {t['symbol']} "
                                      f"LONG extended above upper band")

                        elif t["extended"]:
                            touching = (
                                cur["high"] >= upper - tol_u
                                and cur["low"]  <= upper + tol_u
                                and cur["close"] >= upper - tol_u
                            )
                            if touching:
                                cp, cr = px, "Upper Band Touch Exit ✅"
                                t["exit_bb_level"] = round(float(upper), 8)

                    elif d == "SHORT":
                        if not t["extended"]:
                            entry_ct = t.get("entry_candle_time")
                            if entry_ct:
                                entry_ts = pd.Timestamp(entry_ct)
                                cur_is_new  = cur["time"]  > entry_ts
                                prev_is_new = prev["time"] > entry_ts
                            else:
                                cur_is_new = prev_is_new = True
                            if (cur_is_new and cur["low"] < lower) or (prev_is_new and prev["low"] < lower):
                                t["extended"] = True
                                print(f"    [EXTEND] {t['id']} {t['symbol']} "
                                      f"SHORT extended below lower band")

                        elif t["extended"]:
                            touching = (
                                cur["low"]  <= lower + tol_l
                                and cur["high"] >= lower - tol_l
                                and cur["close"] <= lower + tol_l
                            )
                            if touching:
                                cp, cr = px, "Lower Band Touch Exit ✅"
                                t["exit_bb_level"] = round(float(lower), 8)

            # ── Stop-Loss check ───────────────────────────────────────────────
            if cp is None:
                if d == "LONG"  and px <= t["sl"]:
                    cp, cr = t["sl"], "SL ❌ Stop Loss"
                elif d == "SHORT" and px >= t["sl"]:
                    cp, cr = t["sl"], "SL ❌ Stop Loss"
            if cp is None:
                if d == "LONG":
                    if   t["tp2"] and px >= t["tp2"]:             cp, cr = t["tp2"], "TP2 ✅ Fib 1.618"
                    elif t["tp1"] and px >= t["tp1"]:             cp, cr = t["tp1"], "TP1 ✅ Fib 1.272"
                    else: t["upnl"] = round((px - t["entry"]) / t["entry"] * t["notional"], 4)
                else:
                    if   t["tp2"] and px <= t["tp2"]:             cp, cr = t["tp2"], "TP2 ✅ Fib 1.618"
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

    # ── stats ─────────────────────────────────────────────────────────────────
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

# ═══════════════════════════════════════════════════════════════════
#  ⑧  CHART  (dark theme, professional)
# ═══════════════════════════════════════════════════════════════════
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

    # ── Bollinger Bands ──────────────────────────────────────────────────────
    ax.fill_between(xs, plot["upper"], plot["lower"],
                    color=BB_CLR, alpha=0.06, zorder=1)
    ax.plot(xs, plot["upper"], color=BB_CLR, lw=1.3, label=f"Upper BB", zorder=2)
    ax.plot(xs, plot["mid"],   color=MID_CLR, lw=1.3, label="SMA 200",   zorder=2)
    ax.plot(xs, plot["lower"], color=BB_CLR, lw=1.0, ls="--",
            label="Lower BB", alpha=0.8, zorder=2)

    # ── Candles ───────────────────────────────────────────────────────────────
    for i, row in plot.iterrows():
        col = BULL if row["close"] >= row["open"] else BEAR
        ax.plot([i, i], [row["low"], row["high"]], color=col, lw=0.9, zorder=3)
        ax.bar(i, abs(row["close"] - row["open"]),
               bottom=min(row["open"], row["close"]),
               color=col, width=0.7, zorder=4, alpha=0.95)

    # ── Volume ────────────────────────────────────────────────────────────────
    vcols = [BULL if plot.iloc[i]["close"] >= plot.iloc[i]["open"] else BEAR
             for i in range(n)]
    axv.bar(xs, plot["volume"], color=vcols, alpha=0.65, width=0.7)
    axv.set_ylabel("Volume", color=FG, fontsize=8)

    # ── Signal marker ─────────────────────────────────────────────────────────
    si = n - 2
    is_long = d == "LONG"
    y0 = plot.iloc[si]["low"]  * 0.9965 if is_long else plot.iloc[si]["high"] * 1.0035
    ytext = y0 * 0.993 if is_long else y0 * 1.007
    lbl   = "▲  LONG"  if is_long else "▼  SHORT"
    mcol  = "#22c55e"  if is_long else "#ef4444"
    ax.annotate(
        lbl, xy=(si, y0), xytext=(si, ytext),
        color=mcol, fontsize=9.5, fontweight="bold", ha="center",
        va="top" if is_long else "bottom",
        arrowprops=dict(arrowstyle="-|>", color=mcol, lw=1.4),
        zorder=10,
    )

    # ── Level lines ───────────────────────────────────────────────────────────
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
    # NOTE: the BB-touch exit is DYNAMIC — it's whatever the upper / lower
    # band curve is at the moment of the touch in some future scan. We do NOT
    # draw a frozen horizontal fallback line here because that would be
    # misleading. The live Bollinger Band curves above already show the
    # exit level as it evolves each candle.

    # ── X axis labels ─────────────────────────────────────────────────────────
    step = max(1, n // 10)
    plt.setp(ax.get_xticklabels(), visible=False)
    axv.set_xticks(range(0, n, step))
    axv.set_xticklabels(
        [plot.iloc[i]["time"].strftime("%d %b\n%H:%M") for i in range(0, n, step)],
        fontsize=7, color=FG
    )

    # ── Legend & Title ────────────────────────────────────────────────────────
    ax.legend(loc="upper left", facecolor="#161b22", labelcolor=FG,
              fontsize=8.5, framealpha=0.9, edgecolor=GRID)
    fig.suptitle(
        f"  {symbol}   ·   BB({BB_PERIOD}, {BB_SD})   ·   {TIMEFRAME}   ·   {sig['condition']}",
        color=WHITE, fontsize=12, fontweight="bold", x=0.01, ha="left", y=0.99
    )

    # tight_layout is incompatible with GridSpec + sharex axes – use subplots_adjust instead
    fig.subplots_adjust(left=0.03, right=0.88, top=0.96, bottom=0.07, hspace=0.03)
    buf = io.BytesIO()
    # Save without bbox_inches to avoid conflicts with subplots_adjust
    plt.savefig(buf, format="png", dpi=75, facecolor=BG, edgecolor="none", pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    return buf.read()

# ═══════════════════════════════════════════════════════════════════
#  ⑨  DISCORD  –  institutional monospace style, no emojis
# ═══════════════════════════════════════════════════════════════════
_SEP  = "─" * 44        # section divider inside code blocks
_W    = 18              # label column width for alignment

def _kv(label: str, value: str) -> str:
    """Left-aligned key : value row, fixed label width."""
    return f"{label:<{_W}}: {value}"

def _rr(entry, target, sl) -> str:
    risk = abs(entry - sl)
    if not risk or target is None:
        return "—"
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
        "title": f"📊 {sig['direction']} {pair} | {sig['condition']}",
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
            print(f"  ✅ Chart sent successfully to Discord")
        else:
            print(f"  ! Chart upload returned HTTP {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
    except Exception as ex:
        print(f"  ! Chart send error ({ex.__class__.__name__}): {ex}")


def discord_signal_with_chart(symbol: str, sig: dict, tgt: dict,
                               trade: dict, stats: dict, chart_bytes: bytes | None):
    """NEW SIGNAL alert – detailed trade card + standalone chart."""
    d        = sig["direction"]
    is_long  = d == "LONG"
    color    = 0x22c55e if is_long else 0xef4444
    e, sl    = sig["entry"], sig["sl"]
    rsk_pct  = abs(e - sl) / e * 100
    tp1_str  = str(tgt.get("tp1") or "—")
    tp2_str  = str(tgt.get("tp2") or "—")
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
    bb_ref      = tgt["bb_at_entry"]
    bb_label    = "Upper BB" if is_long else "Lower BB"

    # ── Trend Intelligence block (new) ──────────────────────────────────────
    stage      = sig.get("trend_stage",  "?")
    score      = sig.get("trend_score",   0)
    rsi_1h_v   = sig.get("rsi_1h",      50.0)
    rsi_4h_v   = sig.get("rsi_4h",      50.0)
    rsi_vel_v  = sig.get("rsi_vel",      0.0)
    vol_rat_v  = sig.get("vol_ratio",    1.0)
    stage_icon = {"EARLY": "🌱 EARLY", "MID": "📈 MID", "LATE": "⚠️ LATE"}.get(stage, stage)

    body = "\n".join([
        f"  {d}   {pair}",
        f"  {sig['condition']}",
        f"  BB({BB_PERIOD},{BB_SD})  |  {TIMEFRAME}  |  Binance Perp  |  {LEVERAGE}x Paper",
        f"  {_SEP}",
        f"  {_kv('Entry',        str(e))}",
        f"  {_kv('Stop Loss',    f'{sl}   ({rsk_pct:.2f}% risk)')}",
        f"  {_kv('TP1  Fib 1.272', f'{tp1_str}   [{tp1_rr}]')}",
        f"  {_kv('TP2  Fib 1.618', f'{tp2_str}   [{tp2_rr}]')}",
        f"  {_kv('BB-Touch Exit', f'DYNAMIC  ({bb_label} at touch)')}",
        f"  {_kv(f'  {bb_label} now', f'{bb_ref}   (entry snapshot — band moves every candle)')}",
        f"  {_SEP}",
        f"  TREND INTELLIGENCE",
        f"  {_kv('Stage',        f'{stage_icon}   Score={score}/100')}",
        f"  {_kv('RSI 1h / 4h',  f'{rsi_1h_v:.1f}  /  {rsi_4h_v:.1f}')}",
        f"  {_kv('RSI Velocity', f'{rsi_vel_v:+.1f} pts/3c  (4h accel)')}",
        f"  {_kv('Volume Surge', f'{vol_rat_v:.2f}x avg')}",
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
    """Trade closed – WIN or LOSS."""
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

    # If this trade closed via the dynamic band-touch exit, show BOTH the
    # entry-time BB snapshot and the LIVE band value that actually triggered
    # the close. This makes it obvious that the BB exit is not a frozen level.
    bb_entry = trade.get("bb_at_entry")
    bb_exit  = trade.get("exit_bb_level")
    bb_rows  = []
    if bb_exit is not None and bb_entry is not None:
        drift_pct = (bb_exit - bb_entry) / bb_entry * 100
        bb_rows = [
            f"  {_kv('BB at entry',  f'{bb_entry}   (reference snapshot)')}",
            f"  {_kv('BB at exit',   f'{bb_exit}   (LIVE — triggered close)')}",
            f"  {_kv('BB drift',     f'{drift_pct:+.2f}%   over life of trade')}",
            f"  {_SEP}",
        ]

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
        *bb_rows,
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
        "  BB SCANNER PAPER PORTFOLIO  –  HOURLY REPORT",
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
        "  BB SCANNER  –  SYSTEM ACTIVE",
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
        "  LONG  : Upper Band Breakout Pullback (break above → pullback to band → BUY)",
        "  SHORT : Lower Band Breakdown Pullback (break below → bounce to band → SELL)",
        "  EXIT  : Band re-touch after extension (exit only — never opens opposite)",
        "  FILTER: No middle band activity · Min bandwidth · Min breakout distance",
        f"  {_SEP}",
        "  SIGNAL VALIDATION (NEW)",
        f"  • Signal freshness: {SIGNAL_FRESHNESS//60} min max age",
        f"  • Price slippage tolerance: {SIGNAL_SLIPPAGE_PCT*100:.1f}%",
        "  Stale or slipped signals are REJECTED (no trade opens)",
        f"  {_SEP}",
        "  EXIT LOGIC",
        "  SL         : FIXED at entry — low (LONG) / high (SHORT) of pullback candle",
        "  TP1 / TP2  : FIXED at entry — Fib 1.272 / 1.618 of swing range",
        "  BB Touch   : DYNAMIC — evaluated every scan vs the LIVE upper / lower",
        "               band. Price first extends beyond band, then closes on next",
        "               touch. Exit level is whatever the band is at that moment.",
        f"  {_SEP}",
        "  BB Scanner  |  For informational use only",
    ])

    payload = {
        "content": f"**BB SCANNER  |  SYSTEM ONLINE  |  {n_symbols} SYMBOLS  |  ${balance:,.2f} PAPER  |  VALIDATION ENABLED**",
        "embeds":  [{"color": 0x3b82f6, "description": f"```\n{body}\n```"}],
    }
    _post(payload)

# ═══════════════════════════════════════════════════════════════════
#  ⑩  SCAN LOOP
# ═══════════════════════════════════════════════════════════════════
def scan(symbols: list[str], trader: PaperTrader) -> int:
    found  = 0
    prices = {}   # symbol → last close price

    for i, sym in enumerate(symbols, 1):
        try:
            df = fetch_df(sym)
            if df is None or len(df) < BB_PERIOD + 15:
                time.sleep(REQUEST_DELAY)
                continue

            df = add_bb(df)
            prices[sym] = float(df.iloc[-1]["close"])

            # ── Signal check ──────────────────────────────────────────────────
            # Skip signal detection entirely if price is clearly in the middle
            # zone (between bands, away from both).  This is the "no middle band
            # activity" rule – saves CPU and avoids false signals in sideways.
            last = df.iloc[-1]
            mid_zone = (last["close"] > last["lower"] and last["close"] < last["upper"])
            near_upper = abs(last["close"] - last["upper"]) / last["upper"] < TOUCH_TOL * 3
            near_lower = abs(last["close"] - last["lower"]) / abs(last["lower"]) < TOUCH_TOL * 3
            in_dead_zone = mid_zone and not near_upper and not near_lower

            if not on_cooldown(sym) and not in_dead_zone:
                for fn in CHECKERS:
                    sig = fn(df)
                    if sig:
                        # ── Trend Intelligence Filter ─────────────────────────────
                        # Runs AFTER BB signal fires. Scores the signal on:
                        #   • RSI alignment (1h + 4h confirm direction)
                        #   • Trend stage   (EARLY=best / MID=ok / LATE=skip)
                        #   • RSI velocity  (4h RSI accelerating = trend just starting)
                        #   • Volume surge  (institutional fingerprint)
                        # Only EARLY/MID signals with volume confirmation are traded.
                        ok, trend_info = passes_rsi_filter(sym, sig["direction"], df)
                        if not ok:
                            break   # not aligned / late stage / no volume → skip

                        # Attach trend metadata to the signal for Discord + trade record
                        sig["trend_stage"]  = trend_info.get("stage",     "?")
                        sig["trend_score"]  = trend_info.get("score",      0)
                        sig["trend_reason"] = trend_info.get("reason",    "")
                        sig["rsi_1h"]       = trend_info.get("rsi_1h",   50.0)
                        sig["rsi_4h"]       = trend_info.get("rsi_4h",   50.0)
                        sig["rsi_vel"]      = trend_info.get("velocity",   0.0)
                        sig["vol_ratio"]    = trend_info.get("vol_ratio",  1.0)

                        tgt   = build_targets(df, sig)
                        trade = trader.open_trade(sym, sig, tgt)
                        if trade is None:
                            break

                        chart = make_chart(df, sig, tgt, sym)
                        if chart is None:
                            print(f"  [WARN] Chart skipped for {sym} – matplotlib not available. "
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
                        stage_tag = sig.get("trend_stage", "?")
                        score_tag = sig.get("trend_score", 0)
                        print(f"  [{ts}] 🔔 {sig['direction']} {sym}  "
                              f"Entry={sig['entry']}  SL={sig['sl']}  "
                              f"[{stage_tag} score={score_tag}]")
                        break   # one signal per symbol per scan

            if i % 50 == 0 or i == len(symbols):
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                print(f"  [{ts}] Scanned {i}/{len(symbols)}  ·  signals: {found}")

            time.sleep(REQUEST_DELAY)

        except Exception as ex:
            print(f"  ! {sym}: {ex}")
            time.sleep(REQUEST_DELAY)

    # ── Auto-close trades ──────────────────────────────────────────────────────
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
        print(f"  💰 CLOSED {t['id']} {t['symbol']}  {t['close_reason']}"
              f"  PnL=${rpnl:+.2f}")
        discord_close(t, trader.stats())

    return found

# ═══════════════════════════════════════════════════════════════════
#  ⑪  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════
def main():
    print()
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║   BB SCANNER  –  INSTITUTIONAL GRADE                         ║")
    print("║   Binance Perpetual  ·  1m  ·  BB(200,1)  ·  30x Paper       ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print(f"  Platform : {sys.platform}    Python : {sys.version.split()[0]}")
    print(f"  Charts   : {'ON (matplotlib)' if HAS_CHART else 'OFF (text-only Discord alerts)'}")
    print(f"  Trades   : {TRADES_FILE}")

    trader = PaperTrader()
    s      = trader.stats()
    print(f"  Paper Portfolio  →  Balance: ${s['balance']:,.2f}  "
          f"·  Open: {s['open']}  ·  Closed: {s['closed']}")

    # Robust symbol fetch – Termux / mobile networks can drop the first
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
        print(f"\n{'─'*66}")
        print(f"  SCAN #{scan_no:04d}  ·  {ts} UTC")
        print(f"{'─'*66}")

        try:
            n = scan(symbols, trader)
            s = trader.stats()
            print(f"\n  ✅  Scan #{scan_no:04d} complete  ·  Signals: {n}")
            print(f"  💼  Balance: ${s['balance']:,.2f}  "
                  f"Return: {s['ret_pct']:+.2f}%  "
                  f"Open: {s['open']}  Closed: {s['closed']}")

        except KeyboardInterrupt:
            raise
        except Exception as ex:
            # Never let a transient error kill 24/7 operation.
            print(f"\n  ❌ Scan error ({ex.__class__.__name__}): {ex}")

        # Hourly summary
        if time.time() - last_summary >= SUMMARY_EVERY:
            try:
                discord_summary(trader)
            except Exception as ex:
                print(f"  ! Summary send failed: {ex}")
            last_summary = time.time()

        mins = SCAN_INTERVAL // 60
        print(f"\n  Waiting {mins} min ({SCAN_INTERVAL}s)  ·  Ctrl+C to stop")
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
    # of dying – important for unattended Termux / boot use.
    while True:
        try:
            main()
            break   # clean exit (Ctrl+C inside main)
        except KeyboardInterrupt:
            break
        except Exception as ex:
            print(f"\n  💥 Fatal error: {ex.__class__.__name__}: {ex}")
            print("  Restarting in 30s...")
            time.sleep(30)
