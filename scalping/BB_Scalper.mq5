//+------------------------------------------------------------------+
//| scalping/BB_Scalper.mq5                                          |
//| Scalping EA: Bollinger squeeze -> breakout.                      |
//| Uses core/RiskManager.mqh + core/TradeLogger.mqh                 |
//+------------------------------------------------------------------+
#property copyright "exness-trading-bots"
#property version   "1.00"
#property strict

#include <..\core\RiskManager.mqh>
#include <..\core\TradeLogger.mqh>

//--- Inputs ---------------------------------------------------------
input group "=== Bollinger Bands Config ==="
input int      InpBBPeriod       = 20;     // BB period
input double   InpBBDeviation    = 2.0;    // BB standard deviations
input ENUM_TIMEFRAMES InpBBTF     = PERIOD_M5;  // BB timeframe (M5, M15...)
input int      InpBWSmoothing    = 20;     // BandWidth average period (squeeze compare)
input double   InpSqueezeRatio   = 1.0;    // BW < avg ==> squeeze (1.0 = below average)

input group "=== Trade Config ==="
input double   InpStopMultiplier = 3.0;    // stop = risk_multiplier * last body (pips)
input double   InpRR             = 1.5;    // take profit = RR * stop distance
input int      InpMaxTradesPerDay= 20;     // hard safety cap on trades/day
input long     InpMagic          = 20261001;

CRiskManager   g_risk;
CTradeLogger   g_log;
string         g_symbols[] = {"XAUUSD","EURUSD"}; // ZAR pairs handled by base account
int            g_bbHandles[];
double         g_prevBW[];
bool           g_inTrade[];

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   int n = ArraySize(g_symbols);
   ArrayResize(g_bbHandles, n);
   ArrayResize(g_prevBW,    n);
   ArrayResize(g_inTrade,   n);

   for(int i = 0; i < n; i++)
   {
      g_bbHandles[i] = iBands(g_symbols[i], InpBBTF, InpBBPeriod, 0, InpBBDeviation, PRICE_CLOSE);
      if(g_bbHandles[i] == INVALID_HANDLE)
      {
         Print("Failed to create BB for ", g_symbols[i]);
         return(INIT_FAILED);
      }
   }
   g_log.LogMessage("Scalper initialised. Pairs: " + IntegerToString(n));
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   for(int i = 0; i < ArraySize(g_bbHandles); i++)
      if(g_bbHandles[i] != INVALID_HANDLE)
         IndicatorRelease(g_bbHandles[i]);
   g_log.LogMessage("Scalper stopped, reason code " + IntegerToString(reason));
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   g_risk.OnTickMaintenance();

   //--- honors daily risk/target caps: if capped, close nothing, open nothing new
   if(!g_risk.CanTrade())
   {
      static string lastMsg = "";
      if(lastMsg != "")
      {
         g_log.LogMessage("Trading halted by risk manager (target reached or daily loss cap).");
         lastMsg = "";
      }
      return;
   }

   for(int i = 0; i < ArraySize(g_symbols); i++)
   {
      //--- switch to the symbol context to read its data
      if(!SymbolSelect(g_symbols[i], true))  continue;
      if(g_symbols[i] != _Symbol)
      {
         Print("Bug: attempted to trade ", g_symbols[i], " outside its chart context.");
         continue;
      }

      //--- only one open position at a time per symbol for this EA (magic)
      if(CountOpen(g_symbols[i], InpMagic) > 0)
      {
         continue;
      }

      //--- run breakout detection on this symbol
      CheckSqueezeBreakout(i);
   }
}

