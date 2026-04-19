"""
╔═══════════════════════════════════════════════════════════════════╗
║   BB SCANNER  –  INSTITUTIONAL GRADE                             ║
║   Binance Perpetual Futures  |  1m  |  BB(200, SD 1)             ║
║   Paper Trading: 30x Leverage  |  Discord Webhook Alerts         ║
║   Qwen AI Agent: Auto-analysis every 4h                          ║
║   Runs on:  Railway / Windows / Linux / macOS / Termux           ║
╚═══════════════════════════════════════════════════════════════════╝
"""

import io, json, os, sys, time, threading
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy  as np
import pandas as pd
import requests

try:
    from flask import Flask, jsonify
    app = Flask(__name__)
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    app = None
    print("  [INFO] Flask not installed. Running in standalone mode only.")

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
#  ①   USER CONFIG
# ═══════════════════════════════════════════════════════════════════
DISCORD_WEBHOOK  = os.environ.get(
    "DISCORD_WEBHOOK",
    "https://discord.com/api/webhooks/1494071862609575948/"
    "G04AVF9M0nCp0FYPNDgBwyPzUee-9IMQFxr88uH88euQmaD4JM4LbV1cTofMqGqiz3fX"
)

BB_PERIOD        = 200
BB_SD            = 1
TIMEFRAME        = "1m"
CANDLE_LIMIT     = 320
SCAN_INTERVAL    = 300
LOOKBACK_WINDOW  = 300
REQUEST_DELAY    = 0.15
SWING_LOOKBACK   = 60
TOUCH_TOL        = 0.003       # relaxed from 0.0025

BREAKOUT_LOOKBACK = 30
ENTRY_WINDOW      = 15         # relaxed from 10

MIN_BREAKOUT_PCT  = 0.002
MIN_BANDWIDTH_PCT = 0.008

RSI_PERIOD       = 14
RSI_LONG_1H      = 57          # relaxed from 60
RSI_LONG_4H      = 52          # relaxed from 55
RSI_SHORT_1H     = 43          # relaxed from 40
RSI_SHORT_4H     = 48          # relaxed from 45

TREND_STAGE_MID_4H   = 68
TREND_STAGE_LATE_4H  = 80
SKIP_LATE_STAGE      = True
VOLUME_SURGE_MULT    = 1.3     # relaxed from 1.5
VOLUME_LOOKBACK      = 20
RSI_VELOCITY_MIN     = 3.0     # relaxed from 4.0

INITIAL_BALANCE  = 10_000.0
LEVERAGE         = 30
RISK_PCT         = 0.02
MAX_MARGIN_PCT   = 0.25
SIGNAL_COOLDOWN  = 300
SUMMARY_EVERY    = 3600
QWEN_EVERY       = 4 * 3600

MAX_OPEN_TRADES  = 5

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRADES_FILE = os.path.join(_SCRIPT_DIR, "paper_trades.json")

CHARTS_DIR = os.path.join(_SCRIPT_DIR, "charts")
if not os.path.exists(CHARTS_DIR):
    try:
        os.makedirs(CHARTS_DIR, exist_ok=True)
    except Exception as e:
        print(f"  [WARN] Could not create charts folder: {e}.")
        CHARTS_DIR = _SCRIPT_DIR

# ═══════════════════════════════════════════════════════════════════
#  ②  EXCHANGE  —  multi-endpoint fallback for geo-restrictions
# ═══════════════════════════════════════════════════════════════════
FAPI_BASE = os.environ.get("BINANCE_PROXY_URL", "https://fapi.binance.com")

_FAPI_FALLBACKS_RAW = [
    os.environ.get("BINANCE_PROXY_URL", ""),
    "https://fapi.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://data.binance.com",
]
_seen_urls = set()
_FAPI_FALLBACKS = []
for _u in _FAPI_FALLBACKS_RAW:
    if _u and _u not in _seen_urls:
        _seen_urls.add(_u)
        _FAPI_FALLBACKS.append(_u)

_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})
_SESSION.headers.update({"User-Agent": "DiscordBot/1.0"})

# ═══════════════════════════════════════════════════════════════════
#  ③  SIGNAL COOLDOWN & VALIDATION
# ═══════════════════════════════════════════════════════════════════
_last_signal  = {}
_signal_cache = {}

def on_cooldown(sym):
    return (time.time() - _last_signal.get(sym, 0)) < SIGNAL_COOLDOWN

def mark_cooldown(sym):
    _last_signal[sym] = time.time()

SIGNAL_FRESHNESS    = 60
SIGNAL_SLIPPAGE_PCT = 0.02

def is_signal_valid(sym, current_price):
    if sym not in _signal_cache:
        return False
    cached   = _signal_cache[sym]
    age      = time.time() - cached["timestamp"]
    if age > SIGNAL_FRESHNESS:
        print(f"    [REJECT] {sym}: Signal too old ({age:.0f}s > {SIGNAL_FRESHNESS}s)")
        return False
    entry    = cached["entry_price"]
    slippage = abs(current_price - entry) / entry
    if slippage > SIGNAL_SLIPPAGE_PCT:
        print(f"    [REJECT] {sym}: Price slipped {slippage*100:.2f}%")
        return False
    print(f"    [VALID] {sym}: Signal fresh ({age:.0f}s old), slip {slippage*100:.2f}%")
    return True

