"""Candlestick pattern engine (LONG-only) — exact geometry from the spec.
Ratios are timeframe-independent: same rules on 15m and 1h.
"""
import numpy as np


def body_range_ratio(open_, close, high, low):
    """|close - open| / (high - low)."""
    rng = high - low
    if rng <= 0:
        return 0.0
    return abs(close - open_) / rng


def wicks(open_, close, high, low):
    """Return (upper_wick_pct, lower_wick_pct) as fraction of range."""
    rng = high - low
    if rng <= 0:
        return 0.0, 0.0
    upper = (high - max(open_, close)) / rng
    lower = (min(open_, close) - low) / rng
    return upper, lower


def average_body(bars_close, bars_open, start, period=20):
    """Average |close - open| of the last `period` candles ending at `start` (exclusive)."""
    if start < period:
        return None
    tot = 0.0
    for i in range(start - period, start):
        tot += abs(bars_close[i] - bars_open[i])
    return tot / period


def atr_value(bars, i, period=14):
    """ATR(period) up to and including index i. bars must include high/low/close."""
    if i < period:
        return None
    trs = []
    for j in range(i - period + 1, i + 1):
        prev_close = bars[j - 1]["close"] if j > 0 else bars[j]["open"]
        tr = max(bars[j]["high"] - bars[j]["low"],
                 abs(bars[j]["high"] - prev_close),
                 abs(bars[j]["low"] - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs)


def match_pattern(i, bars, timeframe="1h"):
    """Match L1..L4 on candle index i. Returns (level, extra) or (None, {}).
    `level` is 'L1','L2','L3','L4'. Geometry only — zone/rejection handled by caller.
    """
    if i < 20:
        return None, {}
    c = bars[i]
    open_, close, high, low = c["open"], c["close"], c["high"], c["low"]
    if close <= open_:
        return None, {}          # bullish only
    br = body_range_ratio(open_, close, high, low)
    up, lo = wicks(open_, close, high, low)
    avg_b = average_body([b["close"] for b in bars], [b["open"] for b in bars], i, 20)
    if avg_b is None or avg_b <= 0:
        return None, {}

    body = abs(close - open_)
    rng = high - low
    atr = atr_value(bars, i, 14)

    # --- L1: full-body marubozu / engulf ---
    if br >= 0.90 and up < 0.05 and lo < 0.05 and body >= 2.0 * avg_b:
        # rejection: closes above zone midpoint (caller checks zone) -> handled as flag
        return "L1", {}

    # --- L2: square body (dominant shape) ---
    if 0.50 <= br <= 0.65 and 0.15 <= up <= 0.25 and 0.15 <= lo <= 0.25 \
       and 0.8 * avg_b <= body <= 1.2 * avg_b:
        return "L2", {}

    # --- L3: tall body with upper wick ---
    if 0.55 <= br <= 0.80 and 0.15 <= up <= 0.30 and lo < 0.10 \
       and atr is not None and rng >= 1.5 * atr:
        return "L3", {}

    # --- L4: long body / thin wicks ---
    if 0.70 <= br <= 0.85 and up < 0.12 and lo < 0.12 and body >= 1.4 * avg_b:
        return "L4", {}

    return None, {}


def body_midpoint(open_, close):
    return (open_ + close) / 2.0


def closes_above_zone_mid(open_, close, zone_mid):
    return close > zone_mid


def closes_upper_half_of_range(open_, close, high, low):
    """close in upper 50% of its own range."""
    mid = (high + low) / 2.0
    return close >= mid