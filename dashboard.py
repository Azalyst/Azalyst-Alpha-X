import json
import os
from datetime import datetime, timezone

TRADES_FILE = "paper_trades.json"
ANALYSIS_FILE = "qwen_analysis.json"

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}

def fmt_usd(v):
    if v is None: return "--"
    return f"${v:,.2f}"

def fmt_pct(v):
    if v is None: return "--%"
    return f"{'+' if v >= 0 else ''}{v:.2f}%"

def color_class(v):
    if v is None: return "neu"
    if v > 0: return "up"
    if v < 0: return "dn"
    return "neu"

def generate_html():
    trades_data = load_json(TRADES_FILE)
    analysis_data = load_json(ANALYSIS_FILE)
    
    balance = trades_data.get("balance", 10000.0)
    open_trades = trades_data.get("open_trades", [])
    closed_trades = sorted(trades_data.get("closed_trades", []), key=lambda x: x.get("id", ""), reverse=True)
    
    wins = [t for t in closed_trades if t.get("rpnl", 0) > 0]
    losses = [t for t in closed_trades if t.get("rpnl", 0) <= 0]
    win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0
    total_rpnl = sum([t.get("rpnl", 0) for t in closed_trades])
    total_upnl = sum([t.get("upnl", 0) for t in open_trades])
    total_return_pct = ((balance - 10000.0) / 10000.0) * 100
    
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # CSS and Base HTML
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Azalyst Alpha X</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html{font-size:13px}
body{background:#000;font-family:'Courier New',monospace;color:#ff6600;overflow-x:hidden;min-width:1100px}

/* ── TOP BAR ── */
.topbar{background:#ff6600;color:#000;display:flex;align-items:center;gap:12px;padding:5px 12px;font-weight:700;font-size:13px;position:sticky;top:0;z-index:100}
.logo{background:#000;color:#ff6600;padding:3px 12px;font-size:15px;font-weight:700;letter-spacing:.5px;white-space:nowrap}
.logo span{color:#fff;font-size:10px;font-weight:400;margin-left:5px}
.tabs{display:flex;gap:1px;margin-left:8px}
.tab{background:#cc5200;color:#000;padding:3px 16px;cursor:pointer;font-size:11px;font-weight:700;border:none;font-family:'Courier New',monospace;transition:background .1s}
.tab:hover{background:#e06000}
.tab.active{background:#fff;color:#000}
.topbar-right{margin-left:auto;display:flex;gap:16px;font-size:11px;align-items:center;white-space:nowrap}
.live-dot{color:#000;font-size:16px;animation:blink 1s step-end infinite}
@keyframes blink{50%{opacity:0}}

/* ── TICKER TAPE ── */
.tape{background:#111;padding:3px 0;overflow:hidden;white-space:nowrap;border-bottom:1px solid #222;font-size:11px}
.tape-inner{display:inline-flex;gap:0;will-change:transform;animation:scroll 30s linear infinite}
.tape-item{margin-right:32px;white-space:nowrap}
@keyframes scroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}

/* ── MAIN GRID ── */
.main{display:grid;gap:2px;background:#333;padding:2px}
.grid-2{grid-template-columns:1fr 1fr}
.grid-3{grid-template-columns:1fr 1fr 1fr}
.panel{background:#0a0a0a;padding:8px 10px;min-height:200px}
.panel-header{color:#ff6600;font-weight:700;font-size:11px;border-bottom:1px solid #333;padding-bottom:4px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center}
.cmd{color:#ffaa00;font-size:10px}
.span2{grid-column:span 2}
.span3{grid-column:span 3}

/* ── STAT BOXES ── */
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:7px}
.stat-box{background:#050505;border:1px solid #1a1a1a;padding:5px 8px}
.stat-label{color:#555;font-size:8px;text-transform:uppercase;letter-spacing:.4px}
.stat-val{font-size:15px;font-weight:700;margin:2px 0}
.stat-sub{font-size:8px;color:#333}

/* ── TABLES ── */
.row-header{display:flex;justify-content:space-between;font-size:8px;color:#555;border-bottom:1px solid #333;padding-bottom:3px;margin-bottom:3px}
.prow{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #0d0d0d;font-size:10px;border-radius:2px;background:#050505}
.prow:hover{background:#111}
.pcol{min-width:60px;text-align:right}
.pcol.left{text-align:left}
.pcol.wide{min-width:120px}

/* ── STATUS BAR ── */
.statusbar{background:#0a0a0a;border-top:1px solid #222;display:flex;justify-content:space-between;align-items:center;padding:3px 10px;font-size:9px;color:#444;gap:8px}

/* ── COLOR SEMANTICS ── */
.up{color:#00dd33}
.dn{color:#cc2200}
.neu{color:#cc7700}
.white{color:#fff}

/* ── PAGE VISIBILITY ── */
.page{display:none}
.page.active{display:block}

/* ── QWEN ANALYSIS ── */
.qwen-text{color:#bbb;font-size:11px;line-height:1.5;white-space:pre-wrap}
.qwen-action{color:#00ff41;font-weight:bold;margin-top:10px}
</style>
<script>
function switchTab(id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.getElementById('page-'+id).classList.add('active');
}
function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent = now.toISOString().substring(11, 19) + ' UTC';
}
setInterval(updateClock, 1000);
</script>
</head>
<body onload="updateClock()">

<div class="topbar">
  <div class="logo">AZALYST<span>ALPHA X | BB(200,1) SCANNER</span></div>
  <div class="tabs">
    <button class="tab active" id="tab-OVERVIEW" onclick="switchTab('OVERVIEW')">OVERVIEW</button>
    <button class="tab" id="tab-PORTFOLIO" onclick="switchTab('PORTFOLIO')">PORTFOLIO</button>
    <button class="tab" id="tab-QWEN" onclick="switchTab('QWEN')">QWEN AI INTELLIGENCE</button>
  </div>
  <div class="topbar-right">
    <span class="live-dot">●</span>
    <span id="clock">--:--:-- UTC</span>
    <span style="color:#00ff41">● ONLINE</span>
  </div>
</div>

<div class="tape">
  <div class="tape-inner">
"""

    # Populate tape with recent trades
    tape_items = []
    for t in closed_trades[:10]:
        sym = t.get("symbol", "").replace("/USDT", "")
        pnl = t.get("rpnl", 0)
        cls = "up" if pnl > 0 else "dn"
        tape_items.append(f'<span class="tape-item">{sym} <span class="{cls}">{fmt_usd(pnl)}</span></span>')
    
    tape_html = "".join(tape_items)
    # Duplicate for infinite scroll effect
    html += tape_html + tape_html
    html += """
  </div>
</div>
"""

    # ── PAGE: OVERVIEW ──
    html += f"""
<div id="page-OVERVIEW" class="page active">
  <div class="main grid-3">
    
    <div class="panel">
      <div class="panel-header">ALPHA X — SYSTEM STATUS</div>
      <div class="stat-grid">
        <div class="stat-box">
          <div class="stat-label">Balance (USDT)</div>
          <div class="stat-val {color_class(balance - 10000)}">{fmt_usd(balance)}</div>
          <div class="stat-sub">Starting: $10,000.00</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Total Return</div>
          <div class="stat-val {color_class(total_return_pct)}">{fmt_pct(total_return_pct)}</div>
          <div class="stat-sub">All-time</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Win Rate</div>
          <div class="stat-val {'up' if win_rate >= 50 else 'dn'}">{win_rate:.1f}%</div>
          <div class="stat-sub">{len(wins)}W / {len(losses)}L</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Total Trades</div>
          <div class="stat-val white">{len(closed_trades) + len(open_trades)}</div>
          <div class="stat-sub">{len(open_trades)} Open / {len(closed_trades)} Closed</div>
        </div>
      </div>
      
      <div style="margin-top:10px;font-size:10px;color:#888;">
        <div><strong>Strategy:</strong> Bollinger Band Reversion / Breakout</div>
        <div><strong>Parameters:</strong> Period 200, SD 1</div>
        <div><strong>Timeframe:</strong> 1m (with 1h/4h RSI Filter)</div>
        <div><strong>Leverage:</strong> 30x Paper Trading</div>
        <div><strong>Exchange:</strong> Binance Perpetual Futures</div>
      </div>
    </div>

    <div class="panel span2">
      <div class="panel-header">RECENT ACTIVITY — LATEST 10 CLOSED TRADES</div>
      <div class="row-header">
        <span class="pcol left">ID</span>
        <span class="pcol left wide">SYMBOL</span>
        <span class="pcol left wide">DIR</span>
        <span class="pcol">ENTRY</span>
        <span class="pcol">EXIT</span>
        <span class="pcol">PNL</span>
        <span class="pcol wide">REASON</span>
      </div>
"""
    
    for t in closed_trades[:10]:
        rpnl = t.get('rpnl', 0)
        dir_color = "up" if t.get('direction') == "LONG" else "dn"
        html += f"""
      <div class="prow">
        <span class="pcol left" style="color:#ff9900">{t.get('id')}</span>
        <span class="pcol left wide white">{t.get('symbol')}</span>
        <span class="pcol left wide {dir_color}">{t.get('direction')}</span>
        <span class="pcol">{t.get('entry')}</span>
        <span class="pcol">{t.get('close_price')}</span>
        <span class="pcol {color_class(rpnl)}">{fmt_usd(rpnl)}</span>
        <span class="pcol wide" style="color:#888">{t.get('close_reason')}</span>
      </div>
"""

    html += """
    </div>
  </div>
</div>
"""

    # ── PAGE: PORTFOLIO ──
    html += f"""
<div id="page-PORTFOLIO" class="page">
  <div class="main grid-1">
    
    <div class="panel">
      <div class="panel-header">OPEN POSITIONS <span class="cmd">Total: {len(open_trades)}</span></div>
      <div class="row-header">
        <span class="pcol left">ID</span>
        <span class="pcol left wide">SYMBOL</span>
        <span class="pcol left">DIR</span>
        <span class="pcol wide left">CONDITION</span>
        <span class="pcol">ENTRY</span>
        <span class="pcol">SL</span>
        <span class="pcol">TP1</span>
        <span class="pcol">NOTIONAL</span>
        <span class="pcol">UNREAL PNL</span>
      </div>
"""
    
    if not open_trades:
        html += '<div style="color:#555;font-size:10px;padding:10px 0;">No open positions at this time.</div>'
    
    for t in open_trades:
        upnl = t.get('upnl', 0)
        dir_color = "up" if t.get('direction') == "LONG" else "dn"
        html += f"""
      <div class="prow">
        <span class="pcol left" style="color:#ff9900">{t.get('id')}</span>
        <span class="pcol left wide white"><b>{t.get('symbol')}</b></span>
        <span class="pcol left {dir_color}">{t.get('direction')}</span>
        <span class="pcol wide left" style="color:#888">{t.get('condition')}</span>
        <span class="pcol">{t.get('entry')}</span>
        <span class="pcol dn">{t.get('sl')}</span>
        <span class="pcol up">{t.get('tp1') or '--'}</span>
        <span class="pcol">{fmt_usd(t.get('notional'))}</span>
        <span class="pcol {color_class(upnl)}">{fmt_usd(upnl)}</span>
      </div>
"""

    html += f"""
    </div>

    <div class="panel">
      <div class="panel-header">CLOSED TRADES HISTORY</div>
      <div class="row-header">
        <span class="pcol left">ID</span>
        <span class="pcol left wide">SYMBOL</span>
        <span class="pcol left">DIR</span>
        <span class="pcol wide left">CONDITION</span>
        <span class="pcol">ENTRY</span>
        <span class="pcol">EXIT</span>
        <span class="pcol wide left">REASON</span>
        <span class="pcol">PNL</span>
      </div>
"""

    for t in closed_trades:
        rpnl = t.get('rpnl', 0)
        dir_color = "up" if t.get('direction') == "LONG" else "dn"
        html += f"""
      <div class="prow">
        <span class="pcol left" style="color:#ff9900">{t.get('id')}</span>
        <span class="pcol left wide white"><b>{t.get('symbol')}</b></span>
        <span class="pcol left {dir_color}">{t.get('direction')}</span>
        <span class="pcol wide left" style="color:#555">{t.get('condition')}</span>
        <span class="pcol">{t.get('entry')}</span>
        <span class="pcol">{t.get('close_price')}</span>
        <span class="pcol wide left" style="color:#aaa">{t.get('close_reason')}</span>
        <span class="pcol {color_class(rpnl)} font-bold">{fmt_usd(rpnl)}</span>
      </div>
"""

    html += """
    </div>
  </div>
</div>
"""

    # ── PAGE: QWEN ──
    summary = analysis_data.get("summary", "No recent analysis available.")
    action = analysis_data.get("action", "None")
    
    html += f"""
<div id="page-QWEN" class="page">
  <div class="main grid-1">
    <div class="panel" style="border: 1px solid #0e3460; background: #050a14;">
      <div class="panel-header" style="color: #0ea5e9; border-bottom-color: #0e3460;">
        QWEN AUTONOMOUS AGENT — MARKET INTELLIGENCE & SELF-HEALING
      </div>
      <div style="padding: 10px 5px;">
        <div style="color: #888; font-size: 10px; margin-bottom: 10px; text-transform: uppercase;">Latest Analysis Report</div>
        <div class="qwen-text">{summary}</div>
        
        <div style="margin-top: 20px; border-top: 1px dashed #0e3460; padding-top: 10px;">
          <div style="color: #888; font-size: 10px; margin-bottom: 5px; text-transform: uppercase;">Autonomous Actions Taken</div>
          <div class="qwen-action">>> {action}</div>
        </div>
      </div>
    </div>
  </div>
</div>
"""

    # ── FOOTER ──
    html += f"""
<div class="statusbar">
  <span>{now_str}</span>
  <span>Azalyst Alpha X Scanner | Automated GitHub Actions Runner</span>
  <span style="color:#00ff41">v1.0.0</span>
</div>

</body>
</html>
"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Dashboard generated: index.html")

if __name__ == "__main__":
    generate_html()