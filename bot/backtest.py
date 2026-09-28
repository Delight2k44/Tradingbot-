"""Efficient backtest: precomputes Bollinger indicators once, then scans for
squeeze+breakout signals over real MT5 history.

USAGE:
    python backtest.py USDZARm M5 30
"""
import sys
import datetime as dt

from core.mt5_connector import MT5Connector
from core import strategy
import config


def to_tf(name):
    import MetaTrader5 as mt5
    return getattr(mt5, f"TIMEFRAME_{name}", mt5.TIMEFRAME_M5)


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "USDZARm"
    tf_name = sys.argv[2] if len(sys.argv) > 2 else "M5"
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 30

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

    bars = [
        {"time": c[0], "open": c[1], "high": c[2], "low": c[3],
         "close": c[4], "tick_volume": c[5], "spread": c[6]}
        for c in rates
    ]
    closes = [b["close"] for b in bars]

    # precompute BB once over the whole series
    upper, middle, lower = strategy.bollinger(
        bars, period=config.BB_PERIOD, deviations=config.BB_DEVIATIONS)
    bw = strategy.bandwidth(upper, lower, middle)
    P = config.BB_PERIOD
    S = config.BB_BW_SMOOTHING

    signals = []
    for i in range(P + S + 1, len(bars)):
        avg = strategy.moving_average(bw[i - S:i], S)
        if avg is None or avg == 0:
            continue
        squeeze = bw[i] < avg * config.BB_SQUEEZE_RATIO
        if not squeeze:
            continue
        broke_up = closes[i - 1] > upper[i - 1]
        broke_down = closes[i - 1] < lower[i - 1]
        action = None
        if broke_up:
            action = "buy"
        elif broke_down:
            action = "sell"
        if action:
            signals.append((bars[i - 1], bars[i], action, bw[i] / avg))

    print(f"{symbol} {tf_name} last {days}d: {len(bars)} bars, {len(signals)} signals")
    print(f"{'signal time':<20} {'action':<6} {'close':>10} {'bw_ratio':>8}")
    for prev, cur, action, ratio in signals[-25:]:
        d = dt.datetime.fromtimestamp(cur["time"]).strftime("%Y-%m-%d %H:%M")
        print(f"{d:<20} {action:<6} {cur['close']:>10.5f} {ratio:>8.2f}")

    conn.shutdown()


if __name__ == "__main__":
    main()