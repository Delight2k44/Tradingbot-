"""Backtest for the pattern engine (L1-L4 + demand zones + wick-stop).
Multi-TF: H1 primary, M15 trigger. LONG only. Wick-anchored SL, TP1=1R / TP2=2R.

Demand zones: auto-derived from H1 swing lows (since spec zone prices weren't
given). For live trading you must supply your own zones — flagged in pseudocode.

USAGE:
    python pattern_backtest.py XAUUSDm 30
    python pattern_backtest.py EURUSDm 60
"""
import sys
import datetime as dt

from core.mt5_connector import MT5Connector
from core.patterns import (match_pattern, body_midpoint, atr_value,
                           closes_above_zone_mid, closes_upper_half_of_range)
import config


def to_tf(name):
    import MetaTrader5 as mt5
    return getattr(mt5, f"TIMEFRAME_{name}", mt5.TIMEFRAME_M15)


def bars_from(rates):
    return [
        {"time": c[0], "open": c[1], "high": c[2], "low": c[3],
         "close": c[4], "tick_volume": c[5], "spread": c[6]}
        for c in rates
    ]


def demand_zones(h1_bars, n_zones=3):
    """Auto zones: distinct swing-low clusters on the H1 chart.
    Placeholder for the user's real zones — zones are PERSONAL."""
    # find swing lows (lowest in a window of 10 to the left/right)
    swings = []
    span = 10
    for i in range(span, len(h1_bars) - span):
        window = [h1_bars[j]["low"] for j in range(i - span, i + span + 1)]
        if h1_bars[i]["low"] <= min(window):
            swings.append((i, h1_bars[i]["low"]))
    if not swings:
        return []
    # group nearby lows into zones (within 0.35% of each other)
    swings.sort(key=lambda x: x[1])
    zones = []
    for i, lo in swings:
        # width = the low candle's range blended with the 3 lows around the swing
        low3 = min(h1_bars[j]["low"] for j in range(max(0, i - 3), i + 4))
        hi3 = max(h1_bars[j]["high"] for j in range(max(0, i - 3), i + 4))
        zone_lo = low3
        zone_hi = (low3 + hi3) / 2.0
        placed = False
        for zidx in range(len(zones)):
            zlo, zhi = zones[zidx]
            if abs(lo - (zlo + zhi) / 2) / ((zlo + zhi) / 2) < 0.006:
                zones[zidx] = (min(zlo, zone_lo), max(zhi, zone_hi))
                placed = True
                break
        if not placed:
            zones.append((zone_lo, zone_hi))
    zones.sort(key=lambda x: x[0])
    return zones[:n_zones]


def poc(levels):  # price of close midpoint for the 1h confirmation
    return levels


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSDm"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    point_off = 10  # 10 points below wick low (offset)

    conn = MT5Connector(config.MT5_PATH)
    ok, _ = conn.connect(login=config.MT5_LOGIN, password=config.MT5_PASSWORD,
                         server=config.MT5_SERVER)
    if not ok:
        print("connect failed")
        return

    import MetaTrader5 as mt5
    from_ = dt.datetime.now() - dt.timedelta(days=days)
    to_ = dt.datetime.now()

    h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, from_, to_)
    m15 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, from_, to_)
    if h1 is None or len(h1) < 60 or m15 is None or len(m15) < 60:
        print("Not enough data.")
        conn.shutdown()
        return

    h1b = bars_from(h1)
    m15b = bars_from(m15)
    info = mt5.symbol_info(symbol)
    point = info.point
    spread_points = info.spread if info else 20

    zones = demand_zones(h1b)
    print(f"{symbol} {days}d: H1={len(h1b)} bars, M15={len(m15b)} bars, zones={zones}")

    # index M15 bars by their H1 window
    def h1_index_for(mbar_time):
        for i in range(len(h1b) - 1, -1, -1):
            if h1b[i]["time"] <= mbar_time:
                return i
        return 0

    wins = losses = 0
    total_pts = 0.0
    trades = []
    armed = set()          # zone touched from above
    recent_entries = {}    # zone -> (time, idx) for dedup / 1-per-touch

    for i in range(20, len(h1b)):
        hc = h1b[i]
        # --- 1h pattern evaluation (confirmed close) ---
        lvl, _ = match_pattern(i, h1b, "1h")
        hi_idx = i
        if lvl:
            mid = body_midpoint(hc["open"], hc["close"])
            for z_i, (zlo, zhi) in enumerate(zones):
                if zlo <= mid <= zhi:
                    # rejection rule
                    if lvl in ("L1", "L4") and not closes_above_zone_mid(hc["open"], hc["close"], (zlo + zhi) / 2):
                        continue
                    if lvl in ("L2", "L3") and not closes_upper_half_of_range(hc["open"], hc["close"], hc["high"], hc["low"]):
                        continue
                    if recent_entries.get(z_i, (None, None))[0] == i:
                        break
                    sl = hc["low"] - point_off * point
                    trades.append((z_i, "1h-" + lvl, i, hc["close"], sl))
                    recent_entries[z_i] = (i, hi_idx)
                    break

        # --- 15m trigger scan inside/around this H1 candle ---
        for m in range(1, len(m15b)):
            mb = m15b[m]
            idx = h1_index_for(mb["time"])
            if idx != i:
                continue
            lvl15, _ = match_pattern(m, m15b, "15m")
            if not lvl15:
                continue
            mid15 = body_midpoint(mb["open"], mb["close"])
            for z_i, (zlo, zhi) in enumerate(zones):
                if zlo <= mid15 <= zhi:
                    if lvl15 == "L2" and True:  # L2 requires 1h context (spec)
                        if recent_entries.get(z_i, (None, None))[0] == i:
                            break
                    if recent_entries.get(z_i, (None, None))[0] == i:
                        break
                    trades.append((z_i, "15m-" + lvl15, i, mb["close"],
                                   h1b[i]["low"] - point_off * point))
                    recent_entries[z_i] = (i, idx)
                    break

    # --- simulate each trade: SL = wick - 10pt, TP1=1R close50, TP2=2R ---
    for z_i, tag, h1i, entry, sl in trades:
        atr = atr_value(h1b, h1i, 14)
        if not atr:
            continue
        r = abs(entry - sl)
        if r <= 0:
            continue
        tp1 = entry + r
        tp2 = entry + 2 * r
        outcome = "open"
        for k in range(h1i + 1, min(h1i + 72, len(h1b))):  # up to 3 days forward
            hi, lo = h1b[k]["high"], h1b[k]["low"]
            if lo <= sl:
                outcome = "loss"
                break
            if hi >= tp2:
                outcome = "win"
                break
            if hi >= tp1:
                outcome = "partial"
                break
        if outcome == "loss":
            losses += 1
            total_pts -= abs(entry - sl) / point + spread_points
        elif outcome == "win":
            wins += 1
            total_pts += 1.5 * r / point - spread_points   # avg 1.5R (half at 1R, half at 2R)
        elif outcome == "partial":
            wins += 1
            total_pts += r / point - spread_points

    n = wins + losses
    wr = wins / n * 100 if n else 0.0
    print(f"trades: {n}  wins: {wins}  losses: {losses}  win rate: {wr:.1f}%")
    print(f"net pts ({spread_points:.0f}-pt spread): {total_pts:.0f}")
    from collections import Counter
    print("breakdown:", Counter(t[1] for t in trades))
    conn.shutdown()


if __name__ == "__main__":
    main()