# Project Overview — Exness Trading Bot

## Mission
Build a trading bot that finds a *honest, tested* edge in the market and executes it
disciplined on an Exness demo account (ZAR/rand denominated). The whole project is
built around one hard rule: **no strategy is traded until data proves it**. Every claim
gets backtested against real MT5 history, and nothing is declared a winner on opinion.

## Goal
- Trade **gold (XAUUSDm) and majors** — NOT ZAR pairs (ZAR is only the account currency)
- **R300 daily profit target** in Rands — stop trading for the day once hit
- **1% max risk per trade**, 3% daily loss cap — never risk the account chasing a day
- Run both a **scalping** and a **swing** brain on the same tested core
- 3-month demo test before any real money
- **LLM (Ollama, local) as journalist only** — records, never executes

## Architecture — how it works
```
Exness broker
    ↑  (MT5 terminal open + logged into demo)
MetaTrader 5 terminal on the PC
    ↑  (MetaTrader5 Python API)
bot.py — main loop on the terminal
    ├── core/risk.py          RiskManager: sizing, 1%/trade, 3%/day cap, R300 target (live balance)
    ├── core/logger.py        CSV trade logging (the honest witness)
    ├── core/mt5_connector.py All MT5 API calls wrapped in one place
    ├── core/strategy.py      Bollinger squeeze -> breakout engine
    ├── core/smc.py           SMC breaker/order-block engine (ported)
    └── core/env.py           .env loader (secrets stay out of git)
backtest.py / mean_reversion.py / hybrid.py / smc_projection.py / pnl_projection.py
    └── replay the strategy over real MT5 history and report win rate + net points
```
The bot never "decides" anything — it checks coded rules. Users define the rules;
the code obeys; the backtests judge.

## Tech stack
- **Python 3.14.3** — the bot language
- **MetaTrader5 python package (v5.0.5735)** — connects to the MT5 terminal
- **numpy** — signal math (indicator engine)
- **pandas** — used in the original SMC code (strategy scripts)
- **MT5 terminal** (Exness build) at `C:\Program Files\MetaTrader 5 EXNESS`
- **Exness demo account** — ZAR base currency, balance R500
- **Git / GitHub** — repo `Delight2k44/Tradingbot-`, secrets gitignored
- **Ollama** (planned) — local journal LLM, advisory only
- **pip** via `python -m pip` (standalone pip is policy-blocked on this PC)

## What's built (status)
| Piece | Status |
|---|---|
| Repo scaffold + README + ROADMAP | DONE |
| .env secret handling (gitignored) | DONE |
| RiskManager (live balance, 1%/3%/R300) | DONE |
| Trade logger (CSV) | DONE |
| MT5 connector, connection to Exness demo verified | DONE (ZAR, R500) |
| bot.py main loop (dry-run + live) | DONE / dry-run tested |
| Bollinger squeeze -> breakout engine | DONE |
| SMC engine (ported from user code) | DONE |
| Backtest + P&L projection harness | DONE |
| Hybrid strategy (buy-low/sell-high + trend filter + time exit) | DONE |
| Swing bot | PENDING winner |
| Scalping bot | PENDING winner |
| Ollama journalist | PENDING |
| 3-month demo test | PENDING |PENDING |

## Strategy testing — honest results (real MT5 history, incl spread)
| Strategy | Best tested config | Win rate | Verdict |
|---|---|---|---|
| Bollinger squeeze breakout | USDZARm M5 | 45.8% | loses to spread |
| Buy-low/sell-high (mean rev) | USDZARm H4 + 8-bar exit | 84.6% (13 trades) | break-even |
| SMC + symmetric rejection | gold M15 | 30.0% | losing |
| HYBRID | gold H1 | 54.3% (35) | still negative |

**Conclusion:** win-rate leg exists (whole > 50% on ZAR; hybrid holds 54% gold H1),
but sample sizes are too small and spread eats the scalping timeframe. The bottleneck
right now is **data**, not ideas. Next step: download months of H1/H4 gold + EURUSD
history, rerun, and only then pick the bot's core.

## Rules agreed (no hardcodes, live balance always)
- 1% risk per trade (of live balance)
- 3% daily loss cap → stop all trading for the day
- R300 daily target → stop trading once reached
- Instruments: gold + majors, account in Rands
- LLM/journalist never executes trades
- Screenshots → patterns → written rules → coded strategy

## Research workflow
1. Upload screenshots into research/screenshots/
2. Study patterns together, turn them into written rules
3. Code the rules, backtest honestly, only then trade

## Current blockers / next steps
- [ ] User opens H1/H4 charts in MT5 to unlock multi-month history (data bottleneck)
- [ ] Rerun hybrid + mean-reversion on 6-12 months of data
- [ ] Have user narrate/OCR the 13 screenshots (current model cannot read images)
- [ ] Build swing bot on whatever the data names the winner