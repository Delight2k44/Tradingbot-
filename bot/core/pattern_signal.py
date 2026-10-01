"""Shared fast pattern-strategy engine (L1-L4 + demand zones + wick stop).

Used by BOTH the backtester (pattern_batch.py) and the live bot (pattern_bot.py)
so signal logic can never drift between research and production.

The pattern spec (research/pattern_pseudocode.md):
  LONG only. M15 trigger + H1 primary arming. Demand zones (auto-derived here).
  SL  = wick low - PATTERN_POINT_OFFSET points. Reject if stop > 3x ATR(14).
  TP1 = 1R,  TP2 = 2R.
"""
import datetime as dt

import numpy as np


def bars_from_rates(rates):
    """rates rows [time,o,h,l,c,tv,spread] -> list of dicts used by numpy step."""
    return [
        {"time": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4]}
        for r in rates
    ]


def precompute_patterns(bars):
    """Vectorized pattern flags over candle arrays.
    Returns (o, c, h, l, t, pat, avg_body, atr) all length == len(bars).
    pat: 0=none, 1=L1, 2=L2, 3=L3, 4=L4. LONG-only masks applied (close>open).
    """
    n = len(bars)
    o = np.array([b["open"] for b in bars], dtype=float)
    c = np.array([b["close"] for b in bars], dtype=float)
    h = np.array([b["high"] for b in bars], dtype=float)
    l = np.array([b["low"] for b in bars], dtype=float)
    t = np.array([b["time"] for b in bars], dtype=np.int64)

    rng = h - l
    rng_safe = np.where(rng <= 0, 1e-9, rng)
    body = np.abs(c - o)
    br = body / rng_safe
    upw = (h - np.maximum(o, c)) / rng_safe
    lww = (np.minimum(o, c) - l) / rng_safe

    avg_body = np.full(n, np.nan)
    for i in range(20, n):
        avg_body[i] = body[i - 20:i].mean()

    prev_c = np.empty(n)
    prev_c[0] = o[0]
    prev_c[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr = np.full(n, np.nan)
    for i in range(13, n):
        atr[i] = tr[i - 13:i + 1].mean()

    pat = np.zeros(n, dtype=int)
    m1 = (br >= 0.90) & (upw < 0.05) & (lww < 0.05) & (body >= 2.0 * avg_body)
    m2 = (br >= 0.50) & (br <= 0.65) & (upw >= 0.15) & (upw <= 0.25) \
         & (lww >= 0.15) & (lww <= 0.25) & (body >= 0.8 * avg_body) & (body <= 1.2 * avg_body)
    m3 = (br >= 0.55) & (br <= 0.80) & (upw >= 0.15) & (upw <= 0.30) & (lww < 0.10) \
         & (rng >= 1.5 * atr)
    m4 = (br >= 0.70) & (br <= 0.85) & (upw < 0.12) & (lww < 0.12) & (body >= 1.4 * avg_body)
    pat[m1 & (o < c)] = 1
    pat[m2 & (o < c)] = 2
    pat[m3 & (o < c)] = 3
    pat[m4 & (o < c)] = 4
    return o, c, h, l, t, pat, avg_body, atr


def demand_zones_fast(h, l, times, n_zones=3):
    """Distinct swing-low clusters -> zones [(z_lo, z_hi)] (auto-derived placeholder).
    NOTE: swap with user's real demand zones once they provide price levels.
    """
    span = 10
    n = len(h)
    lows_ = []
    for i in range(span, n - span):
        win_l = l[i - span:i + span + 1]
        if l[i] <= win_l.min():
            lows_.append((i, l[i]))
    if not lows_:
        return []
    lows_.sort(key=lambda x: x[1])
    zones = []
    for i, lo in lows_:
        a = max(0, i - 3)
        b = min(n, i + 4)
        low3 = l[a:b].min()
        hi3 = h[a:b].max()
        zlo, zhi = low3, (low3 + hi3) / 2.0
        placed = False
        for zi in range(len(zones)):
            zl, zh = zones[zi]
            mid = (zl + zh) / 2.0
            if abs(lo - mid) / mid < 0.006:
                zones[zi] = (min(zl, zlo), max(zh, zhi))
                placed = True
                break
        if not placed:
            zones.append((zlo, zhi))
    zones.sort(key=lambda x: x[0])
    return zones[:n_zones]


def ema(values, period):
    """EMA over python floats, returns shifted array aligned to input."""
    alpha = 2.0 / (period + 1)
    out = np.full(len(values), np.nan)
    if len(values) == 0:
        return out
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def latest_signal(symbol, conn, tf_map=None, point_off=10, ema_filter=False,
                  n_zones=3, min_h1=80, min_m15=80, days=30, dealt=None):
    """Return the freshest un-traded LONG signal for a symbol, or None.

    IMPORTANT DESIGN: this reuses scan_symbol (the exact backtest engine) instead of
    hand-rolling a 'look at the newest closed candle' check. That means live trades
    are taken from IDENTICAL signal logic to the backtests that were validated, so
    they can never drift apart.

    `dealt` is a set of (zone, h1_idx) keys already acted on (prevents re-entry).
    """
    cands = scan_symbol(symbol, conn, days=days, point_off=point_off,
                        ema_filter=ema_filter, n_zones=n_zones)
    if not cands:
        return None
    dealt = dealt or set()
    now = int(dt.datetime.now().timestamp())
    # only consider signals whose trigger candle closed within the last hour
    fresh = [c for c in cands
             if c["time"] >= now - 3600
             and (c["zone"], c["h1_idx"]) not in dealt]
    if not fresh:
        return None
    # newest trigger wins
    fresh.sort(key=lambda c: c["time"])
    c = fresh[-1]
    return {"symbol": symbol,
            "zone": c["zone"], "tf": c["tf"], "h1_idx": c["h1_idx"],
            "entry": c["entry"], "entry_r": c["entry_r"], "sl": c["sl"],
            "tp1": c["tp1"], "tp2": c["tp2"], "point": c.get("point") or point_off}


def h1_idx_of(t1, t15_time):
    idx = int(np.searchsorted(t1, t15_time, side="right")) - 1
    return max(0, min(idx, len(t1) - 1))


def scan_symbol(symbol, conn, tf_map=None, days=60, point_off=10, lookback=72,
                ema_filter=False, n_zones=3):
    """Full pattern scan over a symbol's recent H1+M15 history.

    Returns a list of candidate dicts (same shape the backtester consumes) or None
    when there's insufficient data.
    """
    import MetaTrader5 as mt5
    if tf_map is None:
        tf_map = {"H1": mt5.TIMEFRAME_H1, "M15": mt5.TIMEFRAME_M15}
    from_ = dt.datetime.now() - dt.timedelta(days=days)
    h1 = mt5.copy_rates_range(symbol, tf_map["H1"], from_, dt.datetime.now())
    m15 = mt5.copy_rates_range(symbol, tf_map["M15"], from_, dt.datetime.now())
    if h1 is None or len(h1) < 80 or m15 is None or len(m15) < 80:
        return None

    h1b = bars_from_rates(h1)
    m15b = bars_from_rates(m15)

    o1, c1, hh1, l1s, t1, p1, _, atr1 = precompute_patterns(h1b)
    o15, c15, h15, l15, t15, p15, _, _ = precompute_patterns(m15b)

    info = mt5.symbol_info(symbol)
    point = info.point if info else 0.00001
    spread_pts = info.spread if info else 20

    zones = demand_zones_fast(hh1, l1s, t1, n_zones=n_zones)

    h1_idx_of_m15 = np.clip(np.searchsorted(t1, t15, side="right") - 1, 0, len(t1) - 1)

    ema1 = ema(c1.tolist(), 50) if ema_filter else None

    cand = []
    used = {}
    for m in range(21, len(m15)):
        pm = p15[m]
        if pm == 0:
            continue
        hi = h1_idx_of_m15[m]
        mid15 = (o15[m] + c15[m]) / 2.0
        for zi, (zlo, zhi) in enumerate(zones):
            if zlo <= mid15 <= zhi:
                if used.get(zi) == hi:
                    break
                cand.append({
                    "zone": zi, "tf": "15m-L%d" % pm, "h1_idx": hi,
                    "m15_idx": m, "entry": c15[m], "src_h1_idx": hi,
                    "time": int(t15[m]),
                })
                used[zi] = hi
                break
    for i in range(21, len(h1b)):
        pm = p1[i]
        if pm == 0:
            continue
        mid1 = (o1[i] + c1[i]) / 2.0
        for zi, (zlo, zhi) in enumerate(zones):
            if zlo <= mid1 <= zhi:
                if used.get(zi) == i:
                    break
                cand.append({
                    "zone": zi, "tf": "1h-L%d" % pm, "h1_idx": i,
                    "m15_idx": None, "entry": c1[i], "src_h1_idx": i,
                    "time": int(t1[i]),
                })
                used[zi] = i
                break

    result = []
    seen = set()
    for cd in cand:
        key = (cd["zone"], cd["h1_idx"])
        if key in seen:
            continue
        seen.add(key)
        h1i = cd["h1_idx"]
        sl_low_idx = cd["src_h1_idx"] if cd["src_h1_idx"] is not None else h1i
        sl = l1s[sl_low_idx] - point_off * point
        r = abs(cd["entry"] - sl)
        if r <= 0:
            continue
        av = atr1[h1i] if not np.isnan(atr1[h1i]) else None
        if av and r > 3.0 * av:
            continue
        if ema_filter and not np.isnan(ema1[h1i]) and c1[h1i] < ema1[h1i]:
            continue
        tp1 = cd["entry"] + r
        tp2 = cd["entry"] + 2 * r
        outcome = None
        for k in range(h1i + 1, min(h1i + lookback, len(h1b))):
            if l1s[k] <= sl:
                outcome = "loss"
                break
            if hh1[k] >= tp2:
                outcome = "full"
                break
            if hh1[k] >= tp1:
                outcome = "partial"
                break
        pts = 0.0
        if outcome == "loss":
            pts = -(r / point) - spread_pts
        elif outcome == "full":
            pts = 1.5 * (r / point) - spread_pts
        elif outcome == "partial":
            pts = (r / point) - spread_pts
        result.append({**cd, "entry_r": r, "sl": sl, "tp1": tp1, "tp2": tp2,
                       "outcome": outcome, "pts": pts})
    return result