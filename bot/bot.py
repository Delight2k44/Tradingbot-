"""Scalping bot - Bollinger squeeze -> breakout. Runs on the terminal, drives MT5.

USAGE:
    python bot.py                # live/demo trading against MT5
    python bot.py --dry-run      # same logic, but prints signals, no real orders
"""
import sys
import time
import argparse
import datetime as dt

import MetaTrader5 as mt5

from core.mt5_connector import MT5Connector
from core.risk import RiskManager
from core.logger import TradeLogger
from core import strategy
import config


def tf_value(name):
    return getattr(mt5, f"TIMEFRAME_{name}")


def run():
    argp = argparse.ArgumentParser()
    argp.add_argument("--dry-run", action="store_true", help="no real orders")
    argp.add_argument("--cycles", type=int, default=0, help="max loop iterations (0=infinite)")
    args = argp.parse_args()

    # --- connect to MT5 (running terminal on this PC) ---
    conn = MT5Connector(config.MT5_PATH)
    ok, msg = conn.connect(login=config.MT5_LOGIN, password=config.MT5_PASSWORD,
                           server=config.MT5_SERVER)
    if not ok:
        print("MT5 connect failed:", msg)
        sys.exit(1)

    print(f"Connected. Account: {conn.account().login} | {conn.account().currency} "
          f"| balance {conn.balance()}")

    risk = RiskManager(config.RISK_PER_TRADE_PCT, config.DAILY_LOSS_PCT,
                       config.DAILY_TARGET_ZAR, config.MAX_TRADES_PER_DAY)
    symbol = config.SYMBOLS[0]
    logger = TradeLogger(config.LOG_DIR, symbol)
    tf = tf_value(config.BB_TIMEFRAME)
    magic = int(dt.datetime.now().strftime("%Y%m%d") + "01")

    last_candle_time = 0
    cycle = 0
    logger.log_message("Bot started on " + symbol)

    while True:
        cycle += 1
        risk.update(conn, [symbol])

        if not risk.can_trade():
            reason = "target reached" if risk.target_reached() else "daily loss cap hit"
            print(f"[{dt.datetime.now():%H:%M:%S}] Risk halt: {reason}")
            logger.log_message(f"Risk halt: {reason}")
            time.sleep(60)
            continue

        if conn.positions(symbol=symbol, magic=magic):
            time.sleep(3)      # already in a trade, wait
            continue

        # --- get candles on the strategy timeframe ---
        candles = conn.rates(symbol, tf, config.BB_PERIOD + config.BB_BW_SMOOTHING + 5)
        if candles is None or len(candles) == 0:
            print("No candle data")
            time.sleep(10)
            continue

        # --- only evaluate on a NEW closed candle ---
        this_candle_time = candles[-1][0]
        if this_candle_time == last_candle_time:
            time.sleep(2)
            continue
        last_candle_time = this_candle_time

        bars = [
            {"time": c[0], "open": c[1], "high": c[2], "low": c[3],
             "close": c[4], "tick_volume": c[5], "spread": c[6]}
            for c in candles
        ]

        sig = strategy.detect_signal(
            bars,
            period=config.BB_PERIOD,
            deviations=config.BB_DEVIATIONS,
            bw_smoothing=config.BB_BW_SMOOTHING,
            squeeze_ratio=config.BB_SQUEEZE_RATIO,
        )

        if sig["action"] is None:
            time.sleep(2)
            continue

        # -------- signal detected: build the trade --------
        si = conn.symbol_info(symbol)
        if not si:
            continue

        going_long = sig["action"] == "buy"
        price = si.ask if going_long else si.bid
        bid, ask = si.bid, si.ask
        spread_points = (ask - bid) / si.point if si.point else 0.0

        # stop distance from ATR on the strategy timeframe
        atr_v = _atr_value(bars, period=14)
        stop_dist = atr_v * config.BB_STOP_ATR_MULT

        if going_long:
            sl = price - stop_dist
            tp = price + stop_dist * config.BB_RR
        else:
            sl = price + stop_dist
            tp = price - stop_dist * config.BB_RR

        lots = risk.lot_for_pips(conn, symbol, stop_dist / si.point, conn.balance())
        if lots <= 0:
            print("cannot compute lots")
            continue

        # daily trade cap
        if conn.deals_today(magic, symbol) >= config.MAX_TRADES_PER_DAY:
            print("daily trade cap reached")
            time.sleep(60)
            continue

        setup = f"BBsqueeze {'LONG' if going_long else 'SHORT'} bw={sig['bw_ratio']:.2f}"

        if args.dry_run:
            print(f"[DRY] {dt.datetime.now():%H:%M:%S} {symbol} {setup} "
                  f"lots={lots:.2f} px={price:.5f} sl={sl:.5f} tp={tp:.5f}")
            logger.log_trade(0, "dry", symbol, lots, price, sl, tp, 0.0, setup, spread_points)
            time.sleep(3)   # simulated hold in dry-run so it doesn't spam
            continue

        res = conn.make_order(symbol, sig["action"], lots, price, sl, tp,
                              magic, comment=setup)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[TRADE] {setup} lots={lots:.2f} @ {price:.5f}")
            logger.log_trade(res.order, sig["action"], symbol, lots, price, sl, tp,
                             0.0, setup, spread_points)
        else:
            rc = res.retcode if res else "?"
            msg_ = res.comment if res else ""
            print(f"Order failed rc={rc} {msg_}")

        time.sleep(2)

        if args.cycles and cycle >= args.cycles:
            break

    conn.shutdown()
    print("Stopped.")


def _atr_value(bars, period=14):
    """Simple True Range average over the last N bars (close-based approximation)."""
    if len(bars) < period + 1:
        return 0.0
    trs = []
    for i in range(len(bars) - period, len(bars)):
        b = bars[i]
        prev = bars[i - 1]["close"]
        tr = max(b["high"] - b["low"],
                 abs(b["high"] - prev),
                 abs(b["low"] - prev))
        trs.append(tr)
    return sum(trs) / len(trs)


if __name__ == "__main__":
    run()