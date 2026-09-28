# Implementation Roadmap

## Where we are (marked with [DONE])

### Phase 0 - Foundations
- [DONE] Repo scaffold (core/, scalping/, swing/, logs/, journal/, research/)
- [DONE] core/RiskManager.mqh - live-balance sizing, 1%/trade, 3%/day cap, R300 target
- [DONE] core/TradeLogger.mqh - CSV trade logging
- [DONE] Scalping EA skeleton (Bollinger squeeze -> breakout)
- [NEXT] Compile scalping EA in MetaEditor, fix errors
- [NEXT] Backtest in MT5 Strategy Tester (M5 vs M15)
- [TODO] Swing EA skeleton (buy-low/sell-high rules - pending your rules)
- [TODO] Ollama LLM journalist (local, advisory only)
- [TODO] Mainnet: push to Tradingbot- repo after stable

### Rules agreed (no hardcodes, live balance always)
- Exness ZAR demo account
- 1% risk per trade (of live balance)
- 3% daily loss cap -> stop trading for the day
- R300 daily profit target -> stop trading
- Bollinger squeeze detection, breakout entry
- LLM/journalist never executes trades

## Research workflow (screenshots)
1. Upload screenshots into research/screenshots/
2. AI reads/discusses patterns with the team
3. Patterns -> written rules -> coded strategy