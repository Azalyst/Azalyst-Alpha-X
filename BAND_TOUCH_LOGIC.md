# Band Touch Momentum Logic — Documentation

## Overview
Completely new entry strategy that trades **band touches** instead of recrosses.

- **WTS (Old)**: Break outside → Recross inside → Confirmation
- **Band Touch (New)**: Break outside → Touch band again → Bounce/Drop entry

---

## Entry Conditions

### LONG — Upper Band Touch Momentum
```
Pattern:
┌─────────────────────────────────┐
│ 1. Price above upper band       │  Recent break above
│    (within last 3 candles)      │
├─────────────────────────────────┤
│ 2. Previous candle closes AT    │  Close ≈ upper_band ±0.25%
│    upper band (±0.25% tolerance)│
├─────────────────────────────────┤
│ 3. Current candle close >       │  Momentum confirmed
│    previous close (bouncing up) │
└─────────────────────────────────┘
         ↓ BUY SIGNAL ↓
Entry:  c[-1].close
SL:     p[-1].low (low of touch candle)
```

### SHORT — Lower Band Touch Momentum
```
Pattern:
┌─────────────────────────────────┐
│ 1. Price below lower band       │  Recent break below
│    (within last 3 candles)      │
├─────────────────────────────────┤
│ 2. Previous candle closes AT    │  Close ≈ lower_band ±0.25%
│    lower band (±0.25% tolerance)│
├─────────────────────────────────┤
│ 3. Current candle close <       │  Momentum confirmed
│    previous close (dropping)    │
└─────────────────────────────────┘
         ↓ SELL SIGNAL ↓
Entry:  c[-1].close
SL:     p[-1].high (high of touch candle)
```

---

## Exit Conditions

### LONG Position
Exit when price comes back to **touch upper band again**

### SHORT Position
Exit when price comes back to **touch lower band again**

---

## Implementation Details

### Tolerance for Band Touch
```python
TOUCH_TOL = 0.0025  # 0.25% tolerance
band_touch_tol = band_value * TOUCH_TOL

# Example: If upper band = 100
# Touch range = 99.975 to 100.025
```

### Recent Break Check (3-candle lookback)
Ensures price actually broke the band recently before touching again.

---

## Code Implementation

```python
def long_band_touch(df) -> dict | None:
    """Upper Band Touch Momentum → Long"""
    p, c = df.iloc[-2], df.iloc[-1]
    
    # 1. Previous candle touches upper band
    band_touch_tol = p["upper"] * TOUCH_TOL
    at_upper_band = abs(p["close"] - p["upper"]) <= band_touch_tol
    
    # 2. Current bounces up
    bouncing_up = c["close"] > p["close"]
    
    # 3. Price was above band recently
    above_band_recently = any(df.iloc[i]["close"] > df.iloc[i]["upper"] 
                              for i in range(-3, 0))
    
    if at_upper_band and bouncing_up and above_band_recently:
        return _build("LONG", "Upper Band Touch Momentum",
                      c["close"], p["low"])
    return None

def short_band_touch(df) -> dict | None:
    """Lower Band Touch Momentum → Short"""
    p, c = df.iloc[-2], df.iloc[-1]
    
    # 1. Previous candle touches lower band
    band_touch_tol = p["lower"] * TOUCH_TOL
    at_lower_band = abs(p["close"] - p["lower"]) <= band_touch_tol
    
    # 2. Current drops down
    dropping_down = c["close"] < p["close"]
    
    # 3. Price was below band recently
    below_band_recently = any(df.iloc[i]["close"] < df.iloc[i]["lower"] 
                              for i in range(-3, 0))
    
    if at_lower_band and dropping_down and below_band_recently:
        return _build("SHORT", "Lower Band Touch Momentum",
                      c["close"], p["high"])
    return None
```

---

## Scanning Rules

### Timing
- **Scan Interval**: 10 minutes
- **Next Scan**: 15 minutes later
- **Lookback Window**: 10 minutes

### Condition Matching
Only count as valid signal if all 3 conditions are met **within the scan window**

### Middle Band Rule
Don't interfere with middle band activity. Only trade band touches at the **edges** (upper/lower).

---

## Comparison: WTS vs Band Touch

| Aspect | WTS (Recross) | Band Touch (Momentum) |
|--------|---------------|-----------------------|
| **Entry Trigger** | Recross back inside band | Bounce/drop FROM band |
| **Pattern** | 3-candle | 2-candle |
| **SL Location** | Min/Max of 2 candles | Low/High of 1 candle |
| **Risk Profile** | Tighter SL | Wider SL (potentially) |
| **Trading Style** | Mean reversion | Momentum reversion |

---

## Active Logics in Scanner

Both strategies now run simultaneously:

1. **WTS (Lower/Upper Band Recross)**
   - Checks `long_c1()` and `short_c1()`
   
2. **Band Touch (Upper/Lower Band Momentum)**
   - Checks `long_band_touch()` and `short_band_touch()`

```python
CHECKERS = [long_c1, short_c1, long_band_touch, short_band_touch]
```

---

## Position Management

- **Multiple Positions**: YES - Can have WTS trades + Band Touch trades simultaneously
- **Direction Limits**: One LONG + one SHORT allowed (not 2 LONGs or 2 SHORTs)
- **Same Symbol**: No duplicate entries (cooldown of `SIGNAL_COOLDOWN` = 300 seconds)

---

## Configuration

All settings in the **USER CONFIG** section:

```python
SCAN_INTERVAL    = 600      # 10 minutes
TOUCH_TOL        = 0.0025   # 0.25% band touch tolerance
SIGNAL_COOLDOWN  = 300      # 5 minutes before same symbol can signal again
```

Adjust these values to tune sensitivity:
- **Increase TOUCH_TOL**: Looser band touch detection
- **Decrease TOUCH_TOL**: Tighter, more precise touches
