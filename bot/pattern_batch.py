"""Fast multi-asset test for the pattern engine (L1-L4 + zones + wick-stop).
Signal logic lives in core/pattern_signal.py - shared with the live bot.

USAGE:
    python pattern_batch.py                     # default symbol set, 60d
    python pattern_batch.py 30 XAUUSDM XAGUSDM  # custom days + symbols
"""
import sys

from core.pattern_signal import scan_symbol
from core.mt5_connector import MT5Connector
import config


def main():
    days = 60
    args = sys.argv[1:]
    if args and args[0].isdigit():
        days = int(args[0])
        args = args[1:]
    symbols = args if args else [
        "USTECm", "US500m", "UK100m", "AUS200m",
        "XAUUSDm", "XAUEURm", "XAUGBPm", "XAUAUDm", "XPTUSDm", "XPDUSDm",
        "UKOILm",
        "EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm", "USDCHFm", "USDCADm", "NZDUSDm",
        "BTCUSDm", "ETHUSDm",
    ]

    conn = MT5Connector(config.MT5_PATH)
    ok, _ = conn.connect(login=config.MT5_LOGIN, password=config.MT5_PASSWORD,
                         server=config.MT5_SERVER)
    if not ok:
        print("connect failed")
        return

    print(f"{'SYMBOL':<10} {'type':<10} {'trades':>6} {'wins':>5} {'losses':>6} "
          f"{'WR%':>6} {'netpts':>11}")
    print("-" * 70)
    results = []
    for sym in symbols:
        base = sym[:3].upper()
        kind = "FX" if len(sym) == 6 and base in ("EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY") \
            else ("INDEX" if sym in ("US500m", "USTECm", "UK100m", "AUS200m") \
            else ("OIL" if sym in ("UKOILm", "WTIUSDm") \
            else ("METAL" if sym.startswith(("XAU", "XAG", "XPT", "XPD")) else "CRYPTO")))
        try:
            cands = scan_symbol(sym, conn, days=days)
        except Exception as e:
            print(f"{sym:<10} {kind:<10} {'ERR: ' + str(e)[:40]:>45}")
            continue
        if cands is None:
            print(f"{sym:<10} {kind:<10} {'no data':>24}")
            continue
        n = len(cands)
        wins = sum(1 for c in cands if c["outcome"] in ("full", "partial"))
        losses = n - wins
        wr = wins / n * 100 if n else 0.0
        net = sum(c["pts"] for c in cands)
        results.append((sym, kind, n, wr, net))
        print(f"{sym:<10} {kind:<10} {n:>6} {wins:>5} {losses:>6} {wr:>6.1f} {net:>11.0f}")
    conn.shutdown()

    print()
    print("=== sorted by net points (n>=5) ===")
    for sym, kind, n, wr, net in sorted(results, key=lambda x: -x[4]):
        if n >= 5:
            print(f"{sym:<10} {kind:<10} trades={n:>4} WR={wr:>5.1f}%  net={net:>11.0f}")


if __name__ == "__main__":
    main()