"""Fast multi-asset test for the pattern engine (L1-L4 + zones + wick-stop).
Precomputes all indicator/pattern arrays once per symbol for O(n) scanning.

USAGE:
    python pattern_batch.py            # default symbol set
    python pattern_batch.py XAUUSDM XAGUSDM US500M UKOILM
"""
import sys
import time
import datetime as dt

import numpy as np

from core.mt5_connector import MT5Connector
import config


def to_tf(name):
    import MetaTrader5 as mt5
    return getattr(mt5, f"TIMEFRAME_{name}", mt5.TIMEFRAME_M15)


def precompute_patterns(bars):
    """Vectorized pattern flags over candle arrays.
    Returns arrays: pat (0=none,1=L1,2=L2,3=L3,4=L4), plus reusable stats.
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
    low = (np.minimum(o, c) - l) / rng_safe

    # average body of last 20 (exclusive of current)
    avg_body = np.full(n, np.nan)
    for i in range(20, n):
        avg_body[i] = body[i - 20:i].mean()

    # ATR(14)
    prev_c = np.empty(n); prev_c[0] = o[0]; prev_c[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr = np.full(n, np.nan)
    for i in range(13, n):
        atr[i] = tr[i - 13:i + 1].mean()

    pat = np.zeros(n, dtype=int)
    m1 = (br >= 0.90) & (upw < 0.05) & (low < 0.05) & (body >= 2.0 * avg_body)
    m2 = (br >= 0.50) & (br <= 0.65) & (upw >= 0.15) & (upw <= 0.25) \
         & (low >= 0.15) & (low <= 0.25) & (body >= 0.8 * avg_body) & (body <= 1.2 * avg_body)
    m3 = (br >= 0.55) & (br <= 0.80) & (upw >= 0.15) & (upw <= 0.30) & (low < 0.10) \
         & (rng >= 1.5 * atr)
    m4 = (br >= 0.70) & (br <= 0.85) & (upw < 0.12) & (low < 0.12) & (body >= 1.4 * avg_body)
    pat[m1 & (o < c)] = 1
    pat[m2 & (o < c)] = 2
    pat[m3 & (o < c)] = 3
    pat[m4 & (o < c)] = 4
    return o, c, h, l, t, pat, avg_body, atr


def demand_zones_fast(h, l, times, n_zones=3):
    """Distinct swing-low clusters -> zones [(z_lo, z_hi)]."""
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
        a = max(0, i - 3); b = min(n, i + 4)
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


def run_symbol(symbol, conn, days, point_off=10, lookback=72):
    import MetaTrader5 as mt5
    from_ = dt.datetime.now() - dt.timedelta(days=days)
    h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, from_, dt.datetime.now())
    m15 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, from_, dt.datetime.now())
    if h1 is None or len(h1) < 80 or m15 is None or len(m15) < 80:
        return None
    h1b = [{"time": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4]} for r in h1]
    m15b = [{"time": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4]} for r in m15]

    o1, c1, hh1, l1s, t1, p1, _, atr1 = precompute_patterns(h1b)
    o15, c15, h15, l15, t15, p15, _, atr15 = precompute_patterns(m15b)

    info = mt5.symbol_info(symbol)
    point = info.point
    spread_pts = info.spread if info else 20

    zones = demand_zones_fast(hh1, l1s, t1)

    # map each m15 index -> containing h1 index (binary search on h1 start times)
    h1_idx_of_m15 = np.searchsorted(t1, t15, side="right") - 1
    h1_idx_of_m15 = np.clip(h1_idx_of_m15, 0, len(t1) - 1)

    # build candidate list
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
                cand.append((zi, "15m-L%d" % pm, hi, c15[m], None))
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
                cand.append((zi, "1h-L%d" % pm, i, c1[i], i))
                used[zi] = i
                break

    wins = losses = wins15 = 0
    total_pts = 0.0
    seen = set()
    for zi, tag, h1i, entry, src_idx in cand:
        key = (zi, h1i)
        if key in seen:
            continue
        seen.add(key)
        # wick-anchored stop: use 1h low for 1h-primary; also for 15m (1h low) per dedup rule
        sl_low_idx = src_idx if src_idx is not None else h1i
        sl = l1s[sl_low_idx] - point_off * point
        r = abs(entry - sl)
        if r <= 0:
            continue
        av = atr1[h1i] if not np.isnan(atr1[h1i]) else None
        if av and r > 3.0 * av:      # stop too wide -> reject (spec)
            continue
        tp1 = entry + r
        tp2 = entry + 2 * r
        outcome = None
        for k in range(h1i + 1, min(h1i + lookback, len(h1b))):
            if l1s[k] <= sl:
                outcome = "loss"; break
            if hh1[k] >= tp2:
                outcome = "full"; break
            if hh1[k] >= tp1:
                outcome = "partial"; break
        if outcome == "loss":
            losses += 1
            total_pts -= (r / point) + spread_pts
        elif outcome == "full":
            wins += 1
            total_pts += 1.5 * (r / point) - spread_pts
        elif outcome == "partial":
            wins += 1
            total_pts += (r / point) - spread_pts
    n = wins + losses
    wr = wins / n * 100 if n else 0.0
    return (n, wins, losses, wr, total_pts, len(zones))


def main():
    import MetaTrader5 as mt5
    days = 60
    args = sys.argv[1:]
    symbols = args if args else [
        "XAUUSDm", "XAGUSDm", "XPTUSDm", "XPDUSDm",
        "EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm", "USDCHFm", "USDCADm", "NZDUSDm",
        "US500m", "USTECm", "UK100m", "AUS200m",
        "UKOILm", "WTIUSDm", "XAGUSDm",
        "BTCUSDm", "ETHUSDm",
    ]
    conn = MT5Connector(config.MT5_PATH)
    ok, _ = conn.connect(login=config.MT5_LOGIN, password=config.MT5_PASSWORD,
                         server=config.MT5_SERVER)
    if not ok:
        print("connect failed")
        return

    print(f"{'SYMBOL':<10} {'type':<14} {'trades':>6} {'wins':>5} {'losses':>6} {'WR%':>6} {'netpts':>10}")
    print("-" * 65)
    results = []
    for sym in symbols:
        base = sym[:3].upper()
        kind = "CURRENCY" if len(sym) == 6 and base in ("EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY") \
            else ("INDEX" if sym in ("US500m", "USTECm", "UK100m", "AUS200m") \
            else ("COMMOD" if sym in ("UKOILm", "WTIUSDm") \
            else ("METAL" if sym.startswith(("XAU", "XAG", "XPT", "XPD")) else "CRYPTO")))
        try:
            res = run_symbol(sym, conn, days)
        except Exception as e:
            print(f"{sym:<10} {kind:<14} ERROR {e}")
            continue
        if res is None:
            print(f"{sym:<10} {kind:<14} {'no data':>6}")
            continue
        n, w, los, wr, net, nz = res
        results.append((sym, kind, n, wr, net))
        print(f"{sym:<10} {kind:<14} {n:>6} {w:>5} {los:>6} {wr:>6.1f} {net:>10.0f}")
    conn.shutdown()
    print()
    print("=== sorted by net points ===")
    for sym, kind, n, wr, net in sorted(results, key=lambda x: -x[4]):
        if n >= 5:
            print(f"{sym:<10} {kind:<14} trades={n:>4} WR={wr:>5.1f}%  net={net:>10.0f}")


if __name__ == "__main__":
    main()