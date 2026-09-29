# Implementation Roadmap

## Where we are (marked with [DONE])

### Phase 0 - Foundations
- [DONE] Python architecture (bot/, core/ modules, no MQL5 - decided after discussion)
- [DONE] core/.env secret handling (login, path; gitignored, never committed)
- [DONE] core/risk.py - live-balance sizing, 1%/trade, 3%/day cap, R300 target
- [DONE] core/logger.py - CSV trade logging
- [DONE] core/mt5_connector.py - MetaTrader5 API wrapper
- [DONE] core/strategy.py - Bollinger squeeze -> breakout
- [DONE] core/smc.py - SMC breaker/OB + symmetric rejection (ported from user code)
- [DONE] bot.py - main loop (dry-run + live modes), connected to Exness demo ZAR
- [DONE] backtest.py + mean_reversion.py + hybrid.py + smc_projection.py + pnl_projection.py

### Strategy testing so far (real MT5 history, honest results)
- Bollinger squeeze breakout: 45.8% WR, loses to spread
- Buy-low/sell-high (mean reversion): 55-84% WR, depends on TF; H4+8bar near break-even
- SMC + symmetric rejection: 30% WR, losing
- HYBRID (buy-low/sell-high + trend filter + time exit): H1 gold = 54.3% WR but still negative
- Consensus: H1/H4 needs MORE DATA (samples too small) - data is the bottleneck

### Next steps
- [NEXT] Open H1/H4 charts in MT5 to download full history (gold + EURUSD)
- [NEXT] Rerun hybrid + mean_reversion on 6-12 months of H1/H4 data
- [TODO] Swing bot on the winner (buy-low/sell-high + hybrid rules)
- [TODO] Scalping bot on the winner (if any scalping config proves profitable)
- [TODO] Ollama LLM journalist (local, advisory only) - NOT execution
- [TODO] 3-month demo test before any real money

### Rules agreed (no hardcodes, live balance always)
- Exness broker, ZAR (rand) demo account - account & target in Rands
- Instruments: GOLD (XAUUSDm) and majors - NOT ZAR pairs
- 1% risk per trade (of live balance)
- 3% daily loss cap -> stop trading for the day
- R300 daily profit target -> stop trading
- LLM/journalist never executes trades
- Screenshots -> patterns -> written rules -> coded strategy

## Research workflow (screenshots)
1. Upload screenshots into research/screenshots/
2. AI reads/discusses patterns with the team
3. Patterns -> written rules -> coded strategy