def cache_signal(sym, sig, current_price):
    _signal_cache[sym] = {
        "signal":       sig,
        "timestamp":    time.time(),
        "entry_price":  current_price,
    }

# ═══════════════════════════════════════════════════════════════════
#  ④  DATA  —  get_symbols tries all fallback endpoints
# ═══════════════════════════════════════════════════════════════════
def get_symbols():
    global FAPI_BASE
    for base in _FAPI_FALLBACKS:
        try:
            url  = f"{base}/fapi/v1/exchangeInfo"
            print(f"  Trying {base} ...")
            resp = _SESSION.get(url, timeout=15)
            if resp.status_code == 451:
                print(f"  ! {base} geo-blocked (HTTP 451). Trying next...")
                continue
            resp.raise_for_status()
            data = resp.json()
            syms = []
            for s in data.get("symbols", []):
                if (s.get("quoteAsset") == "USDT"
                        and s.get("status")       == "TRADING"
                        and s.get("contractType") == "PERPETUAL"):
                    syms.append(s["baseAsset"] + "/USDT")
            if syms:
                FAPI_BASE = base
                print(f"  [OK] Connected via {base}")
                return sorted(set(syms))
            print(f"  ! {base} returned 0 symbols. Trying next...")
        except requests.exceptions.HTTPError as ex:
            print(f"  ! {base} HTTP error ({ex}). Trying next...")
        except requests.exceptions.ConnectionError:
            print(f"  ! {base} connection error. Trying next...")
        except requests.exceptions.Timeout:
            print(f"  ! {base} timed out. Trying next...")
        except Exception as ex:
            print(f"  ! {base} error ({ex.__class__.__name__}: {ex}). Trying next...")
    return []


def _raw_symbol(ccxt_sym):
    return ccxt_sym.replace("/", "")


_TF_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h",
    "12h": "12h", "1d": "1d", "3d": "3d", "1w": "1w", "1M": "1M",
}

