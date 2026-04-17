import os
import time
import logging
import statistics
import requests
import threading
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Try importing Flask for the web server, ignore if missing
try:
    from flask import Flask
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# --- CONFIGURATION ---
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

SCAN_INTERVAL_SECONDS = int(os.getenv('SCAN_INTERVAL', '300'))
TIMEFRAME = os.getenv('TIMEFRAME', '15m')
MIN_BANDWIDTH_PCT = float(os.getenv('MIN_BANDWIDTH', '0.008'))
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
    try:
        tickers = client.get_ticker()
        usdt_pairs = [
            t for t in tickers 
            if t['symbol'].endswith('USDT') and float(t['quoteVolume']) > 1000000
        ]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
        return [t['symbol'] for t in sorted_pairs[:limit]]
    except Exception as e:
        logger.error(f"Error fetching symbols: {e}")
        return []

def fetch_klines(client, symbol, interval=TIMEFRAME, lookback=50):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=lookback)
        if not klines:
            return None, None, None
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        return closes, highs, lows
    except BinanceAPIException as e:
        if e.code == -1121:
            return None, None, None
        logger.warning(f"API Error for {symbol}: {e}")
        return None, None, None
    except Exception as e:
        logger.warning(f"Data error for {symbol}: {e}")
        return None, None, None

def calculate_bb(closes, period=20, std_dev=2):
    if len(closes) < period:
        return None, None, None
    ma = statistics.mean(closes[-period:])
    std = statistics.stdev(closes[-period:])
    upper = ma + (std_dev * std)
    lower = ma - (std_dev * std)
    bandwidth = (upper - lower) / ma if ma != 0 else 0
    return upper, lower, bandwidth

def calculate_rsi(closes, period=14):
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
    if not closes or len(closes) < 20:
        return None, "INSUFFICIENT_DATA", ""

    current_price = closes[-1]
    prev_close = closes[-2]
    
    upper, lower, bandwidth = calculate_bb(closes)
    rsi = calculate_rsi(closes)
    
    if upper is None or lower is None:
        return None, "CALC_ERROR", ""

    mid = (upper + lower) / 2
    range_size = upper - lower
    
    if bandwidth < MIN_BANDWIDTH_PCT:
        return None, "BANDWIDTH_FAIL", f"BW:{bandwidth:.4f} < {MIN_BANDWIDTH_PCT}"
    
    lower_zone_threshold = lower + (range_size * 0.2)
    upper_zone_threshold = upper - (range_size * 0.2)
    
    position = "MIDDLE"
    if lower <= current_price <= lower_zone_threshold:
        position = "LOWER"
    elif upper_zone_threshold <= current_price <= upper:
        position = "UPPER"
    
    if position == "MIDDLE":
        return None, "DEAD_ZONE", f"Price:{current_price} Mid:{mid:.2f}"

    signal = None
    details = f"RSI:{rsi:.1f} BW:{bandwidth:.4f} Pos:{position}"

    if position == "LOWER":
        if rsi < RSI_LOW:
            if current_price > prev_close:
                candle_body = current_price - prev_close
                if candle_body > (prev_close * 0.002):
                    signal = "LONG"
    
    elif position == "UPPER":
        if rsi > RSI_HIGH:
            if current_price < prev_close:
                candle_body = prev_close - current_price
                if candle_body > (prev_close * 0.002):
                    signal = "SHORT"

    if signal:
        return signal, "MATCH", details
    
    return None, "NO_PATTERN", details

