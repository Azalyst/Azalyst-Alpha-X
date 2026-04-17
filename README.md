Azalyst Alpha X
An institutional-grade quantitative research platform for discovering and validating systematic alpha signals in cryptocurrency markets. Built as a personal project. Not a hedge fund. Not a financial product. Just a passion for systematic research.
Live Deployment Status
Production Environment: Render Cloud
Service Type: Persistent Web Service (Flask + Scanner Engine + Paper Trading Core)
Current Status: Operational
Live Signal & Portfolio Dashboard: https://azalyst-alpha-x-txx1.onrender.com
Function: Real-time text-based feed of all validated signals, active paper trading positions, account equity, PnL tracking, and win-rate statistics. Auto-refreshes every 10 seconds.
Notification Channel: Discord Webhook Integration
Function: Low-latency alert dispatch for executed signals with full trade intelligence, chart attachments, and exit notifications.
Note: As this deployment utilizes a free-tier infrastructure, latency may increase during periods of inactivity while the instance initializes. Refreshing the dashboard wakes the service.
Strategic Architecture
Core Philosophy
The system operates on a breakout-pullback methodology utilizing Bollinger Band volatility envelopes on a 1-minute resolution universe of 450+ Binance USDT-margined perpetual futures. Signal quality is enforced through a four-layer validation stack: structural pattern detection, multi-timeframe RSI alignment, trend stage classification, and institutional volume confirmation. Only signals that pass all four layers are executed.
This design deliberately filters the 450+ symbol universe down to a small set of high-conviction setups — typically 5–15 per scan — where 1m price structure, hourly momentum, and 4h trend direction are all aligned simultaneously.
Signal Generation Framework
Phase 1 — Structural Pattern Detection (1m Timeframe)
Phase
Long Setup — Upper Band
Short Setup — Lower Band
Breakout
Candle closes ABOVE Upper BB by ≥ 0.2%
Candle closes BELOW Lower BB by ≥ 0.2%
Pullback
Price retraces back DOWN to touch the Upper Band within 10 candles
Price bounces back UP to touch the Lower Band within 10 candles
Trigger
Current candle closes ABOVE pullback close (momentum resumed)
Current candle closes BELOW bounce close (momentum resumed)
Entry
BUY at confirmation candle close
SELL at confirmation candle close
Stop Loss
Low of the pullback touch candle
High of the bounce touch candle
Exit
Price extends above upper band → re-touches upper band → CLOSE
Price extends below lower band → re-touches lower band → CLOSE
Sliding-Window Breakout Detection
Signal detection employs a two-tier temporal window rather than a rigid fixed-offset candle pattern:
30-candle detection horizon: Scanner looks back up to 30 minutes to identify the most recent qualifying breakout spike. This captures setups where the institutional move happened several candles prior and price is still in the pullback phase.
10-candle entry gate: The pullback touch and confirmation candle must complete within 10 minutes of the detected breakout. If the band touch has not occurred within this window the opportunity is considered expired and the signal is voided. This prevents entering on stale momentum.
This architecture captures the full spike → BB expansion → pullback-to-band sequence rather than only the 3-candle [-3, -2, -1] slice most scanners use.
Entry / Exit Separation (Critical Rule)
Upper Band Recross: EXIT open LONG only. Never opens a new SHORT.
Lower Band Recross: EXIT open SHORT only. Never opens a new LONG.
A per-trade extended flag tracks whether price has moved beyond the relevant band since entry. Exit fires on the next confirmed band touch after the extension event. The flag is gated to candles that formed strictly after the entry candle to prevent same-bar open-and-close.
Anti-Sideways Filters
All three must pass before pattern detection is evaluated:
Bandwidth Filter: BB width must be ≥ 0.8% of price. Narrow-band squeezes produce false breakouts → skip.
Breakout Distance Filter: Breakout candle must close ≥ 0.2% beyond the band. Micro-pokes are noise → skip.
Middle Band Exclusion: LONG: entry candle must be above the 200-period SMA. SHORT: below. Price in the neutral zone → skip.
Phase 2 — Multi-Timeframe RSI Alignment Filter
Inspired by the CoinGlass RSI Heatmap methodology: structural 1m signals are only acted upon when higher timeframe RSI independently confirms the same directional bias. This eliminates the common failure mode of entering a 1m breakout that is counter to the prevailing 1h/4h trend.
Direction
1-Hour RSI Requirement
4-Hour RSI Requirement
LONG
≥ 60 (bullish momentum building)
≥ 55 (uptrend confirmed on 4h)
SHORT
≤ 40 (bearish momentum building)
≤ 45 (downtrend confirmed on 4h)
RSI is computed using Wilder's smoothed 14-period formula, identical to the TradingView and CoinGlass implementations. The 1h and 4h OHLC data is fetched live at the moment a signal fires — no stale cache — incurring 2 additional API calls per candidate only, not per symbol in the universe.
Phase 3 — Trend Stage Classification Engine
Each signal that passes the RSI alignment filter is scored and classified into one of three trend stages. This answers the key question: is this the beginning of the move or the end?
Stage Definitions
Stage
4h RSI Range
Interpretation
Action
EARLY
55 – 68
Momentum just starting to build. Price has not run yet. Best risk-to-reward.
Execute
MID
68 – 80
Trend confirmed and running. Still valid but extension is partial.
Execute
LATE
> 80
Move already ran (equivalent to SKL at RSI 90+ on CoinGlass heatmap).
Skip
LATE-stage signals are rejected by default (SKIP_LATE_STAGE = True). This can be overridden for research purposes.
Composite Conviction Score (0 – 100)
Every signal is assigned a quantitative conviction score composed of four components:
Component
Max Points
Methodology
RSI Alignment
30
Proportional to how far 1h and 4h RSI have moved into the signal zone
Stage Bonus
25
EARLY = 25, MID = 15, LATE = 0
RSI Velocity
25
Rate of change of 4h RSI over the last 3 candles — fast acceleration from low levels indicates trend onset
Volume Surge
20
Signal-candle volume as a multiple of the 20-candle average
RSI Velocity is the most operationally significant component. A 4h RSI sitting flat at 62 is categorically different from one that moved from 50 → 62 over 3 candles. The latter represents accelerating institutional positioning and is the primary "before the trend sets" signal.
Phase 4 — Institutional Volume Confirmation
A signal is rejected regardless of RSI or stage classification if the signal candle's volume does not represent a meaningful deviation from baseline activity.
Minimum threshold: Signal candle volume ≥ 1.5× the 20-candle rolling average
Rationale: Sustainable trends are always initiated by above-average volume as institutional participants accumulate or distribute. Breakouts on sub-average volume are statistical noise and revert at high frequency.
Signals passing the 2.25× threshold (1.5× the minimum) are flagged in alerts.
Position & Risk Management (Paper Trading Engine)
Position Sizing
Risk is sized as a fixed percentage of current account equity per trade:
text
1234
Portfolio Constraints
Constraint
Value
Purpose
Max Open Trades
5
Prevents correlated drawdown from a bad scan cycle
Symbol Deduplication
1 per symbol
No re-entry while a position in the same symbol is open
Signal Cooldown
300 seconds
Prevents signal churn on the same symbol within a scan window
SL Distance Floor
0.01% (near-zero)
Rejects only mathematically degenerate setups
Take Profit Levels
TP levels are computed at entry using Fibonacci extension of the recent swing range (60-candle lookback):
TP1: Entry + Swing Range × 1.272 (Fib extension)
TP2: Entry + Swing Range × 1.618 (Fib extension)
Both TP levels are fixed at entry and do not adjust dynamically.
Exit Priority Order
text
123
State Persistence
All open positions, balance updates, and trade history are persisted to paper_trades.json. This ensures that:
Account balance survives server restarts.
Open trades are monitored continuously even after redeployment.
Full audit trail of wins/losses is maintained.
Technical Specifications
Indicator Parameters
Parameter
Value
Bollinger Band Period
200-candle SMA
Standard Deviation Multiplier
1.0σ
Execution Timeframe
1-minute candles
Breakout Detection Window
30 candles (30 min)
Entry Gate Window
10 candles (10 min)
Touch Tolerance
±0.25% of band value
Min Breakout Distance
0.2% beyond band
Min Bandwidth
0.8% of mid price
RSI Period
14 (Wilder smoothed)
RSI Alignment: LONG 1h / 4h
≥ 60 / ≥ 55
RSI Alignment: SHORT 1h / 4h
≤ 40 / ≤ 45
RSI Velocity Minimum
4.0 pts / 3 candles (4h)
Trend Stage Boundary MID
4h RSI 68
Trend Stage Boundary LATE
4h RSI 80
Volume Surge Minimum
1.5× 20-candle average
Scan Interval
300 seconds (5 minutes)
Leverage
30×
Risk Per Trade
2% of equity
Max Margin Per Trade
25% of equity
Max Concurrent Positions
5
Data Pipeline
text
123456789101112131415161718192021222324252627282930313233343536373839404142434445464748
Alert Format Specification
Each signal dispatch contains a structured trade card with the following intelligence block. The format is identical across Discord and the Web Portal.
text
12345678910111213141516
Infrastructure & Deployment
Production Environment
Hosting Platform: Render Cloud (Continuous Operation)
Runtime: Python 3.10+, persistent process with Flask web server
Data Source: Binance USDT-Margined Perpetuals — fapi.binance.com (Direct REST API)
Notification System: Discord Webhook (Text-based structured alerts + Chart Images)
Web Interface: Integrated Flask dashboard serving real-time signal history, open positions, and account metrics.
State Persistence: paper_trades.json — Survives restarts, maintains full trade history and balance tracking.
System Requirements
bash
12345
The system requires no external database; state is maintained locally in JSON format for portability and ease of audit.
Termux / Android (Mobile Deployment)
bash
12345
Parameter Reference
All strategy parameters are consolidated in the USER CONFIG block at the top of main.py. No other section requires modification for standard deployment.
Parameter
Default
Description
BB_PERIOD
200
Bollinger Band SMA period
BB_SD
1
Standard deviation multiplier
TIMEFRAME
"1m"
Candle resolution
SCAN_INTERVAL
300
Seconds between full market scans
BREAKOUT_LOOKBACK
30
Candles back to detect the spike event
ENTRY_WINDOW
10
Max candles from spike to entry confirmation
TOUCH_TOL
0.0025
Band touch tolerance (0.25%)
MIN_BREAKOUT_PCT
0.002
Min breakout distance (0.2%)
MIN_BANDWIDTH_PCT
0.008
Min bandwidth to trade (0.8%)
RSI_PERIOD
14
Wilder RSI period
RSI_LONG_1H
60
Min 1h RSI for LONG signals
RSI_LONG_4H
55
Min 4h RSI for LONG signals
RSI_SHORT_1H
40
Max 1h RSI for SHORT signals
RSI_SHORT_4H
45
Max 4h RSI for SHORT signals
RSI_VELOCITY_MIN
4.0
Min 4h RSI change over 3 candles
TREND_STAGE_MID_4H
68
4h RSI threshold for MID stage
TREND_STAGE_LATE_4H
80
4h RSI threshold for LATE stage
SKIP_LATE_STAGE
True
Reject LATE-stage signals
VOLUME_SURGE_MULT
1.5
Min volume multiple vs 20c average
LEVERAGE
30
Position leverage
RISK_PCT
0.02
Account risk per trade (2%)
MAX_MARGIN_PCT
0.25
Max margin per trade (25% of equity)
MAX_OPEN_TRADES
5
Maximum concurrent open positions
SIGNAL_COOLDOWN
300
Cooldown per symbol in seconds
INITIAL_BALANCE
10,000
Starting paper balance (USDT)
Risk Disclosure
This platform is designed for quantitative research and educational purposes. Historical performance does not guarantee future results. Cryptocurrency markets exhibit extreme volatility and leverage amplifies both gains and losses. The strategies implemented herein have not been registered with any regulatory authority and do not constitute investment advice, solicitation, or recommendation.
Users should conduct independent due diligence and consult qualified financial professionals before deploying capital based on signals generated by this system.
Development Status
Current Version: 3.0.0
Last Updated: April 2026
License: Proprietary — All Rights Reserved
Built by Azalyst | Azalyst Alpha Quant Research
"Evidence over claims. Always."
