import os
import time
import logging
import statistics
import requests
import threading
import json
import math
from datetime import datetime
from flask import Flask, render_template_string
from binance.client import Client
from binance.exceptions import BinanceAPIException
import matplotlib
matplotlib.use('Agg') # Non-interactive backend for servers
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

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

# Paper Trading Config
INITIAL_BALANCE = 10000.0
RISK_PER_TRADE = 0.02  # 2%
LEVERAGE = 30
MAX_OPEN_TRADES = 5
DATA_FILE = 'paper_trades.json'

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- GLOBAL STATE ---
signal_history = []
MAX_HISTORY = 50
portfolio = {
    "balance": INITIAL_BALANCE,
    "open_trades": [],
    "closed_trades": [],
    "total_pnl": 0.0,
    "win_count": 0,
    "loss_count": 0
}

# Load state if exists
if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, 'r') as f:
            saved_data = json.load(f)
            portfolio.update(saved_data)
            logger.info(f"Loaded portfolio state. Balance: ${portfolio['balance']:.2f}")
    except Exception as e:
        logger.error(f"Failed to load state: {e}")

def save_state():
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(portfolio, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")

# --- FLASK WEB SERVER ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Azalyst Alpha X | Dashboard</title>
    <meta http-equiv="refresh" content="10">
    <style>
        body { background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; }
        h1, h2 { color: #ffffff; border-bottom: 1px solid #333; padding-bottom: 10px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background-color: #1e1e1e; padding: 20px; border-radius: 8px; border: 1px solid #333; text-align: center; }
        .stat-value { font-size: 2em; font-weight: bold; margin-top: 10px; }
        .green { color: #00ff00; }
        .red { color: #ff4444; }
        .white { color: #ffffff; }
        
        .section { margin-bottom: 40px; }
        .trade-box { background-color: #1e1e1e; border: 1px solid #333; padding: 15px; margin-bottom: 10px; border-radius: 4px; }
        .trade-header { display: flex; justify-content: space-between; font-weight: bold; margin-bottom: 10px; }
        .trade-details { font-family: 'Courier New', monospace; font-size: 0.9em; white-space: pre-wrap; color: #ccc; }
        
        .signal-box { background-color: #2d2d2d; border-left: 5px solid #555; padding: 15px; margin-bottom: 15px; white-space: pre-wrap; font-family: 'Courier New', monospace; }
        .long { border-left-color: #00ff00; }
        .short { border-left-color: #ff0000; }
    </style>
</head>
<body>
    <h1>AZALYST ALPHA X | DASHBOARD</h1>
    <p>Live Paper Trading & Signal Monitor</p>

    <div class="stats-grid">
        <div class="stat-card">
            <div>Balance (USDT)</div>
            <div class="stat-value white">${{ "%.2f"|format(balance) }}</div>
        </div>
        <div class="stat-card">
            <div>Total PnL</div>
            <div class="stat-value {{ 'green' if total_pnl >= 0 else 'red' }}">${{ "%.2f"|format(total_pnl) }}</div>
        </div>
        <div class="stat-card">
            <div>Open Trades</div>
            <div class="stat-value white">{{ open_count }} / {{ max_trades }}</div>
        </div>
        <div class="stat-card">
            <div>Win Rate</div>
            <div class="stat-value white">{{ win_rate }}%</div>
        </div>
    </div>

    <div class="section">
        <h2>Open Positions</h2>
        {% if not open_trades %}
            <p>No active positions.</p>
        {% endif %}
        {% for trade in open_trades %}
            <div class="trade-box">
                <div class="trade-header">
                    <span>{{ trade.type }} {{ trade.symbol }}</span>
                    <span class="{{ 'green' if trade.unrealized_pnl >= 0 else 'red' }}">
                        {{ "%.2f"|format(trade.unrealized_pnl) }} USDT
                    </span>
                </div>
                <div class="trade-details">
Entry: {{ trade.entry_price }} | SL: {{ trade.sl_price }} | TP1: {{ trade.tp1 }}
Current PnL: {{ "%.2f"|format(trade.unrealized_pnl) }}
                </div>
            </div>
        {% endfor %}
    </div>

    <div class="section">
        <h2>Recent Signals</h2>
        {% if not signals %}
            <p>No signals detected yet.</p>
        {% endif %}
        {% for signal in signals %}
            <div class="signal-box {{ signal.type_class }}">
                <pre>{{ signal.content }}</pre>
            </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    # Calculate stats for template
    win_rate = 0
    if portfolio['win_count'] + portfolio['loss_count'] > 0:
        win_rate = (portfolio['win_count'] / (portfolio['win_count'] + portfolio['loss_count'])) * 100
    
    # Format open trades for display
    open_trades_display = []
    for t in portfolio['open_trades']:
        # Simple unrealized PnL estimation (mocked for web display if no live price fetch here)
        # In a real app, you'd fetch current prices here. 
        # For now, we show entry info.
        open_trades_display.append(t)

    return render_template_string(HTML_TEMPLATE, 
        balance=portfolio['balance'],
        total_pnl=portfolio['total_pnl'],
        open_count=len(portfolio['open_trades']),
        max_trades=MAX_OPEN_TRADES,
        win_rate=f"{win_rate:.1f}",
        open_trades=open_trades_display,
        signals=reversed(signal_history[-10:])
    )

def run_web_server():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# --- SCANNER & TRADING LOGIC ---

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
            sig_type = "UPPER BAND BREAKOUT PULLBACK" # Naming convention from your logs
            
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
            "highs": highs,
            "lows": lows,
            "closes": closes
        }
    return None

def calculate_targets(entry, direction, highs, lows):
    # Simple Swing High/Low logic for TP
    swing_range = max(highs[-20:]) - min(lows[-20:])
    if swing_range == 0: swing_range = entry * 0.01
    
    sl_dist = swing_range * 0.5 # Tighter SL based on recent volatility
    if sl_dist < entry * 0.001: sl_dist = entry * 0.001

    if direction == "LONG":
        sl = entry - sl_dist
        tp1 = entry + (sl_dist * 1.272)
        tp2 = entry + (sl_dist * 1.618)
    else:
        sl = entry + sl_dist
        tp1 = entry - (sl_dist * 1.272)
        tp2 = entry - (sl_dist * 1.618)
        
    return sl, tp1, tp2, sl_dist

def generate_chart(symbol, sig, filename="chart.png"):
    try:
        closes = sig['closes']
        highs = sig['highs']
        lows = sig['lows']
        periods = list(range(len(closes)))
        
        fig, ax = plt.subplots(figsize=(10, 6), facecolor='#121212')
        ax.set_facecolor('#121212')
        
        # Plot Price
        ax.plot(periods, closes, label='Price', color='#ffffff', linewidth=1.5)
        
        # Plot BB
        upper, lower, _ = calculate_bb(closes)
        mid = (upper + lower) / 2
        # Simplified BB plot for last 20 periods for visual clarity
        bb_period = 20
        if len(closes) >= bb_period:
            # Recalculate dynamically for plot smoothness would be complex, 
            # just plotting static lines for demo or approximating
            # For a true chart, we'd need full history of BB values. 
            # Here we plot horizontal lines at current levels for simplicity in this snippet
            ax.axhline(y=upper, color='#00ff00', linestyle='--', alpha=0.5, label='Upper BB')
            ax.axhline(y=lower, color='#ff0000', linestyle='--', alpha=0.5, label='Lower BB')
            ax.axhline(y=mid, color='#888888', linestyle=':', alpha=0.5, label='Mid BB')

        # Mark Entry
        ax.scatter(len(closes)-1, sig['price'], color='#ffff00', s=100, zorder=5, marker='*')
        
        ax.set_title(f"{symbol} - {sig['type']} Signal", color='white')
        ax.legend(facecolor='#1e1e1e', labelcolor='white')
        ax.grid(True, color='#333333')
        
        # Save
        plt.savefig(filename, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close()
        return filename
    except Exception as e:
        logger.error(f"Chart generation failed: {e}")
        return None

def format_signal_message(sig, sl, tp1, tp2):
    entry = sig['price']
    risk_pct = ((entry - sl) / entry * 100) if sig['type'] == "LONG" else ((sl - entry) / entry * 100)
    
    msg = (
        f"BB SCANNER | NEW SIGNAL | {sig['type']} {sig['symbol']} | {sig['pattern']}\n"
        f"  {sig['type']}   {sig['symbol']}\n"
        f"  {sig['pattern']}\n"
        f"  BB(20,2)  |  {TIMEFRAME}  |  Binance Spot\n"
        f"  --------------------------------------------\n"
        f"  Entry             : {entry:.5f}\n"
        f"  Stop Loss         : {sl:.5f}   ({risk_pct:.2f}% risk)\n"
        f"  TP1  Fib 1.272    : {tp1:.5f}\n"
        f"  TP2  Fib 1.618    : {tp2:.5f}\n"
        f"  BB-Touch Exit     : DYNAMIC\n"
        f"  --------------------------------------------\n"
        f"  Details           : RSI:{sig['rsi']:.1f} BW:{sig['bw']:.4f} Pos:LOWER\n"
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"  BB Scanner  |  For informational use only"
    )
    return msg

def send_discord_message(message, chart_path=None):
    if not DISCORD_WEBHOOK_URL:
        logger.info(f"Discord disabled. Signal: {message[:50]}...")
        return
    
    payload = {"content": f"```\n{message}\n```"}
    
    files = {}
    if chart_path and os.path.exists(chart_path):
        files['file'] = open(chart_path, 'rb')
    
    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, files=files if files else None, timeout=10)
        if chart_path and os.path.exists(chart_path):
            files['file'].close()
            
        if resp.status_code == 204:
            logger.info(f"Discord message sent for {message.split()[3]}")
        else:
            logger.error(f"Discord error: {resp.text}")
    except Exception as e:
        logger.error(f"Discord request failed: {e}")

def execute_trade(sig, sl, tp1, tp2):
    global portfolio
    
    if len(portfolio['open_trades']) >= MAX_OPEN_TRADES:
        logger.warning("Max open trades reached. Skipping execution.")
        return False
    
    # Check duplicate
    for t in portfolio['open_trades']:
        if t['symbol'] == sig['symbol']:
            return False

    # Size calculation
    risk_amount = portfolio['balance'] * RISK_PER_TRADE
    dist_pct = abs(sig['price'] - sl) / sig['price']
    if dist_pct == 0: dist_pct = 0.001
    
    position_size_usd = risk_amount / dist_pct
    margin = position_size_usd / LEVERAGE
    
    if margin > portfolio['balance'] * 0.25:
        margin = portfolio['balance'] * 0.25
        
    trade = {
        "id": f"T{len(portfolio['closed_trades']) + len(portfolio['open_trades']) + 1:04d}",
        "symbol": sig['symbol'],
        "type": sig['type'],
        "entry_price": sig['price'],
        "sl_price": sl,
        "tp1": tp1,
        "tp2": tp2,
        "margin": margin,
        "size_usd": position_size_usd,
        "quantity": position_size_usd / sig['price'],
        "time": datetime.now().timestamp(),
        "extended": False # For BB touch exit logic
    }
    
    portfolio['open_trades'].append(trade)
    save_state()
    logger.info(f"Opened {sig['type']} {sig['symbol']} @ {sig['price']}")
    return True

def monitor_positions(client):
    global portfolio
    updated = False
    
    for trade in portfolio['open_trades'][:]:
        try:
            ticker = client.get_symbol_ticker(symbol=trade['symbol'])
            current_price = float(ticker['price'])
            
            pnl = 0
            if trade['type'] == "LONG":
                pnl = (current_price - trade['entry_price']) * trade['quantity']
                # Check SL
                if current_price <= trade['sl_price']:
                    close_trade(trade, current_price, "STOP LOSS", -1 * (trade['entry_price'] - trade['sl_price']) * trade['quantity'])
                    portfolio['open_trades'].remove(trade)
                    updated = True
                    continue
                # Check TP
                elif current_price >= trade['tp2']:
                    close_trade(trade, current_price, "TAKE PROFIT 2", pnl)
                    portfolio['open_trades'].remove(trade)
                    updated = True
                    continue
                # Check BB Touch Exit (Simplified: if price went high then came back to entry/BB)
                # Logic: If price extended > 1% then drops back to near entry
                if current_price > trade['entry_price'] * 1.01:
                    trade['extended'] = True
                if trade['extended'] and current_price <= trade['entry_price'] * 1.002:
                     close_trade(trade, current_price, "BB TOUCH EXIT", pnl)
                     portfolio['open_trades'].remove(trade)
                     updated = True
                     continue

            else: # SHORT
                pnl = (trade['entry_price'] - current_price) * trade['quantity']
                if current_price >= trade['sl_price']:
                    close_trade(trade, current_price, "STOP LOSS", -1 * (trade['sl_price'] - trade['entry_price']) * trade['quantity'])
                    portfolio['open_trades'].remove(trade)
                    updated = True
                    continue
                elif current_price <= trade['tp2']:
                    close_trade(trade, current_price, "TAKE PROFIT 2", pnl)
                    portfolio['open_trades'].remove(trade)
                    updated = True
                    continue
                
                if current_price < trade['entry_price'] * 0.99:
                    trade['extended'] = True
                if trade['extended'] and current_price >= trade['entry_price'] * 0.998:
                    close_trade(trade, current_price, "BB TOUCH EXIT", pnl)
                    portfolio['open_trades'].remove(trade)
                    updated = True
                    continue
            
            trade['unrealized_pnl'] = pnl # Update for web display
            
        except Exception as e:
            logger.error(f"Error monitoring {trade['symbol']}: {e}")
            
    if updated:
        save_state()

def close_trade(trade, exit_price, reason, pnl):
    global portfolio
    portfolio['balance'] += pnl
    portfolio['total_pnl'] += pnl
    
    closed_trade = trade.copy()
    closed_trade['exit_price'] = exit_price
    closed_trade['exit_reason'] = reason
    closed_trade['realized_pnl'] = pnl
    closed_trade['close_time'] = datetime.now().timestamp()
    
    if pnl > 0:
        portfolio['win_count'] += 1
    else:
        portfolio['loss_count'] += 1
        
    portfolio['closed_trades'].append(closed_trade)
    
    # Send Close Alert
    msg = (
        f"BB SCANNER | TRADE CLOSED | {trade['id']} {trade['symbol']} | PnL ${pnl:.2f}\n"
        f"  CLOSED   {trade['symbol']}   ({trade['type']})   {'WIN' if pnl > 0 else 'LOSS'}\n"
        f"  {reason}\n"
        f"  ----------------------------------------\n"
        f"  Entry: {trade['entry_price']} | Exit: {exit_price}\n"
        f"  PnL: ${pnl:.2f}\n"
        f"  Balance: ${portfolio['balance']:.2f}\n"
        f"  Win Rate: {portfolio['win_count']}/{portfolio['win_count']+portfolio['loss_count']}"
    )
    send_discord_message(msg) # No chart for close usually
    logger.info(f"Closed {trade['symbol']}: {reason} (${pnl:.2f})")

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

        if client:
            # 1. Monitor Existing Positions First
            monitor_positions(client)
            
            # 2. Scan for New Signals
            try:
                symbols = get_top_symbols(client)
            except Exception:
                symbols = []

            if symbols:
                for symbol in symbols:
                    # Skip if already in open trades
                    if any(t['symbol'] == symbol for t in portfolio['open_trades']):
                        continue
                        
                    data = fetch_klines(client, symbol)
                    if data[0] is None: continue
                    
                    closes, highs, lows, times = data
                    sig = check_signal(symbol, closes, highs, lows)
                    
                    if sig:
                        sl, tp1, tp2, _ = calculate_targets(sig['price'], sig['type'], highs, lows)
                        msg = format_signal_message(sig, sl, tp1, tp2)
                        
                        # Generate Chart
                        chart_file = generate_chart(symbol, sig)
                        
                        # Dispatch
                        send_discord_message(msg, chart_file)
                        
                        # Store for Web
                        signal_history.append({
                            "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            "type_class": "long" if sig['type'] == "LONG" else "short",
                            "content": msg
                        })
                        if len(signal_history) > MAX_HISTORY:
                            signal_history.pop(0)
                            
                        # Execute Paper Trade
                        execute_trade(sig, sl, tp1, tp2)
                        
                        logger.info(f"Signal Found: {sig['symbol']} ({sig['type']})")

        elapsed = time.time() - start_time
        sleep_time = max(0, SCAN_INTERVAL_SECONDS - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

if __name__ == "__main__":
    # Start Web Server
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # Run Scanner
    scanner_loop()
