"""Mean-reversion projection: BUY LOW / SELL HIGH using Bollinger Bands.
Buy when a candle closes below the LOWER band, sell back at the middle band.
Sell when a candle closes above the UPPER band, buy back at the middle band.

Optional TIME EXIT (4th arg): exit at target OR after N bars, whichever first.
This beats the "stop gets run over on trend-continuation days" problem.

USAGE:
    python mean_reversion.py USDZARm H4 30 6
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
    time_exit = int(sys.argv[4]) if len(sys.argv) > 4 else 0  # 0 = no time exit

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

    results = {"win": 0, "loss": 0, "timeout": 0, "open": 0}
    total_points = 0.0

    for i in range(config.BB_PERIOD + 1, len(bars)):
        prev_close = closes[i - 1]
        bought_low = prev_close < lower[i - 1]   # dipped under lower band -> buy
        sold_high = prev_close > upper[i - 1]    # rallied above upper band -> sell
        if not bought_low and not sold_high:
            continue

        entry = prev_close
        target = middle[i]                       # revert to the mean (middle band)
        disturb = (upper[i] - lower[i]) * 0.35   # stop: runaway move away from the band

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
        last_bar = min(i + (time_exit if time_exit > 0 else 200), len(bars))
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

        # time exit: gave it N bars, no target -> exit at close of last scanned bar
        if outcome == "open" and time_exit > 0:
            outcome, exit_price = "timeout", bars[last_bar - 1]["close"]

        if outcome == "win":
            results["win"] += 1
            moves = dist_tp
        elif outcome == "loss":
            results["loss"] += 1
            moves = -dist_sl
        elif outcome == "timeout":
            results["timeout"] += 1
            if bought_low:
                moves = (exit_price - entry) - spread_points
            else:
                moves = (entry - exit_price) - spread_points
        else:
            results["open"] += 1
            continue

        total_points += moves

    n = results["win"] + results["loss"] + results["timeout"]
    wr = results["win"] / n * 100 if n else 0.0
    label = f" + time-exit {time_exit} bars" if time_exit > 0 else ""
    print(f"--- BUY LOW/SELL HIGH | {symbol} {tf_name} | {days}d{label} ---")
    print(f"wins: {results['win']}  losses: {results['loss']}  timeouts: {results['timeout']}  open: {results['open']}")
    print(f"win rate: {wr:.1f}%")
    print(f"net profit (points, incl {spread_points}-pt spread): {total_points:.0f}")
    conn.shutdown()


if __name__ == "__main__":
    main()