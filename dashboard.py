import json
import os
from datetime import datetime

TRADES_FILE = "paper_trades.json"
ANALYSIS_FILE = "qwen_analysis.json"

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}

def generate_html():
    trades_data = load_json(TRADES_FILE)
    analysis_data = load_json(ANALYSIS_FILE)
    
    balance = trades_data.get("balance", 10000.0)
    closed = trades_data.get("closed_trades", [])
    open_t = trades_data.get("open_trades", [])
    
    wins = len([t for t in closed if t.get("rpnl", 0) > 0])
    losses = len([t for t in closed if t.get("rpnl", 0) <= 0])
    win_rate = (wins / len(closed) * 100) if closed else 0
    total_pnl = sum([t.get("rpnl", 0) for t in closed])
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Azalyst Alpha X - Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-900 text-gray-100 font-sans">
        <div class="max-w-6xl mx-auto p-6">
            <header class="mb-8 border-b border-gray-700 pb-4">
                <h1 class="text-3xl font-bold text-blue-400">Azalyst Alpha X</h1>
                <p class="text-gray-400">BB(200,1) Perpetual Futures Scanner Dashboard</p>
            </header>
            
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                <div class="bg-gray-800 p-4 rounded-lg shadow">
                    <h2 class="text-gray-400 text-sm">Balance</h2>
                    <p class="text-2xl font-bold">${balance:,.2f}</p>
                </div>
                <div class="bg-gray-800 p-4 rounded-lg shadow">
                    <h2 class="text-gray-400 text-sm">Win Rate</h2>
                    <p class="text-2xl font-bold text-blue-400">{win_rate:.1f}%</p>
                </div>
                <div class="bg-gray-800 p-4 rounded-lg shadow">
                    <h2 class="text-gray-400 text-sm">Total PnL</h2>
                    <p class="text-2xl font-bold {"text-green-400" if total_pnl >= 0 else "text-red-400"}">${total_pnl:,.2f}</p>
                </div>
                <div class="bg-gray-800 p-4 rounded-lg shadow">
                    <h2 class="text-gray-400 text-sm">Total Trades</h2>
                    <p class="text-2xl font-bold">{len(closed) + len(open_t)}</p>
                </div>
            </div>
    """
    
    if analysis_data:
        html += f"""
            <div class="bg-gray-800 p-6 rounded-lg shadow mb-8 border border-blue-500">
                <h2 class="text-xl font-bold text-blue-400 mb-4">Qwen Autonomous Analysis</h2>
                <div class="prose prose-invert max-w-none text-gray-300">
                    <p>{analysis_data.get("summary", "No summary available.")}</p>
                    <h3 class="text-lg font-bold mt-4 text-white">Action Taken:</h3>
                    <p>{analysis_data.get("action", "None")}</p>
                </div>
            </div>
        """
        
    html += """
            <h2 class="text-xl font-bold mb-4 border-b border-gray-700 pb-2">Recent Closed Trades</h2>
            <div class="overflow-x-auto bg-gray-800 rounded-lg shadow">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-gray-700 bg-gray-900 text-gray-400">
                            <th class="p-3">ID</th>
                            <th class="p-3">Symbol</th>
                            <th class="p-3">Direction</th>
                            <th class="p-3">Entry</th>
                            <th class="p-3">Close Price</th>
                            <th class="p-3">Reason</th>
                            <th class="p-3">PnL</th>
                        </tr>
                    </thead>
                    <tbody>
    """
    
    for t in sorted(closed, key=lambda x: x.get("id", ""), reverse=True)[:50]:
        pnl = t.get("rpnl", 0)
        pnl_class = "text-green-400" if pnl > 0 else "text-red-400"
        html += f"""
                        <tr class="border-b border-gray-700 hover:bg-gray-700">
                            <td class="p-3">{t.get("id")}</td>
                            <td class="p-3 font-semibold">{t.get("symbol")}</td>
                            <td class="p-3">
                                <span class="px-2 py-1 rounded text-xs font-bold {"bg-green-900 text-green-300" if t.get("direction") == "LONG" else "bg-red-900 text-red-300"}">
                                    {t.get("direction")}
                                </span>
                            </td>
                            <td class="p-3">{t.get("entry")}</td>
                            <td class="p-3">{t.get("close_price")}</td>
                            <td class="p-3 text-sm text-gray-400">{t.get("close_reason")}</td>
                            <td class="p-3 font-bold {pnl_class}">${pnl:+.2f}</td>
                        </tr>
        """
        
    html += """
                    </tbody>
                </table>
            </div>
            <footer class="mt-8 text-center text-sm text-gray-500">
                Generated by GitHub Actions & Qwen AI Dashboard Builder
            </footer>
        </div>
    </body>
    </html>
    """
    
    with open("index.html", "w") as f:
        f.write(html)
    print("Dashboard generated: index.html")

if __name__ == "__main__":
    generate_html()