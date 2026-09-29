"""SMC Breaker/Order Block + Symmetrical Rejection - signal engine.
Port of the user's strategy logic into a vectorized form that runs on
our bar format so we can backtest it honestly.
"""
import numpy as np


def smc_signals(bars, timeframe=15, wick_mult=2.0, swing_len=3, atr_period=14):
    """Return a list of signal dicts over the given bars.
    Same rules as the live code: retest breaker + bearish symmetric rejection = BUY,
    retest order block + bullish symmetric rejection = SELL.
    """
    n = len(bars)
    if n < 60:
        return []

    close = np.array([b["close"] for b in bars])
    open_ = np.array([b["open"] for b in bars])
    high = np.array([b["high"] for b in bars])
    low = np.array([b["low"] for b in bars])

    body = np.abs(close - open_)
    body[body == 0] = 1e-5
    upper_wick = high - np.maximum(open_, close)
    lower_wick = np.minimum(open_, close) - low

    is_sym = (upper_wick >= wick_mult * body) & (lower_wick >= wick_mult * body)
    valid_buy_rejection = is_sym & (close < open_)   # bearish candle -> buy rejection
    valid_sell_rejection = is_sym & (close > open_)  # bullish candle -> sell rejection

    # ATR
    tr = np.maximum(high - low,
                    np.maximum(np.abs(high - np.roll(close, 1)),
                               np.abs(low - np.roll(close, 1))))
    tr[tr < 0] = np.nan
    atr_ser = pd_rolling_mean(tr, atr_period)

    # swings (window of 2*swing_len+1 centered)
    swing_high = np.full(n, np.nan)
    swing_low = np.full(n, np.nan)
    span = swing_len
    for i in range(span, n - span):
        win_h = high[i - span:i + span + 1]
        win_l = low[i - span:i + span + 1]
        if high[i] == win_h.max():
            swing_high[i] = high[i]
        if low[i] == win_l.min():
            swing_low[i] = low[i]

    last_sh = ffill(swing_high)
    last_sl = ffill(swing_low)

    brk_low = np.full(n, np.nan)
    brk_high = np.full(n, np.nan)
    ob_low = np.full(n, np.nan)
    ob_high = np.full(n, np.nan)

    b_lo, b_hi = np.nan, np.nan
    o_lo, o_hi = np.nan, np.nan
    prev_sh = np.nan
    prev_sl = np.nan

    for i in range(1, n):
        c_close = close[i]
        p_sh = last_sh[i - 1]
        p_sl = last_sl[i - 1]
        if not np.isnan(p_sh) and c_close > p_sh:      # upside CHoCH -> breaker support
            b_lo, b_hi = low[i - 1], p_sh
        if not np.isnan(p_sl) and c_close < p_sl:      # downside BMS -> OB/breaker resistance
            o_lo, o_hi = p_sl, high[i - 1]
        brk_low[i], brk_high[i] = b_lo, b_hi
        ob_low[i], ob_high[i] = o_lo, o_hi

    retest_breaker = (low <= brk_high) & (high >= brk_low)
    retest_ob = (high >= ob_low) & (low <= ob_high)

    bsl = rolling_max(high, 50)
    ssl = rolling_min(low, 50)

    signals = []
    for i in range(2, n - 1):
        # evaluate on fully closed bar i-1 -> entry announced at bar i
        j = i - 1
        if np.isnan(atr_ser[j]):
            continue
        if retest_breaker[j] and valid_buy_rejection[j]:
            sl = brk_low[j] - atr_ser[j] * 1.0
            tp = bsl[j]
            signals.append({"bar": i, "action": "buy", "entry": close[i],
                            "sl": sl, "tp": tp,
                            "type": "breaker"})
        elif retest_ob[j] and valid_sell_rejection[j]:
            sl = ob_high[j] + atr_ser[j] * 1.0
            tp = ssl[j]
            signals.append({"bar": i, "action": "sell", "entry": close[i],
                            "sl": sl, "tp": tp,
                            "type": "ob"})
    return signals


# ---------- small helpers (no pandas dependency) ----------
def pd_rolling_mean(arr, period):
    out = np.full(len(arr), np.nan)
    acc = 0.0
    for i in range(len(arr)):
        v = arr[i]
        acc = acc + v if i < period else acc + v - arr[i - period]
        if i >= period - 1:
            out[i] = acc / period
    return out


def rolling_max(arr, period):
    out = np.full(len(arr), np.nan)
    for i in range(period - 1, len(arr)):
        out[i] = arr[i - period + 1:i + 1].max()
    return out


def rolling_min(arr, period):
    out = np.full(len(arr), np.nan)
    for i in range(period - 1, len(arr)):
        out[i] = arr[i - period + 1:i + 1].min()
    return out


def ffill(arr):
    out = arr.copy()
    last_v = np.nan
    for i in range(len(out)):
        if not np.isnan(out[i]):
            last_v = out[i]
        else:
            out[i] = last_v
    return out