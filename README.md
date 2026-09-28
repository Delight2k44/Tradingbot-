# exness-trading-bots

Two MT5 Expert Advisors (scalping + swing) trading a ZAR (rand) Exness demo account.
Same core foundation (risk manager, position sizing, logger), two different rule-sets.

## Project rules (agreed)
- Exness broker, ZAR (rand) demo account — account & target denominated in Rands
- Instruments: GOLD (XAUUSDm) and other majors — NOT ZAR pairs
- Scalping: Bollinger squeeze -> breakout, M5 primary / M15 backup, R300 daily profit target
- Daily loss cap: stop all trading for the day at 3% loss (combined across bots)
- Max risk per trade: 1%
- Swing: buy-low/sell-high rules (H4 + time-based exit, data pending)
- LLM: journalist only, never executes trades
- 3-month demo test before any real money

## Structure
- `core/`    — shared MQL5: risk manager, position sizing, logger
- `scalping/`— scalping EA (BB squeeze)
- `swing/`   — swing EA
- `journal/` — LLM-generated trade journal
- `logs/`    — raw trade logs
- `research/`— user notes, strategy rules