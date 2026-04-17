import os
import time
import logging
import statistics
import requests
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException

# --- CONFIGURATION (From Environment Variables) ---
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Scanner Settings
SCAN_INTERVAL_SECONDS = int(os.getenv('SCAN_INTERVAL', '300'))  # Default 5 mins
TIMEFRAME = os.getenv('TIMEFRAME', '15m')
MIN_BANDWIDTH_PCT = float(os.getenv('MIN_BANDWIDTH', '0.008')) # 0.8%
RSI_LOW = int(os.getenv('RSI_LOW', '45'))
RSI_HIGH = int(os.getenv('RSI_HIGH', '65'))
TOP_N_SYMBOLS = int(os.getenv('TOP_N_SYMBOLS', '100'))

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS ---

def get_top_symbols(client, limit=TOP_N_SYMBOLS):
    """Fetch top volume USDT pairs"""
    try:
        tickers = client.get_ticker()
        # Filter USDT pairs with decent volume (> $1M quote volume to avoid dust)
        usdt_pairs = [
            t for t in tickers 
            if t['symbol'].endswith('USDT') and float(t['quoteVolume']) > 1000000
        ]
        # Sort by volume descending
        sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
        return [t['symbol'] for t in sorted_pairs[:limit]]
    except Exception as e:
        logger.error(f"Error fetching symbols: {e}")
        return []

def fetch_klines(client, symbol, interval=TIMEFRAME, lookback=50):
    """Fetch candle data"""
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=lookback)
        if not klines:
            return None, None, None
            
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        return closes, highs, lows
    except BinanceAPIException as e:
        if e.code == -1121: # Invalid symbol
            return None, None, None
        logger.warning(f"API Error for {symbol}: {e}")
        return None, None, None
    except Exception as e:
        logger.warning(f"Data error for {symbol}: {e}")
        return None, None, None

def calculate_bb(closes, period=20, std_dev=2):
    """Calculate Bollinger Bands"""
    if len(closes) < period:
        return None, None, None
    
    ma = statistics.mean(closes[-period:])
    std = statistics.stdev(closes[-period:])
    
    upper = ma + (std_dev * std)
    lower = ma - (std_dev * std)
    bandwidth = (upper - lower) / ma if ma != 0 else 0
    
    return upper, lower, bandwidth

def calculate_rsi(closes, period=14):
    """Calculate RSI"""
    if len(closes) < period + 1:
        return 50 
    
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
            
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def check_signal(symbol, closes, highs, lows):
    """
    Core Logic: Checks for BB + RSI setup
    Returns: (Signal Type, Reason, Details) or (None, Reason, Details)
    """
    if not closes or len(closes) < 20:
        return None, "INSUFFICIENT_DATA", ""

    current_price = closes[-1]
    prev_close = closes[-2]
    
    # Calculate Indicators
    upper, lower, bandwidth = calculate_bb(closes)
    rsi = calculate_rsi(closes)
    
    if upper is None or lower is None:
        return None, "CALC_ERROR", ""

    mid = (upper + lower) / 2
    range_size = upper - lower
    
    # 1. Bandwidth Filter (The Squeeze)
    if bandwidth < MIN_BANDWIDTH_PCT:
        return None, "BANDWIDTH_FAIL", f"BW:{bandwidth:.4f} < {MIN_BANDWIDTH_PCT}"
    
    # 2. Dead Zone Filter
    # Define zones: Lower 20%, Upper 20%, Middle 60%
    lower_zone_threshold = lower + (range_size * 0.2)
    upper_zone_threshold = upper - (range_size * 0.2)
    
    position = "MIDDLE"
    if lower <= current_price <= lower_zone_threshold:
        position = "LOWER"
    elif upper_zone_threshold <= current_price <= upper:
        position = "UPPER"
    
    if position == "MIDDLE":
        return None, "DEAD_ZONE", f"Price:{current_price} Mid:{mid:.2f}"

    # 3. Pattern Detection
    signal = None
    details = f"RSI:{rsi:.1f} BW:{bandwidth:.4f} Pos:{position}"

    # LONG SETUP: Price in Lower Zone + RSI Low + Bullish Candle
    if position == "LOWER":
        if rsi < RSI_LOW:
            # Bullish engulfing or strong green candle
            if current_price > prev_close:
                candle_body = current_price - prev_close
                if candle_body > (prev_close * 0.002): # 0.2% move
                    signal = "LONG"
    
    # SHORT SETUP: Price in Upper Zone + RSI High + Bearish Candle
    elif position == "UPPER":
        if rsi > RSI_HIGH:
            if current_price < prev_close:
                candle_body = prev_close - current_price
                if candle_body > (prev_close * 0.002):
                    signal = "SHORT"

    if signal:
        return signal, "MATCH", details
    
    return None, "NO_PATTERN", details