def send_discord_message(signal, symbol, details, price):
    if not DISCORD_WEBHOOK_URL:
        return

    # Calculate mock SL and TP for the message format
    sl_pct = 0.002
    tp1_pct = 0.01
    tp2_pct = 0.015
    
    if signal == "LONG":
        sl = price * (1 - sl_pct)
        tp1 = price * (1 + tp1_pct)
        tp2 = price * (1 + tp2_pct)
        direction = "LONG"
    else:
        sl = price * (1 + sl_pct)
        tp1 = price * (1 - tp1_pct)
        tp2 = price * (1 - tp2_pct)
        direction = "SHORT"

    # Format the message exactly as requested (Text Block)
    content = (
        f"**BB SCANNER | NEW SIGNAL | {direction} {symbol} | UPPER BAND BREAKOUT PULLBACK**\n"
        f"  {direction}   {symbol}\n"
        f"  Upper Band Breakout Pullback\n"
        f"  BB(20,2)  |  {TIMEFRAME}  |  Binance Spot\n"
        f"  --------------------------------------------\n"
        f"  Entry             : {price:.5f}\n"
        f"  Stop Loss         : {sl:.5f}   ({sl_pct*100:.2f}% risk)\n"
        f"  TP1  Fib 1.272    : {tp1:.5f}\n"
        f"  TP2  Fib 1.618    : {tp2:.5f}\n"
        f"  BB-Touch Exit     : DYNAMIC\n"
        f"  --------------------------------------------\n"
        f"  Details           : {details}\n"
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"  BB Scanner  |  For informational use only"
    )

    payload = {
        "content": content,
        "username": "BB Scanner"
    }
    
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        logger.info(f"Discord message sent for {symbol}")
    except Exception as e:
        logger.error(f"Discord Error: {e}")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Telegram Error: {e}")

# --- TINY WEB SERVER FOR RENDER ---
def run_server():
    if not FLASK_AVAILABLE:
        logger.warning("Flask not installed. Install 'flask' in requirements.txt to keep Render awake.")
        return
    
    app = Flask(__name__)
    
    @app.route('/')
    def home():
        return "BB Scanner is running. Check logs for signals."
    
    @app.route('/health')
    def health():
        return "OK", 200

    # Run on port 8080 (Render default)
    try:
        app.run(host='0.0.0.0', port=8080)
    except Exception as e:
        logger.error(f"Server error: {e}")

# --- MAIN LOOP ---

def main():
    logger.info("Starting BB Scanner...")
    logger.info(f"Config: Interval={SCAN_INTERVAL_SECONDS}s, TF={TIMEFRAME}, MinBW={MIN_BANDWIDTH_PCT}")

    # Start Web Server in a separate thread to keep Render happy
    if FLASK_AVAILABLE:
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        logger.info("Web server started on port 8080")

    client = None
    if API_KEY and API_SECRET:
        try:
            client = Client(API_KEY, API_SECRET)
            client.get_account()
            logger.info("Connected to Binance API")
        except Exception as e:
            logger.error(f"Binance Connection Issue: {e}")
            logger.info("Running in limited mode.")
    else:
        logger.warning("No API Keys found. Running in read-only public mode (may be rate limited).")
        # Initialize client without keys for public data (klines)
        try:
            client = Client()
        except Exception as e:
            logger.error(f"Failed to initialize public client: {e}")

    while True:
        start_time = time.time()
        logger.info(f"Starting Scan Cycle at {datetime.now().strftime('%H:%M:%S')}")

        if not client:
            logger.warning("No valid client. Skipping cycle.")
            time.sleep(SCAN_INTERVAL_SECONDS)
            continue

        try:
            symbols = get_top_symbols(client)
        except Exception as e:
            logger.error(f"Failed to get symbols: {e}")
            symbols = []

        if not symbols:
            logger.warning("No symbols found. Retrying...")
            time.sleep(SCAN_INTERVAL_SECONDS)
            continue

        logger.info(f"Scanning {len(symbols)} symbols...")
        signals_found = 0

        for symbol in symbols:
            try:
                closes, highs, lows = fetch_klines(client, symbol)
            except Exception as e:
                continue

            if closes is None:
                continue

            signal, reason, details = check_signal(symbol, closes, highs, lows)

            if signal:
                price = closes[-1]
                msg = f"SIGNAL ALERT [{signal}] {symbol} @ {price} | {details}"
                
                # Send to Telegram
                send_telegram_message(msg)
                
                # Send to Discord with detailed format
                send_discord_message(signal, symbol, details, price)
                
                logger.info(f"Signal Found: {symbol} ({signal})")
                signals_found += 1

        elapsed = time.time() - start_time
        logger.info(f"Cycle Complete. Found {signals_found} signals. Took {elapsed:.2f}s")

        sleep_time = max(0, SCAN_INTERVAL_SECONDS - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

if __name__ == "__main__":
    main()
