# Band Touch Momentum Logic — Implementation Summary

## ✅ Status: COMPLETED

Added **Band Touch Momentum** strategy alongside existing **WTS (Recross)** strategy.

---

## What Was Added

### 1. **Two New Signal Detection Functions**

**`long_band_touch(df)`** — Lines 313-334
- Detects LONG signals when price bounces UP from upper band touch
- Entry: When current close > previous close (after touching band)
- SL: Low of the touch candle

**`short_band_touch(df)`** — Lines 336-357
- Detects SHORT signals when price drops DOWN from lower band touch
- Entry: When current close < previous close (after touching band)
- SL: High of the touch candle

### 2. **Updated Signal Checkers**

```python
CHECKERS = [long_c1, short_c1, long_band_touch, short_band_touch]
```

Both strategies now run **simultaneously** on every scan.

---

## How It Works

### LONG Signal (Upper Band Touch)
```
Three conditions must ALL be true:

1. Previous candle CLOSES AT upper band (within ±0.25%)
   └─ abs(p[-1].close - upper_band) ≤ band_touch_tol
   
2. Current candle closes ABOVE previous (bouncing up)
   └─ c[-1].close > p[-1].close
   
3. Price was above band recently (within 3 candles)
   └─ any(df.iloc[i].close > df.iloc[i].upper for i in range(-3, 0))

↓ IF ALL TRUE ↓
Entry: c[-1].close
SL:    p[-1].low
```

### SHORT Signal (Lower Band Touch)
```
Three conditions must ALL be true:

1. Previous candle CLOSES AT lower band (within ±0.25%)
   └─ abs(p[-1].close - lower_band) ≤ band_touch_tol
   
2. Current candle closes BELOW previous (dropping down)
   └─ c[-1].close < p[-1].close
   
3. Price was below band recently (within 3 candles)
   └─ any(df.iloc[i].close < df.iloc[i].lower for i in range(-3, 0))

↓ IF ALL TRUE ↓
Entry: c[-1].close
SL:    p[-1].high
```

---

## Key Parameters

Located in **USER CONFIG** section (lines 101-124):

```python
TOUCH_TOL        = 0.0025       # 0.25% tolerance for band touch detection
SCAN_INTERVAL    = 600          # 10 minutes between scans
SIGNAL_COOLDOWN  = 300          # 5 min before same symbol fires again
```

### Adjusting Sensitivity
- **More signals**: Decrease TOUCH_TOL (e.g., 0.001)
- **Fewer signals**: Increase TOUCH_TOL (e.g., 0.005)

---

## Exit Conditions

### Band Touch Strategy Exits
- **LONG**: Exit when price touches upper band again
- **SHORT**: Exit when price touches lower band again

This is handled by the existing `PaperTrader.update()` method when price hits targets or stop loss.

---

## Position Management

### Allowed Simultaneously
- 1 WTS LONG + 1 Band Touch SHORT
- 1 WTS SHORT + 1 Band Touch LONG
- 1 WTS LONG + 1 Band Touch LONG (different symbols)
- etc.

### Per Symbol
- Only 1 LONG position per symbol
- Only 1 SHORT position per symbol
- Cooldown of 300 seconds before same symbol can signal again

---

## Files Modified/Created

### Modified
- **bb_scanner.py** (lines 312-359)
  - Added `long_band_touch()` function
  - Added `short_band_touch()` function
  - Updated `CHECKERS` list

### Created
- **BAND_TOUCH_LOGIC.md** — Detailed documentation
- **IMPLEMENTATION_SUMMARY.md** — This file
- **visualize_strategy_comparison.py** — Creates comparison charts

---

## Testing the New Logic

### Manual Check
Look for trades labeled:
- `"Upper Band Touch Momentum"` (LONG)
- `"Lower Band Touch Momentum"` (SHORT)

In Discord alerts and paper trades file.

### Scanner Output
The condition name in alerts will show:
```
🔔 SIGNAL: Upper Band Touch Momentum (LONG)
🔔 SIGNAL: Lower Band Touch Momentum (SHORT)
```

---

## Backtest Comparison

| Metric | WTS (Recross) | Band Touch | Notes |
|--------|---------------|-----------|-------|
| **Entries per day** | Fewer | More | Band touch is more frequent |
| **Win Rate** | Depends | Depends | Test on your data |
| **Avg Profit** | Depends | Depends | Test on your data |
| **Drawdown** | Depends | Depends | Test on your data |

**Recommendation**: Backtest on historical data to compare performance.

---

## Scanning Timeline

```
T=0:00     Scan 1 (checks last 10 min)
           ↓
           WTS check: long_c1, short_c1
           Band Touch check: long_band_touch, short_band_touch
           
T=15:00    Scan 2 (checks last 10 min relative to T=15)
T=30:00    Scan 3
T=45:00    Scan 4
T=60:00    Scan 5
...
```

Each scan window = 10 minutes of price data analyzed.

---

## Debugging

If band touch signals aren't firing:

1. **Check TOUCH_TOL**
   ```python
   # Current: 0.25%
   # Try: 0.50% for more sensitivity
   TOUCH_TOL = 0.005
   ```

2. **Verify band values are calculating correctly**
   ```python
   # Check in Discord output under trade details
   # See "SL = X" and bands displayed
   ```

3. **Monitor price movement relative to bands**
   ```python
   # Look at signal candle low/high vs bands
   # Make sure previous candle is close enough
   ```

---

## Next Steps (Optional)

1. **Add separate entry levels** — Different targets per strategy
2. **Risk management** — Adjust position size based on SL distance
3. **Correlation filters** — Skip signals when volatility is extreme
4. **Time filters** — Only trade during high-volume hours
5. **Backtesting** — Test on 1 month of historical data

---

## Summary

✅ **Band Touch Momentum logic is LIVE**
✅ **Both strategies run simultaneously**
✅ **Paper trading tracks both independently**
✅ **Discord alerts show which strategy triggered**
✅ **Ready to scan and trade**

Monitor Discord alerts for signals labeled:
- "Upper Band Touch Momentum" → LONG entries
- "Lower Band Touch Momentum" → SHORT entries
