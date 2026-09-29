"""Hybrid strategy: BUY LOW / SELL HIGH + trend filter + time exit.

Core (proven by data): mean reversion off Bollinger bands on H4.
Filter (fixes gold's failure): only trade when not fighting the bigger trend
  (price vs 50-bar EMA / BB middle direction).
Exit (proven): target = middle band, OR exit after N bars.

USAGE:
    python hybrid.py XAUUSDm H4 30 8
    python hybrid.py EURUSDm H4 30 8
"""
import sys
import datetime as dt

from core.mt5_connector import MT5Connector
from core import strategy
import config


def to_tf(name):
    import MetaTrader5 as mt5
    return getattr(mt5, f"TIMEFRAME_{name}", mt5.TIMEFRAME_M15)


def ema(closes, period):
    out = [None] * len(closes)
    if len(closes) < period:
        return out
    k = 2.0 / (period + 1)
    e = sum(closes[:period]) / period
    out[period - 1] = e
    for i in range(period, len(closes)):
        e = closes[i] * k + e * (1 - k)
        out[i] = e
    return out


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSDm"
    tf_name = sys.argv[2] if len(sys.argv) > 2 else "H4"
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    time_exit = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    ema_len = int(sys.argv[5]) if len(sys.argv) > 5 else 50

    conn = MT5Connector(config.MT5_PATH)
    ok, _ = conn.connect(login=config.MT5_LOGIN, password=config.MT5_PASSWORD,
                         server=config.MT5_SERVER)
    if not ok:
        print("connect failed")
        return

    import MetaTrader5 as mt5
    from_ = dt.datetime.now() - dt.timedelta(days=days)
    rates = mt5.copy_rates_range(symbol, to_tf(tf_name), from_, dt.datetime.now())
    if rates is None or len(rates) == 0:
        print("No data.")
        conn.shutdown()
        return

    info = mt5.symbol_info(symbol)
    point = info.point
    spread_points = info.spread if info else 20
    bars = [
        {"time": c[0], "open": c[1], "high": c[2], "low": c[3],
         "close": c[4], "tick_volume": c[5], "spread": c[6]}
        for c in rates
    ]
    closes = [b["close"] for b in bars]

    upper, middle, lower = strategy.bollinger(
        bars, period=config.BB_PERIOD, deviations=config.BB_DEVIATIONS)
    ema50 = ema(closes, ema_len)

    results = {"win": 0, "loss": 0, "timeout": 0}
    total_points = 0.0

    for i in range(max(config.BB_PERIOD + 1, ema_len + 1), len(bars)):
        prev_close = closes[i - 1]
        bought_low = prev_close < lower[i - 1]
        sold_high = prev_close > upper[i - 1]
        if not bought_low and not sold_high:
            continue

        # TREND FILTER: skip ONLY obvious counter-trend trades
        # (price far from EMA = strong trend, don't fade it)
        if bought_low and ema50[i - 1] is not None and prev_close < ema50[i - 1] * 0.985:
            continue   # deep below EMA in strong downtrend - falling knife
        if sold_high and ema50[i - 1] is not None and prev_close > ema50[i - 1] * 1.015:
            continue   # far above EMA in strong uptrend - parabolic top

        entry = prev_close
        target = middle[i]
        disturb = (upper[i] - lower[i]) * 0.35

        if bought_low:
            tp = min(target, entry + disturb)
            sl = entry - disturb
        else:
            tp = max(target, entry - disturb)
            sl = entry + disturb

        if bought_low:
            dist_tp = tp - entry
            dist_sl = entry - sl
        else:
            dist_tp = entry - tp
            dist_sl = sl - entry
        if dist_tp <= 0 or dist_sl <= 0:
            continue

        outcome = "open"
        exit_price = None
        last_bar = min(i + time_exit, len(bars))
        for k in range(i + 1, last_bar):
            hi, lo = bars[k]["high"], bars[k]["low"]
            if bought_low:
                if lo <= sl:
                    outcome, exit_price = "loss", sl
                    break
                if hi >= tp:
                    outcome, exit_price = "win", tp
                    break
            else:
                if hi >= sl:
                    outcome, exit_price = "loss", sl
                    break
                if lo <= tp:
                    outcome, exit_price = "win", tp
                    break

        if outcome == "open":
            outcome, exit_price = "timeout", bars[last_bar - 1]["close"]

        if outcome == "win":
            results["win"] += 1
            total_points += dist_tp - spread_points
        elif outcome == "loss":
            results["loss"] += 1
            total_points -= dist_sl + spread_points
        else:
            results["timeout"] += 1
            if bought_low:
                total_points += (exit_price - entry) - spread_points
            else:
                total_points += (entry - exit_price) - spread_points

    n = results["win"] + results["loss"] + results["timeout"]
    wr = results["win"] / n * 100 if n else 0.0
    print(f"--- HYBRID buy-low/sell-high+trendfilter+timeexit{symbol} {tf_name} {days}d ---")
    print(f"wins: {results['win']}  losses: {results['loss']}  timeouts: {results['timeout']}")
    print(f"win rate: {wr:.1f}%")
    print(f"net points ({spread_points:.0f}-pt spread): {total_points:.0f}")
    conn.shutdown()


if __name__ == "__main__":
    main()