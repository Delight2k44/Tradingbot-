"""SMC projection: replay breaker/OB + symmetric rejection signals over real
MT5 history and compute win rate + net points.

USAGE:
    python smc_projection.py XAUUSDm M15 30
"""
import sys
import datetime as dt

from core.mt5_connector import MT5Connector
from core.smc import smc_signals
import config


def to_tf(name):
    import MetaTrader5 as mt5
    return getattr(mt5, f"TIMEFRAME_{name}", mt5.TIMEFRAME_M15)


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSDm"
    tf_name = sys.argv[2] if len(sys.argv) > 2 else "M15"
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
    spread_points = info.spread if info else 20
    bars = [
        {"time": c[0], "open": c[1], "high": c[2], "low": c[3],
         "close": c[4], "tick_volume": c[5], "spread": c[6]}
        for c in rates
    ]

    signals = smc_signals(bars, wick_mult=2.2, swing_len=4)
    print(f"{symbol} {tf_name} {days}d: {len(bars)} bars, {len(signals)} signals")

    wins = losses = open_ = 0
    total_points = 0.0
    for sig in signals:
        entry, sl, tp, action = sig["entry"], sig["sl"], sig["tp"], sig["action"]
        if np_isnan(sl) or np_isnan(tp) or tp == entry:
            continue
        outcome = "open"
        exit_price = None
        for k in range(sig["bar"], min(sig["bar"] + 200, len(bars))):
            hi, lo = bars[k]["high"], bars[k]["low"]
            if action == "buy":
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

        if outcome == "win":
            wins += 1
            total_points += abs(tp - entry) / point - spread_points
        elif outcome == "loss":
            losses += 1
            total_points -= abs(entry - sl) / point + spread_points
        else:
            open_ += 1

    n = wins + losses
    wr = wins / n * 100 if n else 0.0
    print(f"wins: {wins}  losses: {losses}  still open: {open_}")
    print(f"WIN RATE: {wr:.1f}%")
    print(f"net points ({spread_points:.0f}-pt spread): {total_points:.0f}")
    conn.shutdown()


def np_isnan(v):
    try:
        return v != v
    except Exception:
        return False


if __name__ == "__main__":
    main()