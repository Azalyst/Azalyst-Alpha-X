import os
import time
import logging
import statistics
import requests
import threading
import io
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for servers
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from flask import Flask, render_template_string
from binance.client import Client
from binance.exceptions import BinanceAPIException

# --- CONFIGURATION ---
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

SCAN_INTERVAL_SECONDS = int(os.getenv('SCAN_INTERVAL', '300'))
TIMEFRAME = os.getenv('TIMEFRAME', '15m')
MIN_BANDWIDTH_PCT = float(os.getenv('MIN_BANDWIDTH', '0.008'))
RSI_LOW = int(os.getenv('RSI_LOW', '45'))
RSI_HIGH = int(os.getenv('RSI_HIGH', '65'))
TOP_N_SYMBOLS = int(os.getenv('TOP_N_SYMBOLS', '100'))

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- GLOBAL SIGNAL STORE FOR WEB PORTAL ---
signal_history = []
MAX_HISTORY = 50

# --- FLASK WEB SERVER ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Azalyst Alpha X | Live Signals</title>
    <meta http-equiv="refresh" content="10">
    <style>
        body { background-color: #0f0f0f; color: #cfcfcf; font-family: 'Courier New', Courier, monospace; padding: 20px; }
        h1 { color: #ffffff; border-bottom: 1px solid #333; padding-bottom: 10px; font-size: 1.5em; letter-spacing: 1px; }
        .status { color: #00ff00; font-size: 0.9em; margin-bottom: 20px; }
        .signal-box { background-color: #1a1a1a; border: 1px solid #333; padding: 15px; margin-bottom: 15px; white-space: pre-wrap; border-radius: 2px; font-size: 0.85em; }
        .long { border-left: 4px solid #00ff00; }
        .short { border-left: 4px solid #ff0000; }
        .timestamp { color: #666; font-size: 0.8em; margin-bottom: 5px; }
        .header { font-weight: bold; color: #fff; }
    </style>
</head>
<body>
    <h1>AZALYST ALPHA X | LIVE FEED</h1>
    <div class="status">SYSTEM OPERATIONAL | REFRESHING EVERY 10s</div>
    {% if not signals %}
        <p style="color: #666;">Waiting for validated setups...</p>
    {% endif %}
    {% for signal in signals %}
        <div class="signal-box {{ signal.type_class }}">
            <div class="timestamp">{{ signal.time }}</div>
            <div class="header">{{ signal.headline }}</div>
            <pre>{{ signal.content }}</pre>
        </div>
    {% endfor %}
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, signals=reversed(signal_history))

def run_web_server():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

# --- SCANNER LOGIC ---

def get_top_symbols(client, limit=TOP_N_SYMBOLS):
    try:
        tickers = client.get_ticker()
        usdt_pairs = [t for t in tickers if t['symbol'].endswith('USDT') and float(t['quoteVolume']) > 1000000]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
        return [t['symbol'] for t in sorted_pairs[:limit]]
    except Exception as e:
        logger.error(f"Error fetching symbols: {e}")
        return []

def fetch_klines(client, symbol, interval=TIMEFRAME, lookback=50):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=lookback)
        if not klines: return None, None, None
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        times = [k[0] for k in klines]
        return closes, highs, lows, times
    except BinanceAPIException as e:
        if e.code == -1121: return None, None, None, None
        return None, None, None, None
    except Exception:
        return None, None, None, None

def calculate_bb(closes, period=20, std_dev=2):
    if len(closes) < period: return None, None, None
    ma = statistics.mean(closes[-period:])
    std = statistics.stdev(closes[-period:])
    upper = ma + (std_dev * std)
    lower = ma - (std_dev * std)
    bandwidth = (upper - lower) / ma if ma != 0 else 0
    return upper, lower, bandwidth

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1: return 50
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff >= 0: gains.append(diff); losses.append(0)
        else: gains.append(0); losses.append(abs(diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def check_signal(symbol, closes, highs, lows):
    if not closes or len(closes) < 20: return None
    current_price = closes[-1]
    prev_close = closes[-2]
    upper, lower, bandwidth = calculate_bb(closes)
    rsi = calculate_rsi(closes)
    if upper is None: return None
    if bandwidth < MIN_BANDWIDTH_PCT: return None
    
    mid = (upper + lower) / 2
    range_size = upper - lower
    lower_zone_threshold = lower + (range_size * 0.2)
    upper_zone_threshold = upper - (range_size * 0.2)
    
    position = "MIDDLE"
    if lower <= current_price <= lower_zone_threshold: position = "LOWER"
    elif upper_zone_threshold <= current_price <= upper: position = "UPPER"
    
    if position == "MIDDLE": return None

    signal = None
    sig_type = ""
    
    if position == "LOWER" and rsi < RSI_LOW and current_price > prev_close:
        if (current_price - prev_close) > (prev_close * 0.002):
            signal = "LONG"
            sig_type = "UPPER BAND BREAKOUT PULLBACK" # Keeping your naming convention
            
    elif position == "UPPER" and rsi > RSI_HIGH and current_price < prev_close:
        if (prev_close - current_price) > (prev_close * 0.002):
            signal = "SHORT"
            sig_type = "LOWER BAND BREAKDOWN PULLBACK"

    if signal:
        return {
            "type": signal,
            "symbol": symbol,
            "pattern": sig_type,
            "price": current_price,
            "rsi": rsi,
            "bw": bandwidth,
            "closes": closes,
            "upper": upper,
            "lower": lower,
            "mid": mid
        }
    return None

def generate_chart(sig):
    """Generates a BB chart image and returns a file-like object"""
    try:
        closes = sig['closes']
        periods = list(range(len(closes)))
        
        fig, ax = plt.subplots(figsize=(10, 5), facecolor='#0f0f0f')
        ax.set_facecolor('#0f0f0f')
        
        # Plot Price
        ax.plot(periods, closes, label='Price', color='#ffffff', linewidth=1.5)
        
        # Plot Bands
        upper_band = [sig['upper']] * len(closes)
        lower_band = [sig['lower']] * len(closes)
        mid_band = [sig['mid']] * len(closes)
        
        ax.plot(periods, upper_band, label='Upper BB', color='#00ff00' if sig['type']=='LONG' else '#ff0000', linestyle='--', alpha=0.7)
        ax.plot(periods, lower_band, label='Lower BB', color='#00ff00' if sig['type']=='LONG' else '#ff0000', linestyle='--', alpha=0.7)
        ax.plot(periods, mid_band, label='Mid BB', color='#555555', linestyle=':', alpha=0.5)
        
        # Highlight Entry
        ax.scatter(len(closes)-1, sig['price'], color='#ffff00', s=100, zorder=5, marker='*')
        
        # Styling
        ax.set_title(f"{sig['symbol']} ({sig['type']}) - {TIMEFRAME}", color='#ffffff', pad=10)
        ax.legend(facecolor='#1a1a1a', edgecolor='#333', labelcolor='#cccccc')
        ax.grid(True, color='#222222', linestyle='-', linewidth=0.5)
        
        # Tick colors
        ax.tick_params(colors='#888888')
        for spine in ax.spines.values():
            spine.set_color('#333333')
            
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
        buf.seek(0)
        plt.close(fig)
        return buf
    except Exception as e:
        logger.error(f"Chart generation failed: {e}")
        return None

def format_signal_message(sig):
    entry = sig['price']
    sl_dist = entry * 0.002
    stop_loss = entry - sl_dist if sig['type'] == "LONG" else entry + sl_dist
    tp1 = entry + (sl_dist * 5) if sig['type'] == "LONG" else entry - (sl_dist * 5)
    tp2 = entry + (sl_dist * 8) if sig['type'] == "LONG" else entry - (sl_dist * 8)
    
    msg = (
        f"BB SCANNER | NEW SIGNAL | {sig['type']} {sig['symbol']} | {sig['pattern']}\n"
        f"  {sig['type']}   {sig['symbol']}\n"
        f"  {sig['pattern']}\n"
        f"  BB(20,2)  |  {TIMEFRAME}  |  Binance Spot\n"
        f"  --------------------------------------------\n"
        f"  Entry             : {entry:.5f}\n"
        f"  Stop Loss         : {stop_loss:.5f}   ({(sl_dist/entry)*100:.2f}% risk)\n"
        f"  TP1  Fib 1.272    : {tp1:.5f}\n"
        f"  TP2  Fib 1.618    : {tp2:.5f}\n"
        f"  BB-Touch Exit     : DYNAMIC\n"
        f"  --------------------------------------------\n"
        f"  Details           : RSI:{sig['rsi']:.1f} BW:{sig['bw']:.4f} Pos:LOWER\n"
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"  BB Scanner  |  For informational use only"
    )
    return msg

def send_discord_message(message, chart_buf=None):
    if not DISCORD_WEBHOOK_URL:
        logger.info(f"Discord disabled. Signal: {message[:50]}...")
        return
    
    payload = {"content": f"```\n{message}\n```"}
    
    try:
        if chart_buf:
            files = {'file': ('chart.png', chart_buf, 'image/png')}
            resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, files=files, timeout=10)
        else:
            resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
            
        if resp.status_code == 204:
            logger.info(f"Discord message sent for {message.split()[3]}")
        else:
            logger.error(f"Discord error: {resp.text}")
    except Exception as e:
        logger.error(f"Discord request failed: {e}")

def store_signal_web(sig, raw_text):
    global signal_history
    headline = f"{sig['type']} {sig['symbol']} | {sig['pattern']}"
    entry = {
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "type_class": "long" if sig['type'] == "LONG" else "short",
        "headline": headline,
        "content": raw_text
    }
    signal_history.append(entry)
    if len(signal_history) > MAX_HISTORY:
        signal_history.pop(0)

# --- MAIN LOOP ---

def scanner_loop():
    logger.info("Starting Azalyst Alpha X Scanner...")
    
    client = None
    try:
        client = Client(API_KEY, API_SECRET)
        client.get_account()
        logger.info("Connected to Binance API")
    except Exception as e:
        logger.error(f"Binance Connection Issue: {e}")
        logger.info("Running in limited mode.")

    while True:
        start_time = time.time()
        logger.info(f"Starting Scan Cycle at {datetime.now().strftime('%H:%M:%S')}")

        if not client:
            time.sleep(SCAN_INTERVAL_SECONDS)
            continue

        try:
            symbols = get_top_symbols(client)
        except Exception:
            symbols = []

        if not symbols:
            time.sleep(SCAN_INTERVAL_SECONDS)
            continue

        for symbol in symbols:
            closes, highs, lows, times = fetch_klines(client, symbol)
            if closes is None: continue

            sig = check_signal(symbol, closes, highs, lows)
            
            if sig:
                msg = format_signal_message(sig)
                chart = generate_chart(sig)
                
                # 1. Send to Discord with Chart
                send_discord_message(msg, chart)
                
                # 2. Store for Web Portal (Text only for web)
                store_signal_web(sig, msg)
                
                logger.info(f"Signal Found: {sig['symbol']} ({sig['type']})")

        elapsed = time.time() - start_time
        sleep_time = max(0, SCAN_INTERVAL_SECONDS - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

if __name__ == "__main__":
    # Start Web Server in a separate thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # Run Scanner in main thread
    scanner_loop()