def fetch_df(symbol):
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
        df   = pd.DataFrame(raw, columns=[
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
def add_bb(df):
    df        = df.copy()
    df["mid"]   = df["close"].rolling(BB_PERIOD).mean()
    df["std"]   = df["close"].rolling(BB_PERIOD).std(ddof=0)
    df["upper"] = df["mid"] + BB_SD * df["std"]
    df["lower"] = df["mid"] - BB_SD * df["std"]
    return df.dropna().reset_index(drop=True)

def calc_rsi(closes, period=RSI_PERIOD):
    if len(closes) < period + 1:
        return 50.0
    delta  = closes.diff().dropna()
    gain   = delta.clip(lower=0)
    loss   = (-delta).clip(lower=0)
    avg_g  = gain.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    avg_l  = loss.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - (100 / (1 + rs)), 2)

def fetch_mtf_rsi(symbol):
    result = {"rsi_1h": 50.0, "rsi_4h": 50.0, "rsi_4h_prev3": 50.0}
    for tf, rsi_key, prev_key in [
        ("1h", "rsi_1h",  None),
        ("4h", "rsi_4h",  "rsi_4h_prev3"),
    ]:
        try:
            limit  = RSI_PERIOD * 3 + 5
            params = {
                "symbol":   _raw_symbol(symbol),
                "interval": tf,
                "limit":    limit,
            }
            resp   = _SESSION.get(f"{FAPI_BASE}/fapi/v1/klines",
                                  params=params, timeout=10)
            resp.raise_for_status()
            raw    = resp.json()
            closes = pd.Series([float(c[4]) for c in raw])
            result[rsi_key] = calc_rsi(closes)
            if prev_key:
                result[prev_key] = calc_rsi(closes.iloc[:-3])
        except Exception as ex:
            print(f"    [WARN] RSI fetch failed for {symbol} {tf}: {ex}")
    return result


def score_trend(symbol, direction, df_1m):
    mtf      = fetch_mtf_rsi(symbol)
    r1h      = mtf["rsi_1h"]
    r4h      = mtf["rsi_4h"]
    r4h_prev = mtf["rsi_4h_prev3"]

    try:
        vol_avg   = float(df_1m["volume"].iloc[-VOLUME_LOOKBACK-1:-1].mean())
        vol_now   = float(df_1m["volume"].iloc[-1])
        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0
    except Exception:
        vol_ratio = 1.0

    velocity = r4h - r4h_prev

    if direction == "LONG":
        rsi_check_pass = (r1h >= RSI_LONG_1H) and (r4h >= RSI_LONG_4H)
        is_late        = r4h > TREND_STAGE_LATE_4H
        is_mid         = r4h > TREND_STAGE_MID_4H
        vel_ok         = velocity >= RSI_VELOCITY_MIN
    else:
        rsi_check_pass = (r1h <= RSI_SHORT_1H) and (r4h <= RSI_SHORT_4H)
        is_late        = r4h < (100 - TREND_STAGE_LATE_4H)
        is_mid         = r4h < (100 - TREND_STAGE_MID_4H)
        vel_ok         = velocity <= -RSI_VELOCITY_MIN

    if is_late:
        stage = "LATE"
    elif is_mid:
        stage = "MID"
    else:
        stage = "EARLY"

    if direction == "LONG":
        rsi_pts = min(30, int((r1h - 50) / 50 * 30) + int((r4h - 50) / 50 * 30)) // 2
    else:
        rsi_pts = min(30, int((50 - r1h) / 50 * 30) + int((50 - r4h) / 50 * 30)) // 2
    rsi_pts = max(0, rsi_pts)

    stage_pts = {"EARLY": 25, "MID": 15, "LATE": 0}[stage]

    if direction == "LONG":
        vel_pts = min(25, int(max(0, velocity) / 15 * 25))
    else:
        vel_pts = min(25, int(max(0, -velocity) / 15 * 25))

    vol_pts = min(20, int((vol_ratio - 1.0) / (VOLUME_SURGE_MULT - 1.0) * 20))
    vol_pts = max(0, vol_pts)

    score = rsi_pts + stage_pts + vel_pts + vol_pts

    passed = (
        rsi_check_pass
        and (not SKIP_LATE_STAGE or stage != "LATE")
        and vol_ratio >= VOLUME_SURGE_MULT
    )

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


def passes_rsi_filter(symbol, direction, df_1m=None):
    if df_1m is None:
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

def sw_high(df):
    return float(df.iloc[-(SWING_LOOKBACK + 1):-1]["high"].max())

def sw_low(df):
    return float(df.iloc[-(SWING_LOOKBACK + 1):-1]["low"].min())

# ═══════════════════════════════════════════════════════════════════
#  ⑥  SIGNAL DETECTION
# ═══════════════════════════════════════════════════════════════════
def _build(direction, condition, entry, sl):
    return {"direction": direction, "condition": condition,
            "entry": round(float(entry), 8), "sl": round(float(sl), 8)}


def long_band_touch(df):
    n = len(df)
    if n < BB_PERIOD + BREAKOUT_LOOKBACK + 2:
        return None

    current = df.iloc[-1]

    bandwidth_pct = (current["upper"] - current["lower"]) / current["mid"]
    if bandwidth_pct < MIN_BANDWIDTH_PCT:
        return None

    if current["close"] < current["mid"]:
        return None

    breakout     = None
    breakout_pos = None

    for offset in range(2, min(BREAKOUT_LOOKBACK + 1, n - 1)):
        candidate = df.iloc[-1 - offset]
        if candidate["close"] <= candidate["upper"]:
            continue
        bd = (candidate["close"] - candidate["upper"]) / candidate["upper"]
        if bd < MIN_BREAKOUT_PCT:
            continue
        breakout     = candidate
        breakout_pos = offset
        break

    if breakout is None:
        return None

    if breakout_pos > ENTRY_WINDOW:
        return None

    for pb_offset in range(1, breakout_pos):
        pullback = df.iloc[-1 - pb_offset]
        tol = pullback["upper"] * TOUCH_TOL

        touched = (
            pullback["low"]   <= pullback["upper"] + tol
            and pullback["high"] >= pullback["upper"]
            and pullback["close"] < breakout["close"]
        )
        if not touched:
            continue

        if current["close"] <= pullback["close"]:
            continue

        candles_since = breakout_pos
        print(f"    [SIGNAL] LONG pattern: breakout={candles_since}c ago  "
              f"pullback={pb_offset}c ago  entry={current['close']:.8g}  "
              f"sl={pullback['low']:.8g}")
        return _build("LONG", "Upper Band Breakout Pullback",
                      current["close"], pullback["low"])

    return None


def short_band_touch(df):
    n = len(df)
    if n < BB_PERIOD + BREAKOUT_LOOKBACK + 2:
        return None

    current = df.iloc[-1]

    bandwidth_pct = (current["upper"] - current["lower"]) / current["mid"]
    if bandwidth_pct < MIN_BANDWIDTH_PCT:
        return None
    if current["close"] > current["mid"]:
        return None

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
        return None

    for pb_offset in range(1, breakdown_pos):
        bounce = df.iloc[-1 - pb_offset]
        tol = abs(bounce["lower"]) * TOUCH_TOL

        touched = (
            bounce["high"] >= bounce["lower"] - tol
            and bounce["low"] <= bounce["lower"]
            and bounce["close"] > breakdown["close"]
        )
        if not touched:
            continue

        if current["close"] >= bounce["close"]:
            continue

        print(f"    [SIGNAL] SHORT pattern: breakdown={breakdown_pos}c ago  "
              f"bounce={pb_offset}c ago  entry={current['close']:.8g}  "
              f"sl={bounce['high']:.8g}")
        return _build("SHORT", "Lower Band Breakdown Pullback",
                      current["close"], bounce["high"])

    return None

CHECKERS = [long_band_touch, short_band_touch]


def build_targets(df, sig):
    e  = sig["entry"]
    sl = sig["sl"]
    d  = sig["direction"]
    sh, sl_ = sw_high(df), sw_low(df)
    move = sh - sl_

    if d == "LONG":
        t1 = round(e + move * 1.272, 8)
        t2 = round(e + move * 1.618, 8)
        bb_ref = round(float(df.iloc[-1]["upper"]), 8)
        return {
            "tp1": t1 if t1 > e else None,
            "tp2": t2 if t2 > e else None,
            "bb_at_entry": bb_ref,
            "swing_high": round(sh, 8),
            "swing_low":  round(sl_, 8),
            "entry_candle_time": str(df.iloc[-1]["time"]),
        }
    else:
        t1 = round(e - move * 1.272, 8)
        t2 = round(e - move * 1.618, 8)
        bb_ref = round(float(df.iloc[-1]["lower"]), 8)
        return {
            "tp1": t1 if t1 < e else None,
            "tp2": t2 if t2 < e else None,
            "bb_at_entry": bb_ref,
            "swing_high": round(sh, 8),
            "swing_low":  round(sl_, 8),
            "entry_candle_time": str(df.iloc[-1]["time"]),
        }

# ═══════════════════════════════════════════════════════════════════
#  ⑦  PAPER TRADER
# ═══════════════════════════════════════════════════════════════════
class PaperTrader:

    def __init__(self):
        self._load()

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
        tmp = TRADES_FILE + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump({"balance": round(self.balance, 6),
                           "open_trades":   self.open_trades,
                           "closed_trades": self.closed_trades,
                           "counter":       self.counter}, f, indent=2)
            os.replace(tmp, TRADES_FILE)
        except Exception as ex:
            print(f"  [WARN] Portfolio save failed: {ex}")
            try:
                os.remove(tmp)
            except OSError:
                pass

    def open_trade(self, symbol, sig, targets):
        e  = sig["entry"]
        sl = sig["sl"]
        sl_pct = abs(e - sl) / e
        if sl_pct < 0.0001:
            return None

        if len(self.open_trades) >= MAX_OPEN_TRADES:
            print(f"    [SKIP] {symbol}: max open trades ({MAX_OPEN_TRADES})")
            return None

        existing_syms = {t["symbol"] for t in self.open_trades}
        if symbol in existing_syms:
            print(f"    [SKIP] {symbol}: already has an open trade")
            return None

        risk_usdt = self.balance * RISK_PCT
        notional  = risk_usdt / sl_pct
        margin    = notional / LEVERAGE

        if margin > self.balance * MAX_MARGIN_PCT:
            margin   = self.balance * MAX_MARGIN_PCT
            notional = margin * LEVERAGE

        if margin > self.balance:
            print(f"    [SKIP] {symbol}: margin ({margin:.2f}) > balance ({self.balance:.2f})")
            return None

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
            "bb_at_entry": targets["bb_at_entry"],
            "notional":  round(notional, 4),
            "margin":    round(margin,   4),
            "leverage":  LEVERAGE,
            "qty":       round(notional / e, 6),
            "open_time": datetime.now(timezone.utc).isoformat(),
            "entry_candle_time": targets.get("entry_candle_time"),
            "status":    "OPEN",
            "upnl":      0.0,
            "extended":     False,
            "exit_bb_level": None,
        }
        self.open_trades.append(trade)
        self._save()
        return trade

    def update(self, prices, df_dict=None):
        still_open, closed = [], []

        for t in self.open_trades:
            px = prices.get(t["symbol"])
            if df_dict and t["symbol"] in df_dict:
                px = float(df_dict[t["symbol"]].iloc[-1]["close"])
            if px is None:
                still_open.append(t)
                continue

            d  = t["direction"]
            cp = cr = None

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
                                entry_ts    = pd.Timestamp(entry_ct)
                                cur_is_new  = cur["time"]  > entry_ts
                                prev_is_new = prev["time"] > entry_ts
                            else:
                                cur_is_new = prev_is_new = True
                            if (cur_is_new and cur["high"] > upper) or (prev_is_new and prev["high"] > upper):
                                t["extended"] = True
                                print(f"    [EXTEND] {t['id']} {t['symbol']} LONG extended above upper band")

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
                                entry_ts    = pd.Timestamp(entry_ct)
                                cur_is_new  = cur["time"]  > entry_ts
                                prev_is_new = prev["time"] > entry_ts
                            else:
                                cur_is_new = prev_is_new = True
                            if (cur_is_new and cur["low"] < lower) or (prev_is_new and prev["low"] < lower):
                                t["extended"] = True
                                print(f"    [EXTEND] {t['id']} {t['symbol']} SHORT extended below lower band")

                        elif t["extended"]:
                            touching = (
                                cur["low"]  <= lower + tol_l
                                and cur["high"] >= lower - tol_l
                                and cur["close"] <= lower + tol_l
                            )
                            if touching:
                                cp, cr = px, "Lower Band Touch Exit ✅"
                                t["exit_bb_level"] = round(float(lower), 8)

            if cp is None:
                if d == "LONG"  and px <= t["sl"]:
                    cp, cr = t["sl"], "SL ❌ Stop Loss"
                elif d == "SHORT" and px >= t["sl"]:
                    cp, cr = t["sl"], "SL ❌ Stop Loss"
            if cp is None:
                if d == "LONG":
                    if   t["tp2"] and px >= t["tp2"]: cp, cr = t["tp2"], "TP2 ✅ Fib 1.618"
                    elif t["tp1"] and px >= t["tp1"]: cp, cr = t["tp1"], "TP1 ✅ Fib 1.272"
                    else: t["upnl"] = round((px - t["entry"]) / t["entry"] * t["notional"], 4)
                else:
                    if   t["tp2"] and px <= t["tp2"]: cp, cr = t["tp2"], "TP2 ✅ Fib 1.618"
                    elif t["tp1"] and px <= t["tp1"]: cp, cr = t["tp1"], "TP1 ✅ Fib 1.272"
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

    def stats(self):
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
#  ⑧  CHART
# ═══════════════════════════════════════════════════════════════════
BG      = "#0d1117"
BULL    = "#26a69a"
BEAR    = "#ef5350"
BB_CLR  = "#3b82f6"
MID_CLR = "#f97316"
GRID    = "#1c2333"
FG      = "#8b949e"
WHITE   = "#e6edf3"