def send_telegram_message(message):
    """Send alert to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials missing. Logging only.")
        logger.info(f"🚨 ALERT: {message}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("Telegram message sent successfully.")
        else:
            logger.error(f"Telegram API Error: {response.text}")
    except Exception as e:
        logger.error(f"Telegram Request Failed: {e}")

# --- MAIN LOOP ---

def main():
    logger.info("🚀 Starting BB Scanner on Railway...")
    logger.info(f"Config: Interval={SCAN_INTERVAL_SECONDS}s, TF={TIMEFRAME}, MinBW={MIN_BANDWIDTH_PCT}")

    if not API_KEY or not API_SECRET:
        logger.error("❌ CRITICAL: Missing BINANCE_API_KEY or BINANCE_API_SECRET in Env Vars!")
        # Don't exit immediately in case user wants to see logs, but loop will fail safely
        time.sleep(10)

    client = Client(API_KEY, API_SECRET)

    # Test connection
    try:
        client.get_account()
        logger.info("✅ Connected to Binance API")
    except Exception as e:
        logger.error(f"❌ Binance Connection Failed: {e}")
        # Continue anyway to see if it's a permission issue vs key issue

    while True:
        start_time = time.time()
        logger.info(f"\n🔍 Starting Scan Cycle at {datetime.now().strftime('%H:%M:%S')}")

        symbols = get_top_symbols(client)
        if not symbols:
            logger.warning("No symbols found. Retrying in full interval...")
            time.sleep(SCAN_INTERVAL_SECONDS)
            continue

        logger.info(f"Scanning {len(symbols)} top volume symbols...")

        signals_found = 0
        rejection_counts = {
            "BANDWIDTH_FAIL": 0,
            "DEAD_ZONE": 0,
            "NO_PATTERN": 0,
            "RSI_FAIL": 0,
            "OTHER": 0
        }

        for symbol in symbols:
            closes, highs, lows = fetch_klines(client, symbol)

            if closes is None:
                continue

            signal, reason, details = check_signal(symbol, closes, highs, lows)

            if signal:
                msg = (
                    f"🚨 **{signal} SIGNAL** 🚨\n\n"
                    f"Coin: `{symbol}`\n"
                    f"Timeframe: `{TIMEFRAME}`\n"
                    f"Details: {details}\n"
                    f"Price: `{closes[-1]}`"
                )
                send_telegram_message(msg)
                signals_found += 1
            else:
                # Track rejections for diagnostics
                if reason in rejection_counts:
                    rejection_counts[reason] += 1
                else:
                    rejection_counts["OTHER"] += 1

        elapsed = time.time() - start_time
        logger.info(f"✅ Cycle Complete. Found {signals_found} signals.")
        logger.info(f"📊 Rejections: BW={rejection_counts['BANDWIDTH_FAIL']} | "
                    f"Zone={rejection_counts['DEAD_ZONE']} | "
                    f"Pat={rejection_counts['NO_PATTERN']}")

        # Sleep until next cycle
        sleep_time = max(0, SCAN_INTERVAL_SECONDS - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

if __name__ == "__main__":
    main()
