"""Bollinger squeeze -> breakout strategy. Determines WHEN/IF to trade.
The bot executes, this module decides direction and levels.
"""
import math


def bollinger(candles, period=20, deviations=2.0):
    """Return (upper, middle, lower) series over the candle close list."""
    closes = [c["close"] for c in candles]
    n = len(closes)
    if n < period:
        return [], [], []
    upper, middle, lower = [], [], []
    for i in range(n):
        window = closes[i - period + 1:i + 1] if i >= period - 1 else closes[:i + 1]
        if len(window) < period:
            # pad forward stats for early bars (matches most indicators)
            window = closes[:period]
        m = sum(window) / period
        var = sum((x - m) ** 2 for x in window) / period
        sd = math.sqrt(var)
        upper.append(m + deviations * sd)
        middle.append(m)
        lower.append(m - deviations * sd)
    return upper, middle, lower


def bandwidth(upper, lower, middle):
    """BandWidth = (upper - lower) / middle  (standard Bollinger BandWidth)."""
    out = []
    for u, l, m in zip(upper, lower, middle):
        out.append((u - l) / m if m else 0.0)
    return out


def moving_average(values, length):
    if len(values) < length:
        return None
    return sum(values[-length:]) / length


def detect_signal(candles, period=20, deviations=2.0, bw_smoothing=20, squeeze_ratio=1.0):
    """Return a dict signal:
    {'action': 'buy'|'sell'|None, 'bw_ratio': float, 'close': float,
     'upper': float, 'lower': float}
    Called once per closed candle on the strategy timeframe.
    """
    upper, middle, lower = bollinger(candles, period, deviations)
    if not upper or len(upper) < bw_smoothing + 2:
        return {"action": None, "bw_ratio": 0.0}

    bw = bandwidth(upper, lower, middle)
    # squeeze: current BW < average of previous BW window
    avg = moving_average(bw[:-1], bw_smoothing)
    if avg is None or avg == 0:
        return {"action": None, "bw_ratio": 0.0}

    current = bw[-1]
    squeeze = current < avg * squeeze_ratio

    prev_close = candles[-2]["close"]
    prev_upper = upper[-2]
    prev_lower = lower[-2]

    broke_up = prev_close > prev_upper
    broke_down = prev_close < prev_lower

    action = None
    if squeeze and broke_up:
        action = "buy"
    elif squeeze and broke_down:
        action = "sell"

    return {
        "action": action,
        "bw_ratio": current / avg if avg else 0.0,
        "close": candles[-1]["close"],
        "upper": upper[-1],
        "lower": lower[-1],
    }