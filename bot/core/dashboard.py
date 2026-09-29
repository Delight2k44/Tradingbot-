"""Terminal dashboard for the pattern bot.

Renders a live status panel each cycle: account, day P&L vs risk caps, per-market
price/zones/position, and a rolling event feed.

Only used when stdout is an interactive console (isatty). When piped/redirected the
bot keeps printing plain event lines so logs stay clean.
"""
import os
import sys
from collections import deque

# --- ANSI color helpers (safe when not a tty) -------------------------------
_USE_COLOR = sys.stdout.isatty()


def _col(code, text):
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def green(t):
    return _col("32", t)


def red(t):
    return _col("31", t)


def yellow(t):
    return _col("33", t)


def cyan(t):
    return _col("36", t)


def bold(t):
    return _col("1", t)


def dim(t):
    return _col("2", t)


SYMBOL_LABEL = {
    "USTECm": "Nasdaq 100 (USTECm)",
    "XAUEURm": "Gold / EUR (XAUEURm)",
    "US500m": "S&P 500 (US500m)",
    "XAUUSDm": "Gold / USD (XAUUSDm)",
}


class Dashboard:
    def __init__(self, max_events=40):
        self.enabled = _USE_COLOR and sys.stdout.isatty()
        self.events = deque(maxlen=max_events)

    def add_event(self, msg, color=None):
        stamp = f"{dt_str()} {msg}"
        if self.enabled and color:
            stamp = color(stamp)
        self.events.append(stamp)

    def render(self, state):
        """state keys:
            mode, account (login/currency), balance, equity,
            day_pnl, day_start, target, loss_cap_pct, can_trade,
            markets: list of {
                sym, price, bid, ask, spread, zones, position (str|None),
                pos_profit, status, last_signal, h1_idx
            }
        """
        if not self.enabled:
            return None
        lines = []
        sep = "=" * 62
        lines.append(bold(" EXNESS PATTERN BOT ") + cyan(f"  mode={state['mode']}") +
                     dim(f"  {dt_str()}"))
        lines.append(sep)

        acct = state["account"]
        pnl = state["day_pnl"]
        pnl_col = green if pnl >= 0 else red
        lines.append(f" {cyan('Account')}  {acct['login']} ({acct['currency']})   "
                     f"{cyan('Balance')} {state['balance']:,.2f}   "
                     f"{cyan('Equity')} {state['equity']:,.2f}")
        trgt = state["target"]
        cap = state.get("loss_cap_pts")
        cap_txt = f"  cap -{state['loss_cap_pct']}% = -{cap:.2f}" if cap else ""
        lines.append(f" {cyan('Day P&L')}  {pnl_col(f'{pnl:+,.2f}')}"
                     f"  {cyan('start')} {state['day_start']:,.2f}"
                     f"  {cyan('target')} +{trgt:.0f}{cap_txt}"
                     f"  -> {green('OK') if state['can_trade'] else red('HALTED')}")

        # per-market block
        for m in state["markets"]:
            lines.append("")
            lines.append(bold(f" {m['sym']}") + dim(f"  {SYMBOL_LABEL.get(m['sym'], '')}"))
            lines.append(f"  {cyan('Price')} {m['price']:,.2f}   {cyan('bid')} {m['bid']:,.2f}  "
                         f"{cyan('ask')} {m['ask']:,.2f}  {cyan('spread')} {m['spread']}")
            if m["zones"]:
                ztxt = " | ".join(f"{lo:,.2f}-{hi:,.2f}" for lo, hi in m["zones"])
                lines.append(f"  {cyan('Zones')}  {dim(ztxt)}")
            pos = m.get("position")
            if pos:
                pp = m.get("pos_profit", 0.0)
                lines.append(f"  {cyan('Position')}  {m['position']}"
                             f"  {cyan('profit')} {pnl_col(f'{pp:+,.2f}')}")
            lines.append(f"  {cyan('Signal')}  {m['status']}")

        lines.append("")
        lines.append(sep)
        if self.events:
            lines.append(dim(" Events"))
            for e in list(self.events)[-8:]:
                lines.append(f"   {e}")
        lines.append(sep)
        return "\n".join(lines)

    def show(self, state):
        if not self.enabled:
            return
        os.system("cls" if os.name == "nt" else "clear")
        print(self.render(state), flush=True)


def dt_str():
    import datetime as _dt
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")