//+------------------------------------------------------------------+
//| Detect squeeze then breakout for symbol i                        |
//+------------------------------------------------------------------+
void CheckSqueezeBreakout(int i)
{
   string   sym   = g_symbols[i];
   datetime start = iTime(sym, InpBBTF, 0);   // current bar
   //--- enough history
   if(start <= 0) return;

   int barsTotal = iBars(sym, InpBBTF);
   if(barsTotal < InpBBPeriod + InpBWSmoothing + 2) return;

   //--- read 3 bars of BB values (upper, middle, lower)
   double upper[], middle[], lower[];
   ArraySetAsSeries(upper, true);
   ArraySetAsSeries(middle,true);
   ArraySetAsSeries(lower, true);
   if(CopyBuffer(g_bbHandles[i], BASE_LINE, 0, 3, middle) <= 0) return;
   if(CopyBuffer(g_bbHandles[i], UPPER_BAND, 0, 3, upper)  <= 0) return;
   if(CopyBuffer(g_bbHandles[i], LOWER_BAND, 0, 3, lower)  <= 0) return;

   //--- BandWidth history for squeeze detection (raw, needs full series)
   int need = InpBWSmoothing + 2;
   double bw[], bwMA[];
   ArrayResize(bw, need);
   for(int b = 0; b < need; b++)
   {
      double u[], m[], l[];
      ArraySetAsSeries(u, true); ArraySetAsSeries(m, true); ArraySetAsSeries(l, true);
      if(CopyBuffer(g_bbHandles[i], BASE_LINE, b, 1, m) <= 0) return;
      if(CopyBuffer(g_bbHandles[i], UPPER_BAND, b, 1, u) <= 0) return;
      if(CopyBuffer(g_bbHandles[i], LOWER_BAND, b, 1, l) <= 0) return;
      if(m[0] == 0.0) return;
      bw[b] = (u[0] - l[0]) / m[0];
   }

   //--- average of BandWidth over the smoothing period (excluding current bar)
   double sum = 0.0;
   for(int b = 1; b <= InpBWSmoothing; b++) sum += bw[b];
   double bwAvg = sum / InpBWSmoothing;

   //--- squeeze: current BandWidth below average * ratio
   bool squeeze = (bw[0] < bwAvg * InpSqueezeRatio);

   //--- breakout: bar[1] closed beyond a band
   double close1 = iClose(sym, InpBBTF, 1);
   bool   brokeUp   = (close1 > upper[1]);
   bool   brokeDown = (close1 < lower[1]);

   if(!squeeze)      return;  // no tension -> no trade
   if(!brokeUp && !brokeDown) return;

   //--- build order
   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);

   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = sym;
   req.magic     = InpMagic;
   req.type      = brokeUp ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.volume    = 0.0;
   req.deviation = 10;

   //--- entry at market
   req.price = SymbolInfoDouble(sym, SYMBOL_ASK);   // buy
   if(!brokeUp)
      req.price = SymbolInfoDouble(sym, SYMBOL_BID); // sell

   //--- stop distance: N * average true range (rough) or fixed fallback
   double atrVal = iATR(sym, InpBBTF, 14);
   if(atrVal == 0.0) atrVal = 0.0010;
   double stopDist = atrVal * InpStopMultiplier;

   if(brokeUp)
   {
      req.sl = req.price - stopDist;
      req.tp = req.price + stopDist * InpRR;
   }
   else
   {
      req.sl = req.price + stopDist;
      req.tp = req.price - stopDist * InpRR;
   }

   //--- position size from risk manager (risk exactly 1% of live balance)
   double stopPips = stopDist / SymbolInfoDouble(sym, SYMBOL_POINT);
   req.volume = g_risk.LotForPips(stopPips);
   if(req.volume <= 0) return;

   //--- cap trades per day
   if(DealsToday(InpMagic) >= InpMaxTradesPerDay) return;

   if(OrderSend(req, res))
   {
      if(res.retcode == TRADE_RETCODE_DONE)
      {
         string setup = "BBsqueeze " + (brokeUp ? "LONG" : "SHORT") +
                        " bw=" + DoubleToString(bw[0] / bwAvg, 2) + "x";
         g_log.LogMessage(setup + " entry @ " + DoubleToString(req.price, _Digits));
      }
      else
      {
         Print("Order failed rc=", res.retcode, " ", res.comment);
      }
   }
}

//+------------------------------------------------------------------+
//| Count open positions for symbol + magic                          |
//+------------------------------------------------------------------+
int CountOpen(string sym, long magic)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;
      if(PositionGetInteger(POSITION_MAGIC) != magic) continue;
      count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| Count closed deals today for this magic                          |
//+------------------------------------------------------------------+
int DealsToday(long magic)
{
   int count = 0;
   datetime dayStart = (datetime)((ulong)(TimeCurrent() / 86400) * 86400);
   HistorySelect(dayStart, TimeCurrent());
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;
      if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != magic) continue;
      if(HistoryDealGetInteger(ticket, DEAL_ENTRY) == DEAL_ENTRY_IN) count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| ATR helper (returns current value as double)                     |
//+------------------------------------------------------------------+
double iATR(string sym, ENUM_TIMEFRAMES tf, int period)
{
   int h = iATR(sym, tf, period);
   if(h == INVALID_HANDLE) return 0.0;
   double v[1];
   if(CopyBuffer(h, 0, 0, 1, v) <= 0) return 0.0;
   return v[0];
}