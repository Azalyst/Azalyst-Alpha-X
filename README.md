# Azalyst Alpha X

An institutional-style quantitative research platform for discovering and validating systematic alpha signals in cryptocurrency markets. Built as a personal project. Not a hedge fund. Not a financial product. Just a passion for systematic research.

## Overview

Azalyst Alpha X is a sophisticated Bollinger Band breakout pullback strategy scanner designed for systematic trading in cryptocurrency markets. The platform implements institutional-grade quantitative logic with precise entry and exit rules.

## Strategy Logic

### LONG Position (Upper Band)
1. **Breakout**: Price moves UP above the Upper Bollinger Band
2. **Pullback**: Price comes DOWN to touch the Upper Band
3. **Entry Trigger**: Price starts going UP again from the touch point
   - **Action**: BUY
   - **Stop Loss**: Low of the candle that touched the band
4. **Hold**: Price runs up, staying above the band
5. **Exit**: Price moves above band again, then returns to TOUCH the Upper Band
   - **Action**: SELL (Close Long)

### SHORT Position (Lower Band)
1. **Breakout**: Price moves DOWN below the Lower Bollinger Band
2. **Pullback**: Price comes UP to touch the Lower Band
3. **Entry Trigger**: Price starts going DOWN again from the touch point
   - **Action**: SELL (Short)
   - **Stop Loss**: High of the candle that touched the band
4. **Hold**: Price runs down, staying below the band
5. **Exit**: Price moves below band again, then returns to TOUCH the Lower Band
   - **Action**: BUY (Close Short)

### Key Rules
- **No Middle Band Trading**: The system completely ignores price action between the bands
- **Automatic Re-entry**: After stop loss is hit, the system waits for a new setup formation
- **Strict Band Interaction**: Entries only on re-touch after breakout; exits on re-touch after extension

## Scanner Configuration

- **Scan Interval**: Every 15 minutes
- **Lookback Window**: 10 minutes
- **Condition Validation**: Signals are only triggered if breakout + pullback + turn conditions occur within the 10-minute lookback window during each scan
- **Timeframe**: Operates on 10-minute candles

## Features

- 🎯 Precise entry/exit logic based on Bollinger Band interactions
- 🛡️ Automatic stop loss placement based on touch candle highs/lows
- ⏱️ Time-constrained signal validation (10-min lookback)
- 📊 Real-time chart generation and Discord notifications
- 🔄 Mirror-opposite logic for long and short positions
- 🚫 No interference in middle band price action

## Files Structure

- `bb_scanner.py` - Main scanner implementation with Bollinger Band logic
- `paper_trades.json` - Paper trading log and performance tracking
- `charts/` - Directory for generated strategy charts

## Usage

The scanner runs automatically every 15 minutes, checking for valid setups within the last 10 minutes of price action. When conditions are met, it:
1. Generates entry/exit signals
2. Creates visual charts with Bollinger Bands
3. Sends notifications via Discord webhook
4. Logs trades to paper trading journal

## Disclaimer

This is a personal research project for educational and experimental purposes only. It is not a hedge fund, not a financial product, and should not be considered financial advice. Always conduct your own research and risk management before trading.

---

*Built with passion for systematic quantitative research.*
