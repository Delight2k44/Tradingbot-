"""Pattern-strategy bot (L1-L4 + demand zones + wick stop). LONG only.

Trades the markets chosen from backtesting: USTECm (Nasdaq) + XAUEURm (gold/EUR).
Signal logic is shared with the backtester via core/pattern_signal.py.

USAGE:
    python pattern_bot.py              # live/demo trading against MT5
    python pattern_bot.py --dry-run    # same logic, prints signals, no orders

Risk model (config.py): 1% risk/trade, 3% daily loss cap, R300 daily target,
1h-50-EMA trend filter, reject stops wider than 3x ATR(14).
"""
import sys
import time
import argparse
import datetime as dt

import MetaTrader5 as mt5

from core.mt5_connector import MT5Connector
from core.risk import RiskManager
from core.logger import TradeLogger
from core.pattern_signal import latest_signal
import config


def main():
    argp = argparse.ArgumentParser()
    argp.add_argument("--dry-run", action="store_true", help="no real orders")
    argp.add_argument("--cycles", type=int, default=0, help="max loop iterations (0=infinite)")
    args = argp.parse_args()

    symbols = config.SYMBOLS
    conn = MT5Connector(config.MT5_PATH)
    ok, msg = conn.connect(login=config.MT5_LOGIN, password=config.MT5_PASSWORD,
                           server=config.MT5_SERVER)
    if not ok:
        print("MT5 connect failed:", msg)
        sys.exit(1)

    print(f"Connected. Account: {conn.account().login} | {conn.account().currency} "
          f"| balance {conn.balance()} | symbols={symbols}")

    risk = RiskManager(conn, config.RISK_PER_TRADE_PCT, config.DAILY_LOSS_PCT,
                       config.DAILY_TARGET_ZAR, config.MAX_TRADES_PER_DAY)
    magic = int(dt.datetime.now().strftime("%Y%m%d") + "02")

    logger = TradeLogger(config.LOG_DIR, "+".join(symbols))
    loggers = {s: TradeLogger(config.LOG_DIR, s) for s in symbols}

    last_m15_time = {s: 0 for s in symbols}
    entered_zones = {}   # sym -> {(zone, h1_idx)} windows already acted on
    cycle = 0
    logger.log_message(f"Pattern bot started on {symbols} (magic={magic})")

    while True:
        cycle += 1
        risk.update(conn, symbols)

        if not risk.can_trade():
            reason = "target reached" if risk.target_reached() else "daily loss cap hit"
            print(f"[{dt.datetime.now():%H:%M:%S}] Risk halt: {reason}")
            logger.log_message(f"Risk halt: {reason}")
            time.sleep(60)
            continue

        for sym in symbols:
            _process_symbol(sym, conn, risk, magic, args, loggers, last_m15_time,
                            logger, entered_zones)

        if args.cycles and cycle >= args.cycles:
            break
        time.sleep(15)

    conn.shutdown()
    print("Stopped.")


def _process_symbol(sym, conn, risk, magic, args, loggers, last_m15_time, log,
                    entered_zones):
    # only evaluate on a new closed M15 candle
    m15 = conn.rates(sym, mt5.TIMEFRAME_M15, 3)
    if m15 is None or len(m15) == 0:
        print(f"{sym}: no data")
        return
    this_m15_time = m15[-1][0]
    if this_m15_time == last_m15_time[sym]:
        return
    last_m15_time[sym] = this_m15_time

    if conn.positions(symbol=sym, magic=magic):
        return  # one trade at a time per symbol

    sig = latest_signal(sym, conn,
                        ema_filter=config.USE_1H_EMA_TREND_FILTER,
                        point_off=config.PATTERN_POINT_OFFSET)
    if sig is None:
        print(f"{sym}: no fresh signal")
        return

    # dedup: one setup per (zone, H1 window) - matches the backtest rule
    key = (sig["zone"], sig["h1_idx"])
    done = entered_zones.setdefault(sym, set())
    if key in done:
        print(f"{sym}: zone#{sig['zone']} already entered this H1 window")
        return
    done.add(key)

    si = conn.symbol_info(sym)
    if not si:
        return

    price = si.ask
    point = si.point
    entry_r = sig["entry_r"]
    sl = sig["sl"]
    tp1 = sig["tp1"]
    tp2 = sig["tp2"]
    stop_pts = entry_r / point if point else 0.0

    lots = risk.lot_for_pips(conn, sym, stop_pts, conn.balance())
    if lots <= 0:
        print(f"{sym}: cannot size (stop_pts={stop_pts:.1f})")
        return

    if conn.deals_today(magic, sym) >= config.MAX_TRADES_PER_DAY:
        print(f"{sym}: daily trade cap reached")
        return

    # risk split: 15m-only triggers get half size per spec
    if sig["tf"].startswith("15m"):
        lots = max(si.volume_min, round(lots * config.RISK_PER_TRADE_PCT_15M
                                        / config.RISK_PER_TRADE_PCT
                                        / si.volume_step) * si.volume_step)

    setup = f"{sig['tf']} zone#{sig['zone']} R={entry_r:.0f} stop={stop_pts:.0f}p"
    spread_points = (si.ask - si.bid) / point if point else 0.0

    if args.dry_run:
        print(f"[DRY] {dt.datetime.now():%H:%M:%S} {sym} {setup} "
              f"lots={lots:.2f} entry~{price:.4f} sl={sl:.4f} "
              f"tp1={tp1:.4f} tp2={tp2:.4f}")
        loggers[sym].log_trade(0, "dry", sym, lots, price, sl, tp2, 0.0, setup,
                               spread_points)
        time.sleep(3)  # dry-run pacing
        return

    # TWO orders: half at TP1 (1R), half at TP2 (2R) - matches backtest PnL
    full = max(si.volume_min, round(lots / si.volume_step) * si.volume_step)
    half = max(si.volume_min, round(full / 2 / si.volume_step) * si.volume_step)

    r1 = conn.make_order(sym, "buy", half, price, sl, tp1, magic, comment=f"{setup} TP1")
    if r1 and r1.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[TRADE] {sym} {setup} half@{tp1:.4f} {half} @ {price:.4f}")
        loggers[sym].log_trade(r1.order, "buy", sym, half, price, sl, tp1, 0.0,
                               setup, spread_points)
        r2 = conn.make_order(sym, "buy", full - half, price, sl, tp2, magic,
                             comment=f"{setup} TP2")
        if r2 and r2.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[TRADE] {sym} {setup} rest@{tp2:.4f} {full - half} @ {price:.4f}")
            loggers[sym].log_trade(r2.order, "buy", sym, full - half, price, sl,
                                   tp2, 0.0, setup, spread_points)
        else:
            rc = r2.retcode if r2 else "?"
            print(f"Order2 failed rc={rc} {r2.comment if r2 else ''} (TP1 leg open)")
    else:
        rc = r1.retcode if r1 else "?"
        print(f"Order1 failed rc={rc} {r1.comment if r1 else ''}")
        # rescue: retry as a single full position to TP2
        r3 = conn.make_order(sym, "buy", full, price, sl, tp2, magic,
                             comment=f"{setup} FULL")
        if r3 and r3.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[TRADE] {sym} {setup} full@{tp2:.4f} {full} @ {price:.4f}")
            loggers[sym].log_trade(r3.order, "buy", sym, full, price, sl, tp2,
                                   0.0, setup, spread_points)


if __name__ == "__main__":
    main()