"""CSV trade logging - the honest witness. Writes every trade to logs/."""
import os
import csv
import datetime as dt


class TradeLogger:
    def __init__(self, log_dir="logs", symbol="USDZAR"):
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(log_dir, f"trades_{symbol}.csv")
        self._init_file()

    def _init_file(self):
        if os.path.exists(self.path):
            return
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "position_id", "time", "type", "symbol", "volume",
                "price", "sl", "tp", "profit", "setup", "spread_points", "comment",
            ])

    def log_trade(self, ticket, deal_type, symbol, volume, price, sl, tp,
                  profit, setup="", spread_points=0.0, comment=""):
        row = [
            ticket,
            dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            deal_type, symbol, volume,
            price, sl, tp, profit, setup, spread_points, comment,
        ]
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

    def log_message(self, msg, symbol="USDZAR"):
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([0, dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "NOTE", symbol, "", "", "", "", "", msg, "", ""])