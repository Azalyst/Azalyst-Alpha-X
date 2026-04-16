# Azalyst Alpha X

## Institutional-Style Quantitative Research Platform

**Systematic Alpha Signal Discovery & Validation Engine for Cryptocurrency Markets**


### Overview

Azalyst Alpha X is a proprietary quantitative research framework designed to identify, validate, and execute systematic trading signals in digital asset markets. The platform employs rigorous statistical methodologies, multi-timeframe analysis, and disciplined risk management protocols characteristic of institutional trading desks.

**Deployment Status:** Production environment hosted on Railway with automated scanning cycles and real-time signal generation.

**Tech Stack & Tools**

![Python](https://img.shields.io/badge/Python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white)
![Matplotlib](https://img.shields.io/badge/Matplotlib-11557c?style=for-the-badge&logo=matplotlib&logoColor=white)
![Requests](https://img.shields.io/badge/Requests-2d2d2d?style=for-the-badge)
![Railway](https://img.shields.io/badge/Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)
![Binance API](https://img.shields.io/badge/Binance%20API-F3BA2F?style=for-the-badge&logo=binance&logoColor=white)
![Discord Webhook](https://img.shields.io/badge/Discord%20Webhook-5865F2?style=for-the-badge&logo=discord&logoColor=white)
---
### Strategic Architecture

#### Core Philosophy

The system operates on a breakout-pullback methodology utilizing Bollinger Band volatility envelopes. This approach capitalises on momentum continuation following volatility expansions while maintaining strict discipline against noise trading in neutral (middle-band) market conditions.

#### Signal Generation Framework

| Phase | Long Setup (Upper Band) | Short Setup (Lower Band) |
|-------|-------------------------|--------------------------|
| **Breakout** | Price closes ABOVE Upper Bollinger Band (breakout) | Price closes BELOW Lower Bollinger Band (breakdown) |
| **Pullback** | Price retraces back DOWN to touch the Upper Band | Price bounces back UP to touch the Lower Band |
| **Trigger** | Current candle closes ABOVE pullback candle (momentum up) | Current candle closes BELOW bounce candle (momentum down) |
| **Entry** | BUY at current close | SELL at current close |
| **Stop Loss** | Low of the pullback touch candle | High of the bounce touch candle |
| **Exit** | Price extends above upper band again → re-touches upper band → CLOSE | Price extends below lower band again → re-touches lower band → CLOSE |

#### Entry / Exit Separation (Critical Rule)

- **Upper Band Recross** (price above upper band → closes back below) → **EXIT open LONG only** — never opens a new SHORT
- **Lower Band Recross** (price below lower band → closes back above) → **EXIT open SHORT only** — never opens a new LONG
- The `extended` flag tracks per-trade whether price has moved beyond the band since entry; exit fires on the next band touch after extension

#### Anti-Sideways Filters

All three must pass before any entry fires:

1. **Bandwidth Check** — Bollinger Band width must be ≥ 0.8% of price. Narrow bands = squeeze = sideways → skip.
2. **Minimum Breakout Distance** — Breakout candle must close ≥ 0.2% beyond the band. Tiny pokes are noise → skip.
3. **Middle Band Exclusion** — For LONG: entry candle must be above middle band. For SHORT: below middle band. Price in dead zone → skip.

#### Operational Constraints

- **Neutral Zone Protocol:** No signal generation or position management occurs when price action resides between Bollinger Bands (Middle Band region)
- **Temporal Validation:** All signal conditions must manifest within a 10-minute lookback window
- **Scan Frequency:** Systematic evaluation occurs at 15-minute intervals
- **Risk Management:** Automatic position closure upon stop-loss trigger; no re-entry until fresh setup criteria are met

---

### Technical Specifications

#### Data Pipeline

```
Market Data Feed → 10-Minute Candle Aggregation → Bollinger Band Calculation
    → Anti-Sideways Filters → Breakout Detection → Pullback Monitoring
    → Trigger Validation → Order Execution → Position Management
    → Extended Flag Tracking → Band Touch Exit Logic
```

#### Indicator Parameters

- **Bollinger Bands:** 200-period Simple Moving Average with 1.0 standard deviation envelopes
- **Timeframe:** 10-minute candle resolution
- **Lookback Window:** 10 minutes for condition validation
- **Scan Interval:** 15 minutes between evaluation cycles
- **Touch Tolerance:** 0.25% for band touch detection
- **Min Breakout:** 0.2% beyond band to qualify as real breakout
- **Min Bandwidth:** 0.8% to filter out sideways squeezes

#### Execution Logic Flow

```
+-------------------------------------------------------------------------+
|                         SCAN CYCLE INITIATION                            |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|              ANTI-SIDEWAYS FILTERS (bandwidth / dead zone)               |
+-------------------------------------------------------------------------+
                                    |
                    +---------------+---------------+
                    |                               |
                    v                               v
        +---------------------+         +---------------------+
        |   LONG SETUP        |         |   SHORT SETUP       |
        |                     |         |                     |
        | 1. Break > Upper BB |         | 1. Break < Lower BB |
        | 2. Pullback to Touch|         | 2. Bounce to Touch  |
        | 3. Momentum Up      |         | 3. Momentum Down    |
        | 4. Above Middle Band|         | 4. Below Middle Band|
        +---------------------+         +---------------------+
                    |                               |
                    v                               v
        +---------------------+         +---------------------+
        |    EXECUTE BUY      |         |    EXECUTE SELL     |
        |                     |         |                     |
        | SL: Touch Candle Low|         | SL: Touch Candle Hi |
        | extended = False    |         | extended = False    |
        +---------------------+         +---------------------+
                    |                               |
                    v                               v
        +---------------------+         +---------------------+
        |   MONITOR POSITION  |         |   MONITOR POSITION  |
        |                     |         |                     |
        | If close > upper BB |         | If close < lower BB |
        |   extended = True   |         |   extended = True   |
        |                     |         |                     |
        | If extended AND     |         | If extended AND     |
        |   touch upper BB    |         |   touch lower BB    |
        |   → EXIT (close)    |         |   → EXIT (close)    |
        +---------------------+         +---------------------+
                    |                               |
                    +---------------+---------------+
                                    v
                    +-------------------------------+
                    |   POSITION CLOSED / SL HIT    |
                    |                               |
                    |   WAIT FOR NEXT VALID SETUP   |
                    |   (NO MIDDLE BAND ACTIVITY)   |
                    +-------------------------------+
```

---

### Infrastructure & Deployment

#### Production Environment

- **Hosting Platform:** Railway
- **Runtime:** Continuous operation with automated scan cycles
- **Data Source:** Binance USDT-Margined Perpetual Futures (fapi.binance.com)
- **Notification System:** Discord Webhook alerts with chart images

#### System Requirements

- Python 3.9+ runtime environment
- Network connectivity for market data ingestion
- Dependencies: pandas, numpy, requests, matplotlib (optional)

#### Quick Start

```bash
pip install pandas numpy requests matplotlib
python main.py
```

---

### Risk Disclosure

This platform is designed for quantitative research and educational purposes. Historical performance does not guarantee future results. Cryptocurrency markets exhibit extreme volatility and may result in substantial financial loss. The strategies implemented herein have not been registered with any regulatory authority and do not constitute investment advice, solicitation, or recommendation.

Users should conduct independent due diligence and consult qualified financial professionals before deploying capital based on signals generated by this system.

---

### Development Status

**Current Version:** 2.0.0
**Last Updated:** 2025
**License:** Proprietary - All Rights Reserved

---

*Azalyst Alpha X - Systematic Research. Disciplined Execution. Quantitative Precision.*
