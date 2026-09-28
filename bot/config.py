# Configuration for the Exness trading bot.
# Values loaded from bot/.env (secrets + machine-specific) then overridden here.
# No balance hardcoding: risk is always % of LIVE account balance.

from core.env import load_env, get as env_get
load_env()

# --- MT5 connection (from .env) ---
MT5_LOGIN = env_get("MT5_LOGIN")           # Exness account login (demo). Empty = terminal already logged in.
MT5_PASSWORD = env_get("MT5_PASSWORD")     # Not needed if terminal is already logged in.
MT5_SERVER = env_get("MT5_SERVER")         # e.g. "Exness-Real7". Empty = current terminal connection.
MT5_PATH = env_get("MT5_PATH", r"C:\Program Files\Exness MetaTrader 5\terminal64.exe")

# --- Symbols traded (from .env, default USDZAR) ---
SYMBOLS = [_s.strip() for _s in env_get("SYMBOLS", "USDZAR").split(",") if _s.strip()]

# --- Risk (percent of LIVE balance) ---
RISK_PER_TRADE_PCT = 1.0    # max loss per trade
DAILY_LOSS_PCT = 3.0        # stop all trading for the day after this loss
DAILY_TARGET_ZAR = 300.0    # stop after +R300 (set 0 to disable)
MAX_TRADES_PER_DAY = 20     # hard safety cap on number of trades/day

# --- Bollinger strategy (squeeze -> breakout) ---
BB_TIMEFRAME = "M5"         # M5 primary, M15 backup
BB_PERIOD = 20
BB_DEVIATIONS = 2.0
BB_BW_SMOOTHING = 20        # BandWidth moving-average length for squeeze detection
BB_SQUEEZE_RATIO = 1.0      # BW < avg * ratio => squeeze
BB_STOP_ATR_MULT = 3.0      # stop distance = ATR * mult
BB_RR = 1.5                 # take-profit = stop * RR

# --- Logging ---
LOG_DIR = "logs"
JOURNAL_DIR = "journal"
SCREENSHOT_DIR = "research/screenshots"