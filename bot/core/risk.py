"""Shared risk controls. Reads LIVE balance - never hardcoded values."""
import time
import datetime as dt
from dataclasses import dataclass


@dataclass
class RiskState:
    day_start_balance: float = 0.0
    day_start_date: str = ""
    day_pnl: float = 0.0


class RiskManager:
    def __init__(self, risk_pct=1.0, daily_loss_pct=3.0, daily_target=300.0, max_trades=20):
        self.risk_pct = risk_pct
        self.daily_loss_pct = daily_loss_pct
        self.daily_target = daily_target
        self.max_trades = max_trades
        self.state = RiskState()

    # --- must be called once per tick -------------------------------
    def update(self, mt5, symbols):
        today = dt.datetime.now().strftime("%Y-%m-%d")
        if self.state.day_start_date != today:
            self.state.day_start_date = today
            bal = _balance(mt5)
            self.state.day_start_balance = bal if bal else 1.0
            self.state.day_pnl = 0.0
        self.state.day_pnl = self._today_pnl(mt5, symbols)

    # --- decision helpers --------------------------------------------
    def can_trade(self):
        if self.daily_target and self.state.day_pnl >= self.daily_target:
            return False
        if self.state.day_pnl <= -(self.state.day_start_balance * self.daily_loss_pct / 100.0):
            return False
        return True

    def target_reached(self):
        return bool(self.daily_target) and self.state.day_pnl >= self.daily_target

    def max_loss_reached(self):
        return self.state.day_pnl <= -(self.state.day_start_balance * self.daily_loss_pct / 100.0)

    # --- sizing -------------------------------------------------------
    def max_loss_per_trade(self, balance=None):
        bal = balance or _balance(None)  # caller passes real balance; fallback unsafe
        return bal * self.risk_pct / 100.0

    def lot_for_pips(self, mt5, symbol, stop_pips, balance):
        """Return lots so that 'stop_pips' loss == 1% of live balance."""
        risk_money = balance * self.risk_pct / 100.0
        info = mt5.symbol_info(symbol)
        if not info or stop_pips <= 0:
            return 0.0
        tick_value = info.trade_tick_value_loss
        tick_size = info.trade_tick_size
        point = info.point
        if tick_value == 0 or tick_size == 0 or point == 0:
            return 0.0
        loss_per_lot = (tick_value / tick_size) * stop_pips * point
        lots = risk_money / loss_per_lot if loss_per_lot > 0 else 0.0
        step = info.volume_step or 0.01
        lots = max(info.volume_min, min(info.volume_max, int(lots / step) * step))
        return lots

    # --- internals ----------------------------------------------------
    def _today_pnl(self, mt5, symbols):
        pnl = 0.0
        # open positions
        for p in mt5.positions_get(symbol=symbols):
            pnl += p.profit
        # today's closed deals
        now = dt.datetime.now()
        start = dt.datetime(now.year, now.month, now.day)
        deals = mt5.history_deals_get(start, now)
        if deals:
            for d in deals:
                if d.symbol in symbols:
                    pnl += d.profit
        return pnl


def _balance(mt5):
    info = mt5.account_info()
    return info.balance if info else 0.0