"""Forward P&L projection for the Bollinger squeeze->breakout strategy.
For every signal, applies the bot's exact rules (ATR stop, RR take-profit,
spread handling) to the candle data that follows, and reports win/loss.

USAGE:
    python pnl_projection.py USDZARm M5 30
"""
import sys
import datetime as dt

from core.mt5_connector import MT5Connector
from core import strategy
import config


def to_tf(name):
    import MetaTrader5 as mt5
    return getattr(mt5, f"TIMEFRAME_{name}", mt5.TIMEFRAME_M5)


def atr(bars, i, period=14):
    """ATR at index i over true ranges (requires i >= period)."""
    if i < period:
        return None
    trs = []
    for j in range(i - period, i):
        hi, lo, pc = bars[j]["high"], bars[j]["low"], bars[j - 1]["close"]
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    return sum(trs) / len(trs)


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

    info = mt5.symbol_info(symbol)
    point = info.point
    bars = [
        {"time": c[0], "open": c[1], "high": c[2], "low": c[3],
         "close": c[4], "tick_volume": c[5], "spread": c[6]}
        for c in rates
    ]
    closes = [b["close"] for b in bars]

    # precompute BB + signals (same scan as backtest.py)
    upper, middle, lower = strategy.bollinger(
        bars, period=config.BB_PERIOD, deviations=config.BB_DEVIATIONS)
    bw = strategy.bandwidth(upper, lower, middle)
    P, S = config.BB_PERIOD, config.BB_BW_SMOOTHING

    # also precompute ATR per index
    atrs = [atr(bars, i) for i in range(len(bars))]

    results = {"win": 0, "loss": 0, "open": 0}
    total_profit_points = 0.0
    spread_points = (info.spread if info else 20) / 1.0  # bid-ask in points

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
        if not action:
            continue

        # ----- simulate the trade -----
        atr_val = atrs[i] if atrs[i] else closes[i] * 0.001
        stop_dist = atr_val * config.BB_STOP_ATR_MULT
        tp_dist = stop_dist * config.BB_RR

        entry = closes[i]
        # add realistic spread cost at entry for buy (ask > bid)
        cost_points = spread_points
        entry_eff = entry + point * cost_points  # buy pays spread

        sl = entry - stop_dist if action == "buy" else entry + stop_dist
        tp = entry + tp_dist if action == "buy" else entry - tp_dist

        # walk forward up to 200 bars to find SL or TP hit
        outcome = "open"
        for k in range(i + 1, min(i + 200, len(bars))):
            hi, lo = bars[k]["high"], bars[k]["low"]
            if action == "buy":
                if lo <= sl:
                    outcome = "loss"
                    break
                if hi >= tp:
                    outcome = "win"
                    break
            else:
                if hi >= sl:
                    outcome = "loss"
                    break
                if lo <= tp:
                    outcome = "win"
                    break

        if outcome == "win":
            results["win"] += 1
            total_profit_points += tp_dist - cost_points
        elif outcome == "loss":
            results["loss"] += 1
            total_profit_points -= stop_dist + cost_points
        else:
            results["open"] += 1

    n = results["win"] + results["loss"]
    wr = results["win"] / n * 100 if n else 0.0
    print(f"--- {symbol} {tf_name}, last {days}d ---")
    print(f"wins: {results['win']}  losses: {results['loss']}  still open: {results['open']}")
    print(f"win rate: {wr:.1f}%")
    print(f"net profit (points, incl {spread_points:.0f}-pt spread): {total_profit_points:.0f}")
    conn.shutdown()


if __name__ == "__main__":
    main()