def make_chart(df, sig, tgt, symbol):
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

    ax.fill_between(xs, plot["upper"], plot["lower"],
                    color=BB_CLR, alpha=0.06, zorder=1)
    ax.plot(xs, plot["upper"], color=BB_CLR, lw=1.3, label="Upper BB", zorder=2)
    ax.plot(xs, plot["mid"],   color=MID_CLR, lw=1.3, label="SMA 200",   zorder=2)
    ax.plot(xs, plot["lower"], color=BB_CLR, lw=1.0, ls="--",
            label="Lower BB", alpha=0.8, zorder=2)

    for i, row in plot.iterrows():
        col = BULL if row["close"] >= row["open"] else BEAR
        ax.plot([i, i], [row["low"], row["high"]], color=col, lw=0.9, zorder=3)
        ax.bar(i, abs(row["close"] - row["open"]),
               bottom=min(row["open"], row["close"]),
               color=col, width=0.7, zorder=4, alpha=0.95)

    vcols = [BULL if plot.iloc[i]["close"] >= plot.iloc[i]["open"] else BEAR
             for i in range(n)]
    axv.bar(xs, plot["volume"], color=vcols, alpha=0.65, width=0.7)
    axv.set_ylabel("Volume", color=FG, fontsize=8)

    si = n - 2
    is_long = d == "LONG"
    y0    = plot.iloc[si]["low"]  * 0.9965 if is_long else plot.iloc[si]["high"] * 1.0035
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

    step = max(1, n // 10)
    plt.setp(ax.get_xticklabels(), visible=False)
    axv.set_xticks(range(0, n, step))
    axv.set_xticklabels(
        [plot.iloc[i]["time"].strftime("%d %b\n%H:%M") for i in range(0, n, step)],
        fontsize=7, color=FG
    )

    ax.legend(loc="upper left", facecolor="#161b22", labelcolor=FG,
              fontsize=8.5, framealpha=0.9, edgecolor=GRID)
    fig.suptitle(
        f"  {symbol}   ·   BB({BB_PERIOD}, {BB_SD})   ·   {TIMEFRAME}   ·   {sig['condition']}",
        color=WHITE, fontsize=12, fontweight="bold", x=0.01, ha="left", y=0.99
    )

    fig.subplots_adjust(left=0.03, right=0.88, top=0.96, bottom=0.07, hspace=0.03)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=75, facecolor=BG, edgecolor="none", pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    return buf.read()

# ═══════════════════════════════════════════════════════════════════
#  ⑨  DISCORD
# ═══════════════════════════════════════════════════════════════════
_SEP  = "─" * 44
_W    = 18

def _kv(label, value):
    return f"{label:<{_W}}: {value}"

def _rr(entry, target, sl):
    risk = abs(entry - sl)
    if not risk or target is None:
        return "—"
    return f"{abs(target - entry) / risk:.2f}x R:R"

def _strip_attachment_images(payload):
    clean = json.loads(json.dumps(payload))
    clean.pop("attachments", None)
    for embed in clean.get("embeds", []):
        image = embed.get("image")
        if isinstance(image, dict) and str(image.get("url", "")).startswith("attachment://"):
            embed.pop("image", None)
    return clean

def _post(payload, chart=None):
    last_error = None

    for attempt in range(1, 5):
        try:
            if chart:
                chart_size_kb = len(chart) / 1024
                print(f"  [DEBUG] Uploading chart ({chart_size_kb:.1f} KB) to Discord...")
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


def _post_chart_only(symbol, sig, chart):
    pair = symbol.replace("/USDT", "") + " / USDT"
    embed = {
        "title":       f"📊 {sig['direction']} {pair} | {sig['condition']}",
        "color":       2263127 if sig["direction"] == "LONG" else 15728640,
        "description": f"Signal: {sig['condition']}\nEntry: {sig['entry']}\nStop Loss: {sig['sl']}",
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }
    payload_json = json.dumps({"embeds": [embed]})
    try:
        print(f"  [DEBUG] Sending chart to Discord...")
        r = _SESSION.post(
            DISCORD_WEBHOOK,
            data={"payload_json": payload_json},
            files={"file": ("chart.png", chart, "image/png")},
            timeout=60,
        )
        print(f"  [DEBUG] Chart upload response: HTTP {r.status_code}")
        if r.status_code in (200, 204):
            print(f"  ✅ Chart sent successfully to Discord")
        else:
            print(f"  ! Chart upload returned HTTP {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
    except Exception as ex:
        print(f"  ! Chart send error ({ex.__class__.__name__}): {ex}")


def discord_signal_with_chart(symbol, sig, tgt, trade, stats, chart_bytes):
    d        = sig["direction"]
    is_long  = d == "LONG"
    color    = 0x22c55e if is_long else 0xef4444
    e, sl    = sig["entry"], sig["sl"]
    rsk_pct  = abs(e - sl) / e * 100
    tp1_str  = str(tgt.get("tp1") or "—")
    tp2_str  = str(tgt.get("tp2") or "—")
    ts       = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S UTC")
    pair     = symbol.replace("/USDT", "") + " / USDT"

    tp1_rr     = _rr(e, tgt.get("tp1"), sl)
    tp2_rr     = _rr(e, tgt.get("tp2"), sl)
    notional_v = trade["notional"]
    margin_v   = trade["margin"]
    bal_v      = stats["balance"]
    ret_v      = stats["ret_pct"]
    win_v      = stats["win_rate"]
    bb_ref     = tgt["bb_at_entry"]
    bb_label   = "Upper BB" if is_long else "Lower BB"

    stage     = sig.get("trend_stage",  "?")
    score     = sig.get("trend_score",   0)
    rsi_1h_v  = sig.get("rsi_1h",      50.0)
    rsi_4h_v  = sig.get("rsi_4h",      50.0)
    rsi_vel_v = sig.get("rsi_vel",      0.0)
    vol_rat_v = sig.get("vol_ratio",    1.0)
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
        f"  {_kv(f'  {bb_label} now', f'{bb_ref}   (entry snapshot)')}",
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

    embed   = {"color": color, "description": f"```\n{body}\n```"}
    payload = {
        "content": f"**BB SCANNER  |  NEW SIGNAL  |  {d}  {pair}  |  {sig['condition'].upper()}**",
        "embeds":  [embed],
    }
    _post(payload)
    if chart_bytes:
        print(f"  [DEBUG] Sending chart separately after text alert...")
        _post_chart_only(symbol, sig, chart_bytes)


def discord_close(trade, stats):
    rpnl   = trade.get("rpnl", 0)
    color  = 0x22c55e if rpnl > 0 else 0xef4444
    result = "WIN" if rpnl > 0 else "LOSS"
    pct    = (trade["close_price"] - trade["entry"]) / trade["entry"] * 100
    if trade["direction"] == "SHORT":
        pct = -pct
    ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S UTC")
    pair  = trade["symbol"].replace("/USDT", "") + " / USDT"

    _bal = stats["balance"]
    _ret = stats["ret_pct"]
    _wr  = stats["win_rate"]
    _w   = stats["wins"]
    _l   = stats["losses"]

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


def discord_summary(trader):
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

    _sb  = s["balance"]
    _sr  = s["ret_pct"]
    _srp = s["rpnl"]
    _sup = s["upnl"]
    _swr = s["win_rate"]
    _sw  = s["wins"]
    _sl_ = s["losses"]

    body = "\n".join([
        "  BB SCANNER PAPER PORTFOLIO  –  HOURLY REPORT",
        f"  {ts}",
        f"  {_SEP}",
        f"  {_kv('Balance',       f'$ {_sb:>12,.2f}')}",
        f"  {_kv('Total Return',  f'{_sr:+.2f}%')}",
        f"  {_kv('Realised PnL',  f'$ {_srp:>+12,.2f}')}",
        f"  {_kv('Unrealised',    f'$ {_sup:>+12,.2f}')}",
        f"  {_SEP}",
        f"  {_kv('Win Rate',      f'{_swr}%   ({_sw}W / {_sl_}L)')}",
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


def discord_qwen_report(analysis):
    ts     = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S UTC")
    summ   = str(analysis.get("summary", "No summary."))[:400]
    act    = str(analysis.get("action",  "No action."))[:300]
    upd    = analysis.get("parameter_updates", {})
    if not isinstance(upd, dict):
        upd = {}
    applied = analysis.get("_applied_changes", {})
    if not isinstance(applied, dict):
        applied = {}

    if applied:
        upd_str = "\n".join([f"  {k}: {v}" for k, v in applied.items()])
    elif upd:
        upd_str = "\n".join([f"  {k} → {v}" for k, v in upd.items()])
    else:
        upd_str = "  No changes applied."

    body = "\n".join([
        "  QWEN AI ANALYSIS REPORT",
        f"  {ts}",
        f"  {_SEP}",
        "  SUMMARY",
        f"  {summ}",
        f"  {_SEP}",
        "  RECOMMENDED ACTION",
        f"  {act}",
        f"  {_SEP}",
        "  PARAMETER UPDATES APPLIED",
        upd_str,
        f"  {_SEP}",
        "  BB Scanner  |  Qwen AI Agent",
    ])

    payload = {
        "content": "**BB SCANNER  |  QWEN AI ANALYSIS  |  4-HOUR REPORT**",
        "embeds":  [{"color": 0x9333ea, "description": f"```\n{body}\n```"}],
    }
    _post(payload)


def discord_startup(n_symbols, balance):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S UTC")

    body = "\n".join([
        "  BB SCANNER  –  SYSTEM ACTIVE",
        f"  {ts}",
        f"  {_SEP}",
        f"  {_kv('Strategy',       f'BB({BB_PERIOD},{BB_SD})  |  {TIMEFRAME}')}",
        f"  {_kv('Exchange',       'Binance USDT-Margined Perpetuals')}",
        f"  {_kv('Base URL',       FAPI_BASE)}",
        f"  {_kv('Universe',       f'{n_symbols} active USDT perpetuals')}",
        f"  {_kv('Scan interval',  f'Every {SCAN_INTERVAL // 60} min  ({SCAN_INTERVAL}s)')}",
        f"  {_kv('Leverage',       f'{LEVERAGE}x paper trading')}",
        f"  {_kv('Start balance',  f'$ {balance:>12,.2f}')}",
        f"  {_kv('Qwen Agent',     'Every 4h  (auto trade analysis)')}",
        f"  {_SEP}",
        "  SIGNAL CONDITIONS",
        "  LONG  : Upper Band Breakout Pullback",
        "  SHORT : Lower Band Breakdown Pullback",
        "  EXIT  : Band re-touch after extension",
        "  FILTER: No middle band activity, Min bandwidth, Min breakout distance",
        f"  {_SEP}",
        f"  {_kv('RSI LONG  1h/4h',  f'>= {RSI_LONG_1H} / >= {RSI_LONG_4H}')}",
        f"  {_kv('RSI SHORT 1h/4h',  f'<= {RSI_SHORT_1H} / <= {RSI_SHORT_4H}')}",
        f"  {_kv('Volume surge min', f'{VOLUME_SURGE_MULT}x')}",
        f"  {_kv('Entry window',     f'{ENTRY_WINDOW} candles')}",
        f"  {_kv('Touch tolerance',  f'{TOUCH_TOL*100:.2f}%')}",
        f"  {_SEP}",
        "  BB Scanner  |  For informational use only",
    ])

    payload = {
        "content": f"**BB SCANNER  |  SYSTEM ONLINE  |  {n_symbols} SYMBOLS  |  ${balance:,.2f} PAPER**",
        "embeds":  [{"color": 0x3b82f6, "description": f"```\n{body}\n```"}],
    }
    _post(payload)

# ═══════════════════════════════════════════════════════════════════
#  ⑩  QWEN AGENT RUNNER (called from main loop every 4h)
# ═══════════════════════════════════════════════════════════════════
def run_qwen_agent():
    try:
        print("\n  Running Qwen AI analysis...")
        from qwen_agent import analyze_and_fix
        analysis = analyze_and_fix()
        if analysis:
            discord_qwen_report(analysis)
            print("  Qwen analysis complete and sent to Discord.")
        else:
            # Still send a report so Discord doesn't just show the title with no body
            discord_qwen_report({
                "summary": "No recent trades to analyze this cycle. Scanner is running normally.",
                "action":  "No parameter changes required. Waiting for next trade cycle.",
                "parameter_updates": {},
                "_applied_changes": {},
            })
            print("  Qwen agent: nothing to report this cycle.")
    except ImportError:
        print("  [WARN] qwen_agent.py not found. Skipping Qwen analysis.")
        discord_qwen_report({
            "summary": "qwen_agent.py not found. Please ensure the file is deployed.",
            "action":  "Upload qwen_agent.py to the same directory as main.py.",
            "parameter_updates": {},
            "_applied_changes": {},
        })
    except Exception as ex:
        err_msg = f"{ex.__class__.__name__}: {ex}"
        print(f"  ! Qwen analysis failed: {err_msg}")
        discord_qwen_report({
            "summary": f"Qwen agent error: {err_msg}",
            "action":  "Check Railway logs for details. Verify QWEN_API_KEY is set if using AI analysis.",
            "parameter_updates": {},
            "_applied_changes": {},
        })

# ═══════════════════════════════════════════════════════════════════
#  ⑪  SCAN LOOP
# ═══════════════════════════════════════════════════════════════════
def scan(symbols, trader):
    found  = 0
    prices = {}

    for i, sym in enumerate(symbols, 1):
        try:
            df = fetch_df(sym)
            if df is None or len(df) < BB_PERIOD + 15:
                time.sleep(REQUEST_DELAY)
                continue

            df = add_bb(df)
            prices[sym] = float(df.iloc[-1]["close"])

            last = df.iloc[-1]
            mid_zone  = (last["close"] > last["lower"] and last["close"] < last["upper"])
            near_upper = abs(last["close"] - last["upper"]) / last["upper"] < TOUCH_TOL * 3
            near_lower = abs(last["close"] - last["lower"]) / abs(last["lower"]) < TOUCH_TOL * 3
            in_dead_zone = mid_zone and not near_upper and not near_lower

            if not on_cooldown(sym) and not in_dead_zone:
                for fn in CHECKERS:
                    sig = fn(df)
                    if sig:
                        ok, trend_info = passes_rsi_filter(sym, sig["direction"], df)
                        if not ok:
                            break

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
                            print(f"  [WARN] Chart skipped for {sym}.")
                        else:
                            chart_size_kb = len(chart) / 1024
                            print(f"  [DEBUG] Chart generated: {chart_size_kb:.1f} KB")
                            try:
                                chart_file = os.path.join(
                                    CHARTS_DIR,
                                    f"chart_{sym.replace('/', '_')}_{int(time.time())}.png"
                                )
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
                        print(f"  [{ts}] SIGNAL {sig['direction']} {sym}  "
                              f"Entry={sig['entry']}  SL={sig['sl']}  "
                              f"[{stage_tag} score={score_tag}]")
                        break

            if i % 50 == 0 or i == len(symbols):
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                print(f"  [{ts}] Scanned {i}/{len(symbols)}  ·  signals: {found}")

            time.sleep(REQUEST_DELAY)

        except Exception as ex:
            print(f"  ! {sym}: {ex}")
            time.sleep(REQUEST_DELAY)

    # Auto-close open trades
    df_dict = {}
    for t in trader.open_trades:
        sym = t["symbol"]
        if sym in prices:
            try:
                df = fetch_df(sym)
                if df is not None and len(df) >= BB_PERIOD + 15:
                    df = add_bb(df)
                    df_dict[sym] = df
            except Exception:
                pass

    closed = trader.update(prices, df_dict if df_dict else None)
    for t in closed:
        rpnl = t.get("rpnl", 0)
        print(f"  CLOSED {t['id']} {t['symbol']}  {t['close_reason']}"
              f"  PnL=${rpnl:+.2f}")
        discord_close(t, trader.stats())

    return found

# ═══════════════════════════════════════════════════════════════════
#  ⑫  MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    print()
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║   BB SCANNER  –  INSTITUTIONAL GRADE                         ║")
    print("║   Binance Perpetual  ·  1m  ·  BB(200,1)  ·  30x Paper       ║")
    print("║   Qwen AI Agent: every 4h                                    ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print(f"  Platform : {sys.platform}    Python : {sys.version.split()[0]}")
    print(f"  Charts   : {'ON (matplotlib)' if HAS_CHART else 'OFF (text-only Discord alerts)'}")
    print(f"  Trades   : {TRADES_FILE}")

    trader = PaperTrader()
    s      = trader.stats()
    print(f"  Paper Portfolio  →  Balance: ${s['balance']:,.2f}  "
          f"·  Open: {s['open']}  ·  Closed: {s['closed']}")

    symbols = []
    backoff = 5
    while not symbols:
        try:
            print("  Loading Binance symbols...")
            symbols = get_symbols()
            if symbols:
                print(f"  {len(symbols)} USDT perpetuals loaded.")
        except Exception as ex:
            print(f"  ! Symbol fetch failed ({ex.__class__.__name__}: {ex}). "
                  f"Retrying in {backoff}s...")
        if not symbols:
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)
    print()

    try:
        discord_startup(len(symbols), trader.balance)
    except Exception as ex:
        print(f"  ! Startup notification failed: {ex}")

    scan_no      = 0
    last_summary = time.time()
    last_qwen    = time.time()
    max_loops    = int(os.environ.get("MAX_LOOPS", "0"))

    while True:
        scan_no += 1
        if max_loops > 0 and scan_no > max_loops:
            print(f"\n  [INFO] Reached MAX_LOOPS ({max_loops}). Exiting...")
            break

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'─'*66}")
        print(f"  SCAN #{scan_no:04d}  ·  {ts} UTC")
        print(f"{'─'*66}")

        try:
            n = scan(symbols, trader)
            s = trader.stats()
            print(f"\n  Scan #{scan_no:04d} complete  ·  Signals: {n}")
            print(f"  Balance: ${s['balance']:,.2f}  "
                  f"Return: {s['ret_pct']:+.2f}%  "
                  f"Open: {s['open']}  Closed: {s['closed']}")

        except KeyboardInterrupt:
            raise
        except Exception as ex:
            print(f"\n  Scan error ({ex.__class__.__name__}): {ex}")

        if time.time() - last_summary >= SUMMARY_EVERY:
            try:
                discord_summary(trader)
            except Exception as ex:
                print(f"  ! Summary send failed: {ex}")
            last_summary = time.time()

        if time.time() - last_qwen >= QWEN_EVERY:
            run_qwen_agent()
            last_qwen = time.time()

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


# ═══════════════════════════════════════════════════════════════════
#  ⑬  ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    IS_CI     = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
    IS_RENDER = os.environ.get("PORT") is not None and not IS_CI

    if IS_RENDER and HAS_FLASK:
        @app.route("/")
        def health():
            return jsonify({"status": "running", "service": "BB Scanner"})

        @app.route("/health")
        def health_check():
            return jsonify({"status": "healthy"})

        @app.route("/status")
        def status():
            trader_tmp = PaperTrader()
            s = trader_tmp.stats()
            return jsonify({
                "scanner":  "active",
                "flask":    "running",
                "port":     os.environ.get("PORT", 8000),
                "balance":  s["balance"],
                "return":   s["ret_pct"],
                "open":     s["open"],
                "closed":   s["closed"],
            })

        scanner_thread = threading.Thread(target=main, daemon=True)
        scanner_thread.start()
        print("  Scanner started in background thread")
        print(f"  Flask server starting on port {os.environ.get('PORT', 8000)}")

        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), threaded=True)

    else:
        if IS_CI:
            print("  [CI] GitHub Actions detected — Flask server disabled.")
        while True:
            try:
                main()
                break
            except KeyboardInterrupt:
                break
            except Exception as ex:
                print(f"\n  Fatal error: {ex.__class__.__name__}: {ex}")
                if IS_CI:
                    raise
                print("  Restarting in 30s...")
                time.sleep(30)
