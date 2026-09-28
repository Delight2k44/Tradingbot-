"""Thin wrapper around the MetaTrader5 Python API.
Keeps ALL MetaTrader5 usage in one place so the rest of the bot is testable.
"""
import MetaTrader5 as mt5


class MT5Connector:
    def __init__(self, path=None):
        self.path = path

    def connect(self, login=0, password="", server=""):
        if login and str(login).isdigit():
            login = int(login)
        if not mt5.initialize(self.path, login=login, password=password, server=server):
            return False, mt5.last_error()
        # ensure the trading is available
        if not mt5.terminal_info().trade_allowed:
            return False, ("Algo trading disabled", "")
        return True, ""

    def shutdown(self):
        mt5.shutdown()

    def account(self):
        return mt5.account_info()

    def balance(self):
        info = mt5.account_info()
        return info.balance if info else 0.0

    def symbol_info(self, symbol):
        return mt5.symbol_info(symbol)

    def rates(self, symbol, timeframe, count):
        """Return list of bars for symbol/timeframe: [time, o, h, l, c, tick_volume, spread]"""
        return mt5.copy_rates_from_pos(symbol, timeframe, 0, count)

    def make_order(self, symbol, side, volume, price, sl, tp, magic, comment=""):
        order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 10,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        return result

    def positions(self, symbol=None, magic=None):
        pos = mt5.positions_get(symbol=symbol) or []
        if magic is not None:
            pos = [p for p in pos if p.magic == magic]
        return pos

    def history_deals(self, start, end):
        return mt5.history_deals_get(start, end)

    def deals_today(self, magic, symbol=None):
        import datetime as dt
        now = dt.datetime.now()
        start = dt.datetime(now.year, now.month, now.day)
        deals = mt5.history_deals_get(start, now)
        if not deals:
            return 0
        n = 0
        for d in deals:
            if d.magic == magic and (symbol is None or d.symbol == symbol):
                if d.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL):
                    n += 1
        return n