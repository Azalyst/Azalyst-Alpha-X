"""
Visual comparison: WTS (Recross) vs Band Touch Momentum
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

BG = "#0d1117"
WHITE = "#e6edf3"
FG = "#8b949e"
GRID = "#1c2333"
BULL = "#26a69a"
BEAR = "#ef5350"
BLUE = "#3b82f6"
ORANGE = "#f97316"
GREEN = "#22c55e"
RED = "#ef4444"
YELLOW = "#facc15"

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), facecolor=BG)

# ═════════════════════════════════════════════════════════════════
#  LEFT: WTS LOGIC (Recross)
# ═════════════════════════════════════════════════════════════════
ax1.set_facecolor(BG)
ax1.tick_params(colors=FG, labelsize=9)
for sp in ax1.spines.values():
    sp.set_color(GRID)
ax1.grid(color=GRID, linewidth=0.5, alpha=0.6)
ax1.set_title("STRATEGY 1: WTS (Recross) — 3-Candle Pattern", 
              color=GREEN, fontsize=12, fontweight="bold", pad=12)

xs = np.arange(12)
upper, mid, lower = 105, 100, 95
ax1.axhline(upper, color=BLUE, lw=1.5, label="Upper BB", zorder=1)
ax1.axhline(mid, color=ORANGE, lw=1.5, label="Mid BB", ls="--", zorder=1)
ax1.axhline(lower, color=BLUE, lw=1.5, ls="--", label="Lower BB", alpha=0.8, zorder=1)
ax1.fill_between(xs, upper, lower, color=BLUE, alpha=0.04, zorder=0)

def candle(ax, x, o, h, l, c, color):
    ax.plot([x, x], [l, h], color=color, lw=1.2, zorder=3)
    ax.bar(x, abs(c - o), bottom=min(o, c), color=color, width=0.5, alpha=0.9, zorder=4)

# WTS pattern
candles_wts = [
    (0, 100.5, 101.5, 99.8, 100.8, BULL),
    (1, 100.8, 102.0, 100.2, 101.5, BULL),
    (2, 101.5, 103.0, 100.8, 102.2, BULL),
    (3, 102.2, 104.5, 101.5, 103.8, BULL),
    (4, 103.8, 105.5, 102.5, 103.0, BEAR),
    (5, 103.0, 103.5, 100.5, 101.0, BEAR),
    (6, 101.0, 101.5, 97.5, 98.0, BEAR),    # p[-3]: BREAK below
    (7, 98.0, 98.8, 94.5, 94.8, BEAR),      # s[-2]: RECROSS above
    (8, 94.8, 95.5, 93.5, 94.2, BEAR),      # Waiting
    (9, 94.2, 96.5, 93.8, 96.0, BULL),      # s[-2]: recross back
    (10, 96.0, 97.5, 95.5, 97.2, BULL),     # c[-1]: confirm
]

for x, o, h, l, c, col in candles_wts:
    candle(ax1, x, o, h, l, c, col)

# Annotate WTS pattern
ax1.add_patch(mpatches.FancyBboxPatch((5.65, 96.8), 0.7, 3, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=RED, facecolor="none", zorder=10))
ax1.text(6.0, 91.2, "p[-3]\nBREAK <\n94.2", ha="center", fontsize=8, 
    color=RED, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=RED, alpha=0.9))

ax1.add_patch(mpatches.FancyBboxPatch((6.65, 94.2), 0.7, 2.5, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=GREEN, facecolor="none", zorder=10))
ax1.text(7.0, 91.2, "s[-2]\nRECROSS >\n95.2", ha="center", fontsize=8,
    color=GREEN, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=GREEN, alpha=0.9))

ax1.add_patch(mpatches.FancyBboxPatch((9.65, 94.8), 0.7, 2.2, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=YELLOW, facecolor="none", zorder=10))
ax1.text(10.0, 91.2, "c[-1]\nCONFIRM >\n96.0 > 95.2", ha="center", fontsize=8,
    color=YELLOW, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=YELLOW, alpha=0.9))

ax1.axhline(97.2, color=YELLOW, lw=2, ls=":", alpha=0.8, zorder=2)
ax1.text(11.3, 97.2, "ENTRY", fontsize=9, color=YELLOW, fontweight="bold", va="center")

ax1.set_xlim(-0.5, 11.8)
ax1.set_ylim(90, 108)
ax1.set_ylabel("Price", color=FG, fontsize=10)
ax1.legend(loc="upper left", fontsize=9, facecolor="#161b22", labelcolor=FG, edgecolor=GRID)

# ═════════════════════════════════════════════════════════════════
#  RIGHT: BAND TOUCH LOGIC (Momentum)
# ═════════════════════════════════════════════════════════════════
ax2.set_facecolor(BG)
ax2.tick_params(colors=FG, labelsize=9)
for sp in ax2.spines.values():
    sp.set_color(GRID)
ax2.grid(color=GRID, linewidth=0.5, alpha=0.6)
ax2.set_title("STRATEGY 2: Band Touch Momentum — 2-Candle Pattern",
              color=RED, fontsize=12, fontweight="bold", pad=12)

xs2 = np.arange(10)
ax2.axhline(upper, color=BLUE, lw=1.5, label="Upper BB", zorder=1)
ax2.axhline(mid, color=ORANGE, lw=1.5, label="Mid BB", ls="--", zorder=1)
ax2.axhline(lower, color=BLUE, lw=1.5, ls="--", label="Lower BB", alpha=0.8, zorder=1)
ax2.fill_between(xs2, upper, lower, color=BLUE, alpha=0.04, zorder=0)

# Band Touch pattern
candles_touch = [
    (0, 100.5, 101.5, 99.8, 100.8, BULL),
    (1, 100.8, 102.0, 100.2, 101.5, BULL),
    (2, 101.5, 103.5, 100.8, 103.2, BULL),    # BREAK above
    (3, 103.2, 105.0, 102.5, 104.8, BULL),    # Still above
    (4, 104.8, 106.5, 103.0, 105.2, BULL),    # Above upper band
    (5, 105.2, 105.8, 104.5, 105.0, BULL),    # Touch band (close ≈ 105)
    (6, 105.0, 105.5, 104.0, 104.8, BULL),    # Drop but < prev → not yet
    (7, 104.8, 105.8, 103.8, 104.6, BULL),    # Still touching
    (8, 104.6, 106.0, 104.0, 104.9, BULL),    # p[-1]: AT band
    (9, 104.9, 105.5, 103.5, 105.3, BULL),    # c[-1]: BOUNCE UP
]

for x, o, h, l, c, col in candles_touch:
    candle(ax2, x, o, h, l, c, col)

# Annotate Band Touch pattern
ax2.add_patch(mpatches.FancyBboxPatch((7.65, 103.2), 0.7, 2.3, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=RED, facecolor="none", zorder=10))
ax2.text(8.0, 100.8, "BREAK\nAbove\n105+", ha="center", fontsize=8,
    color=RED, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=RED, alpha=0.9))

ax2.add_patch(mpatches.FancyBboxPatch((8.65, 103.6), 0.7, 1.8, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=GREEN, facecolor="none", zorder=10))
ax2.text(9.0, 100.8, "p[-1]\nTOUCH @\n≈ 105", ha="center", fontsize=8,
    color=GREEN, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=GREEN, alpha=0.9))

ax2.add_patch(mpatches.FancyBboxPatch((9.65, 104.8), 0.7, 2.2, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=YELLOW, facecolor="none", zorder=10))
ax2.text(9.95, 100.8, "c[-1]\nBOUNCE ↑\n105.3 > 104.9", ha="center", fontsize=8,
    color=YELLOW, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=YELLOW, alpha=0.9))

ax2.axhline(105.3, color=YELLOW, lw=2, ls=":", alpha=0.8, zorder=2)
ax2.text(9.7, 105.3, "ENTRY", fontsize=9, color=YELLOW, fontweight="bold", va="center")

ax2.set_xlim(-0.5, 9.8)
ax2.set_ylim(100, 110)
ax2.set_ylabel("Price", color=FG, fontsize=10)
ax2.legend(loc="upper left", fontsize=9, facecolor="#161b22", labelcolor=FG, edgecolor=GRID)

fig.suptitle("Both Strategies Run Simultaneously — Different Entry Patterns",
             color=WHITE, fontsize=14, fontweight="bold", y=0.98)

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig("d:/Azalyst Alpha X/charts/wts_vs_band_touch.png",
            dpi=120, facecolor=BG, edgecolor="none", bbox_inches="tight")
print("✅ Chart saved: charts/wts_vs_band_touch.png")
plt.close()

# ═════════════════════════════════════════════════════════════════
#  Summary comparison table
# ═════════════════════════════════════════════════════════════════
fig2 = plt.figure(figsize=(14, 6), facecolor=BG)
ax = fig2.add_subplot(111)
ax.axis("off")

title = "Trading Strategies Comparison"
ax.text(0.5, 0.95, title, transform=ax.transAxes, ha="center", va="top",
    fontsize=14, color=WHITE, fontweight="bold")

comparison = """
STRATEGY 1: WTS (Recross) — Mean Reversion
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Entry Pattern:    Break Outside Band  →  Recross Back Inside  →  Confirm
  
  Candles Needed:   3 (p[-3], s[-2], c[-1])
  
  LONG Entry:       p[-3].close < lower_band
                    s[-2].close > lower_band
                    c[-1].close > s[-2].close
                    Entry @ c[-1].close
  
  SHORT Entry:      p[-3].close > upper_band
                    s[-2].close < upper_band
                    c[-1].close < s[-2].close
                    Entry @ c[-1].close
  
  SL (LONG):        min(s[-2].low, p[-3].low)
  SL (SHORT):       max(s[-2].high, p[-3].high)


