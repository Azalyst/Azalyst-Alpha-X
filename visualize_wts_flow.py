"""
Visual diagram showing WTS entry logic with real price action flow
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# ─── Colors ──────────────────────────────────────────────────
BG     = "#0d1117"
WHITE  = "#e6edf3"
FG     = "#8b949e"
GRID   = "#1c2333"
BULL   = "#26a69a"
BEAR   = "#ef5350"
BLUE   = "#3b82f6"
ORANGE = "#f97316"
GREEN  = "#22c55e"
RED    = "#ef4444"
YELLOW = "#facc15"
CYAN   = "#06b6d4"

fig = plt.figure(figsize=(20, 12), facecolor=BG)
fig.suptitle("WTS Entry Logic Flow — Three-Candle Pattern Detection",
             color=WHITE, fontsize=16, fontweight="bold", y=0.98)

# ═══════════════════════════════════════════════════════════════════
#  PANEL 1: LONG SIGNAL FLOW
# ═══════════════════════════════════════════════════════════════════
ax1 = plt.subplot(2, 2, 1)
ax1.set_facecolor(BG)
ax1.tick_params(colors=FG, labelsize=9)
for sp in ax1.spines.values():
    sp.set_color(GRID)
ax1.grid(color=GRID, linewidth=0.5, alpha=0.6)
ax1.set_title("LONG Entry: Lower Band Recross", color=GREEN, fontsize=12, fontweight="bold", pad=12)

# Draw BB bands
xs = np.arange(10)
upper, mid, lower = 105, 100, 95
ax1.axhline(upper, color=BLUE, lw=1.5, label="Upper BB", zorder=1)
ax1.axhline(mid, color=ORANGE, lw=1.5, label="Mid BB (SMA)", ls="--", zorder=1)
ax1.axhline(lower, color=BLUE, lw=1.5, ls="--", label="Lower BB", alpha=0.8, zorder=1)
ax1.fill_between(xs, upper, lower, color=BLUE, alpha=0.04, zorder=0)

# Draw candles
def draw_candle(ax, x, o, h, l, c, color, label=None):
    ax.plot([x, x], [l, h], color=color, lw=1.2, zorder=3)
    ax.bar(x, abs(c - o), bottom=min(o, c), color=color, width=0.5, alpha=0.9, zorder=4)
    if label:
        ax.text(x, l - 1.5, label, ha="center", fontsize=9, fontweight="bold", color=WHITE)

# Price action: moves up, peaks, then drops below lower BB, bounces back
candles = [
    (0, 100.5, 101.5, 99.8, 100.8, BULL, "Start"),
    (1, 100.8, 102.0, 100.2, 101.5, BULL, None),
    (2, 101.5, 103.0, 100.8, 102.2, BULL, None),
    (3, 102.2, 104.5, 101.5, 103.8, BULL, None),
    (4, 103.8, 105.5, 102.5, 103.0, BEAR, None),
    (5, 103.0, 103.5, 100.5, 101.0, BEAR, None),
    (6, 101.0, 101.5, 97.5, 98.0, BEAR, "p[-3]"),
    (7, 98.0, 98.8, 94.5, 94.8, BEAR, "s[-2]"),
    (8, 94.8, 95.5, 93.5, 94.2, BEAR, None),
]

for x, o, h, l, c, col, lbl in candles:
    draw_candle(ax1, x, o, h, l, c, col, lbl)

# Highlight the critical candles
ax1.add_patch(FancyBboxPatch((6.65, 96.8), 0.7, 3, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=RED, facecolor="none", zorder=10))
ax1.text(6.65, 91, "p[-3]\nClose < lower\n(94.2)", ha="center", fontsize=9,
    color=RED, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=RED, alpha=0.9))

ax1.add_patch(FancyBboxPatch((7.65, 94.2), 0.7, 2.5, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=GREEN, facecolor="none", zorder=10))
ax1.text(7.65, 91, "s[-2]\nClose > lower\n(95.2)", ha="center", fontsize=9,
    color=GREEN, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=GREEN, alpha=0.9))

# Current candle (c[-1])
ax1.plot([9, 9], [93.5, 96.5], color=YELLOW, lw=2, zorder=5)
ax1.bar(9, abs(96.0 - 95.2), bottom=95.2, color=YELLOW, width=0.5, alpha=0.9, zorder=5)
ax1.add_patch(FancyBboxPatch((8.65, 94.8), 0.7, 2.2, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=YELLOW, facecolor="none", zorder=10))
ax1.text(9, 91, "c[-1]\nClose > s close\n(96.0 > 95.2)", ha="center", fontsize=9,
    color=YELLOW, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=YELLOW, alpha=0.9))

# Entry and SL lines
ax1.axhline(96.0, color=YELLOW, lw=2, ls=":", alpha=0.8, zorder=2)
ax1.text(9.3, 96.0, "ENTRY @ 96.0", fontsize=9, color=YELLOW, fontweight="bold", va="center")

ax1.axhline(94.2, color=RED, lw=2, ls=":", alpha=0.8, zorder=2)
ax1.text(9.3, 94.2, "SL @ 94.2\n(min of p.low & s.low)", fontsize=9, color=RED, fontweight="bold", va="center")

ax1.set_xlim(-0.5, 9.8)
ax1.set_ylim(90, 108)
ax1.set_ylabel("Price", color=FG, fontsize=10)
ax1.legend(loc="upper left", fontsize=9, facecolor="#161b22", labelcolor=FG, edgecolor=GRID, framealpha=0.9)

# ═══════════════════════════════════════════════════════════════════
#  PANEL 2: SHORT SIGNAL FLOW
# ═══════════════════════════════════════════════════════════════════
ax2 = plt.subplot(2, 2, 2)
ax2.set_facecolor(BG)
ax2.tick_params(colors=FG, labelsize=9)
for sp in ax2.spines.values():
    sp.set_color(GRID)
ax2.grid(color=GRID, linewidth=0.5, alpha=0.6)
ax2.set_title("SHORT Entry: Upper Band Recross", color=RED, fontsize=12, fontweight="bold", pad=12)

# Draw BB bands
xs = np.arange(10)
upper, mid, lower = 105, 100, 95
ax2.axhline(upper, color=BLUE, lw=1.5, label="Upper BB", zorder=1)
ax2.axhline(mid, color=ORANGE, lw=1.5, label="Mid BB (SMA)", ls="--", zorder=1)
ax2.axhline(lower, color=BLUE, lw=1.5, ls="--", label="Lower BB", alpha=0.8, zorder=1)
ax2.fill_between(xs, upper, lower, color=BLUE, alpha=0.04, zorder=0)

# Price action: moves down, bottoms, then rises above upper BB, drops back
short_candles = [
    (0, 100.5, 101.5, 99.8, 100.8, BULL, "Start"),
    (1, 100.8, 102.0, 100.2, 101.5, BULL, None),
    (2, 101.5, 103.0, 100.8, 102.2, BULL, None),
    (3, 102.2, 104.5, 101.5, 103.8, BULL, None),
    (4, 103.8, 105.5, 102.5, 105.2, BULL, "p[-3]"),
    (5, 105.2, 107.0, 104.5, 106.5, BULL, "s[-2]"),
    (6, 106.5, 107.5, 103.5, 103.8, BEAR, None),
    (7, 103.8, 104.2, 102.5, 102.8, BEAR, None),
    (8, 102.8, 103.5, 101.5, 102.2, BEAR, None),
]

for x, o, h, l, c, col, lbl in short_candles:
    draw_candle(ax2, x, o, h, l, c, col, lbl)

# Highlight critical candles
ax2.add_patch(FancyBboxPatch((3.65, 101.5), 0.7, 3.5, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=RED, facecolor="none", zorder=10))
ax2.text(3.65, 108.5, "p[-3]\nClose > upper\n(105.2)", ha="center", fontsize=9,
    color=RED, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=RED, alpha=0.9))

ax2.add_patch(FancyBboxPatch((4.65, 104.5), 0.7, 2.5, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=GREEN, facecolor="none", zorder=10))
ax2.text(4.65, 108.5, "s[-2]\nClose < upper\n(106.5)", ha="center", fontsize=9,
    color=GREEN, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=GREEN, alpha=0.9))

# Current candle (c[-1])
ax2.plot([9, 9], [101.5, 102.2], color=YELLOW, lw=2, zorder=5)
ax2.bar(9, abs(102.2 - 102.8), bottom=102.2, color=YELLOW, width=0.5, alpha=0.9, zorder=5)
ax2.add_patch(FancyBboxPatch((8.65, 101.8), 0.7, 1.5, boxstyle="round,pad=0.08",
    linewidth=2.5, edgecolor=YELLOW, facecolor="none", zorder=10))
ax2.text(9, 100, "c[-1]\nClose < s close\n(102.2 < 103.8)", ha="center", fontsize=9,
    color=YELLOW, fontweight="bold", bbox=dict(boxstyle="round", facecolor=BG, edgecolor=YELLOW, alpha=0.9))

# Entry and SL lines
ax2.axhline(102.8, color=YELLOW, lw=2, ls=":", alpha=0.8, zorder=2)
ax2.text(9.3, 102.8, "ENTRY @ 102.8", fontsize=9, color=YELLOW, fontweight="bold", va="center")

ax2.axhline(107.5, color=RED, lw=2, ls=":", alpha=0.8, zorder=2)
ax2.text(9.3, 107.5, "SL @ 107.5\n(max of s.high & p.high)", fontsize=9, color=RED, fontweight="bold", va="center")

ax2.set_xlim(-0.5, 9.8)
ax2.set_ylim(100, 112)
ax2.set_ylabel("Price", color=FG, fontsize=10)
ax2.legend(loc="upper left", fontsize=9, facecolor="#161b22", labelcolor=FG, edgecolor=GRID, framealpha=0.9)

# ═══════════════════════════════════════════════════════════════════
#  PANEL 3: CODE LOGIC VISUALIZATION
# ═══════════════════════════════════════════════════════════════════
ax3 = plt.subplot(2, 2, 3)
ax3.axis("off")
ax3.set_xlim(0, 10)
ax3.set_ylim(0, 10)

# LONG logic
long_code = (
    "LONG ENTRY CONDITIONS:\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "✓  p[-3].close < lower_band\n"
    "    └─ Prev candle closed BELOW\n"
    "\n"
    "✓  s[-2].close > lower_band\n"
    "    └─ Signal candle crossed BACK ABOVE\n"
    "\n"
    "✓  c[-1].close > s[-2].close\n"
    "    └─ Current confirms move UP\n"
    "\n"
    "ENTRY: c[-1].close (current close)\n"
    "SL:    min(s.low, p.low)"
)

ax3.text(0.5, 9, long_code, fontsize=10, color=GREEN, fontfamily="monospace",
    fontweight="bold", va="top", ha="left",
    bbox=dict(boxstyle="round", facecolor="#161b22", edgecolor=GREEN, 
              linewidth=2, alpha=0.95, pad=1))

# ═══════════════════════════════════════════════════════════════════
#  PANEL 4: SHORT LOGIC VISUALIZATION
# ═══════════════════════════════════════════════════════════════════
ax4 = plt.subplot(2, 2, 4)
ax4.axis("off")
ax4.set_xlim(0, 10)
ax4.set_ylim(0, 10)

# SHORT logic
short_code = (
    "SHORT ENTRY CONDITIONS:\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "✓  p[-3].close > upper_band\n"
    "    └─ Prev candle closed ABOVE\n"
    "\n"
    "✓  s[-2].close < upper_band\n"
    "    └─ Signal candle crossed BACK BELOW\n"
    "\n"
    "✓  c[-1].close < s[-2].close\n"
    "    └─ Current confirms move DOWN\n"
    "\n"
    "ENTRY: c[-1].close (current close)\n"
    "SL:    max(s.high, p.high)"
)

ax4.text(0.5, 9, short_code, fontsize=10, color=RED, fontfamily="monospace",
    fontweight="bold", va="top", ha="left",
    bbox=dict(boxstyle="round", facecolor="#161b22", edgecolor=RED, 
              linewidth=2, alpha=0.95, pad=1))

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig("d:/Azalyst Alpha X/charts/wts_flow_diagram.png", 
            dpi=120, facecolor=BG, edgecolor="none", bbox_inches="tight")
print("✅ Chart saved to: charts/wts_flow_diagram.png")
plt.close()

# ═══════════════════════════════════════════════════════════════════
#  GENERATE TIMELINE FLOW CHART
# ═══════════════════════════════════════════════════════════════════
fig2, (ax_long, ax_short) = plt.subplots(1, 2, figsize=(16, 8), facecolor=BG)

for ax in (ax_long, ax_short):
    ax.set_facecolor(BG)
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)

# ─── LONG TIMELINE ───────────────────────────────────────────────
ax_long.text(5, 11.5, "LONG Entry Timeline", color=GREEN, fontsize=14, 
    fontweight="bold", ha="center")

steps_long = [
    ("1️⃣ DOWNTREND", "Price falling, candles going down", 10, RED),
    ("2️⃣ BREAK LOWER", "p[-3] close < lower band\n(Band touched, went below)", 8.5, RED),
    ("3️⃣ RECROSS UP", "s[-2] close > lower band\n(Price bounces, crosses back up)", 7, GREEN),
    ("4️⃣ CONFIRM UP", "c[-1] close > s[-2] close\n(Current higher than signal close)", 5.5, YELLOW),
    ("5️⃣ BUY SIGNAL", "Entry triggered @ c[-1].close\nSL = min(s.low, p.low)", 3.5, GREEN),
]

for i, (title, desc, y, col) in enumerate(steps_long):
    ax_long.add_patch(FancyBboxPatch((0.5, y-0.6), 9, 1.2, 
        boxstyle="round,pad=0.1", facecolor="#161b22", 
        edgecolor=col, linewidth=2.5))
    ax_long.text(1, y+0.3, title, fontsize=11, color=col, fontweight="bold")
    ax_long.text(1, y-0.2, desc, fontsize=9, color=FG, fontfamily="monospace")
    
    if i < len(steps_long) - 1:
        ax_long.annotate("", xy=(5, y-0.7), xytext=(5, y-1.3),
            arrowprops=dict(arrowstyle="->", color=CYAN, lw=2.5))

# ─── SHORT TIMELINE ──────────────────────────────────────────────
ax_short.text(5, 11.5, "SHORT Entry Timeline", color=RED, fontsize=14, 
    fontweight="bold", ha="center")

steps_short = [
    ("1️⃣ UPTREND", "Price rising, candles going up", 10, GREEN),
    ("2️⃣ BREAK UPPER", "p[-3] close > upper band\n(Band touched, went above)", 8.5, GREEN),
    ("3️⃣ RECROSS DOWN", "s[-2] close < upper band\n(Price pulls back, crosses below)", 7, RED),
    ("4️⃣ CONFIRM DOWN", "c[-1] close < s[-2] close\n(Current lower than signal close)", 5.5, YELLOW),
    ("5️⃣ SELL SIGNAL", "Entry triggered @ c[-1].close\nSL = max(s.high, p.high)", 3.5, RED),
]

for i, (title, desc, y, col) in enumerate(steps_short):
    ax_short.add_patch(FancyBboxPatch((0.5, y-0.6), 9, 1.2, 
        boxstyle="round,pad=0.1", facecolor="#161b22", 
        edgecolor=col, linewidth=2.5))
    ax_short.text(1, y+0.3, title, fontsize=11, color=col, fontweight="bold")
    ax_short.text(1, y-0.2, desc, fontsize=9, color=FG, fontfamily="monospace")
    
    if i < len(steps_short) - 1:
        ax_short.annotate("", xy=(5, y-0.7), xytext=(5, y-1.3),
            arrowprops=dict(arrowstyle="->", color=CYAN, lw=2.5))

fig2.suptitle("WTS Entry Logic — Step-by-Step Timeline", 
    color=WHITE, fontsize=15, fontweight="bold", y=0.98)
plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig("d:/Azalyst Alpha X/charts/wts_timeline.png", 
    dpi=120, facecolor=BG, edgecolor="none", bbox_inches="tight")
print("✅ Chart saved to: charts/wts_timeline.png")
plt.close()

print("\n📊 Two diagrams created:")
print("   1. wts_flow_diagram.png - Detailed candle patterns + logic")
print("   2. wts_timeline.png - Step-by-step entry flow")