STRATEGY 2: Band Touch Momentum — Bounce Reversion
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Entry Pattern:    Break Outside Band  →  Touch Band Again  →  Momentum Entry
  
  Candles Needed:   2 (p[-1], c[-1])
  
  LONG Entry:       p[-1].close ≈ upper_band (±0.25%)
                    c[-1].close > p[-1].close (bounce up)
                    Price was above band recently (3-candle check)
                    Entry @ c[-1].close
  
  SHORT Entry:      p[-1].close ≈ lower_band (±0.25%)
                    c[-1].close < p[-1].close (drop down)
                    Price was below band recently (3-candle check)
                    Entry @ c[-1].close
  
  SL (LONG):        p[-1].low (low of touch candle)
  SL (SHORT):       p[-1].high (high of touch candle)


BOTH RUN SIMULTANEOUSLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Scanner checks all 4 conditions every scan interval (10 min)
  
  Possible positions:  1 WTS LONG  +  1 Band Touch SHORT
                       1 WTS SHORT  +  1 Band Touch LONG
                       etc.
  
  Position limit:      Max 1 LONG per strategy + Max 1 SHORT per strategy
  
  Exit logic:          Each strategy tracks its own positions independently
"""

ax.text(0.05, 0.88, comparison, transform=ax.transAxes, ha="left", va="top",
    fontsize=9, color=FG, fontfamily="monospace",
    bbox=dict(boxstyle="round", facecolor="#161b22", edgecolor=GRID, linewidth=2, alpha=0.95, pad=1))

plt.savefig("d:/Azalyst Alpha X/charts/strategy_comparison.png",
            dpi=120, facecolor=BG, edgecolor="none", bbox_inches="tight")
print("✅ Chart saved: charts/strategy_comparison.png")
plt.close()

print("\n📊 Comparison diagrams created!")
