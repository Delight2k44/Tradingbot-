//+------------------------------------------------------------------+
//| scalping/BB_Scalper.mq5                                          |
//| Scalping EA: Bollinger squeeze -> breakout.                      |
//| Trades the symbol of the chart it is attached to (M5/M15).       |
//| Uses core/RiskManager.mqh + core/TradeLogger.mqh                 |
//+------------------------------------------------------------------+
#property copyright "exness-trading-bots"
#property version   "1.00"
#property strict

#include <..\core\RiskManager.mqh>
#include <..\core\TradeLogger.mqh>

//--- Inputs ---------------------------------------------------------
input group "=== Bollinger Bands Config ==="
input int                 InpBBPeriod    = 20;    // BB period
input double              InpBBDeviation = 2.0;   // BB standard deviations
input ENUM_TIMEFRAMES     InpBBTF        = PERIOD_M5; // BB timeframe
input int                 InpBWSmoothing = 20;    // BandWidth average period (squeeze compare)
input double              InpSqueezeRatio= 1.0;   // BW < average*ratio ==> squeeze

input group "=== Trade Config ==="
input int    InpATRPeriod       = 14;    // ATR period for stop distance
input double InpStopATRMult     = 3.0;   // stop = ATR * multiplier
input double InpRR              = 1.5;   // take profit = RR * stop distance
input int    InpMaxTradesPerDay = 20;    // hard safety cap on trades/day
input long   InpMagic           = 20261001;

CRiskManager   g_risk;
CTradeLogger   g_log;

int            g_bbHandle   = INVALID_HANDLE;
int            g_atrHandle  = INVALID_HANDLE;
datetime       g_lastTradeDayTime = 0;
bool           g_squeezeHeld  = false; // confirmed squeeze before break

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   g_bbHandle  = iBands(_Symbol, InpBBTF, InpBBPeriod, 0, InpBBDeviation, PRICE_CLOSE);
   g_atrHandle = iATR(_Symbol, InpBBTF, InpATRPeriod);
   if(g_bbHandle  == INVALID_HANDLE ||
      g_atrHandle == INVALID_HANDLE)
   {
      Print("Failed to create indicators for ", _Symbol);
      return(INIT_FAILED);
   }

   g_log.LogMessage("Scalper initialised on " + _Symbol + " TF " + EnumToString(InpBBTF));
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_bbHandle  != INVALID_HANDLE) IndicatorRelease(g_bbHandle);
   if(g_atrHandle != INVALID_HANDLE) IndicatorRelease(g_atrHandle);
   g_log.LogMessage("Scalper stopped, reason " + IntegerToString(reason));
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   g_risk.OnTickMaintenance();

   //--- Daily target reached OR daily loss cap hit -> block trading
   if(!g_risk.CanTrade())
   {
      if(g_lastTradeDayTime != DayStartTime())
      {
         g_log.LogMessage("Risk manager halted trading (target hit or daily loss cap).");
         g_lastTradeDayTime = DayStartTime();
      }
      return;
   }

   //--- Already holding a position for this EA? do nothing new.
   if(CountOpen(_Symbol, InpMagic) > 0)
      return;

   //--- Trades/day cap
   if(DealsToday(InpMagic) >= InpMaxTradesPerDay)
      return;

   CheckSqueezeBreakout();
}

//+------------------------------------------------------------------+
//| Squeeze + breakout logic                                         |
//+------------------------------------------------------------------+
void CheckSqueezeBreakout()
{
   //--- Read current and prior band values
   double upper[], middle[], lower[];
   ArraySetAsSeries(upper,  true);
   ArraySetAsSeries(middle, true);
   ArraySetAsSeries(lower,  true);

   if(CopyBuffer(g_bbHandle, BASE_LINE, 0, 2, middle) <= 0) return;
   if(CopyBuffer(g_bbHandle, UPPER_BAND, 0, 2, upper)  <= 0) return;
   if(CopyBuffer(g_bbHandle, LOWER_BAND, 0, 2, lower)  <= 0) return;

   int bars = iBars(_Symbol, InpBBTF);
   if(bars < InpBBPeriod + InpBWSmoothing + 2) return;

   //--- Build BandWidth series to compute its average
   static double bwBuf[];
   int need = InpBWSmoothing + 2;
   if(ArraySize(bwBuf) < need) ArrayResize(bwBuf, need);

   for(int b = 0; b < need; b++)
   {
      double u[1], m[1], l[1];
      if(CopyBuffer(g_bbHandle, BASE_LINE, b, 1, m) <= 0) return;
      if(CopyBuffer(g_bbHandle, UPPER_BAND, b, 1, u) <= 0) return;
      if(CopyBuffer(g_bbHandle, LOWER_BAND, b, 1, l) <= 0) return;
      if(m[0] == 0.0) return;
      bwBuf[b] = (u[0] - l[0]) / m[0];
   }

   double sum = 0.0;
   for(int b = 1; b <= InpBWSmoothing; b++) sum += bwBuf[b];
   double bwAvg = sum / InpBWSmoothing;

   bool squeeze = (bwBuf[0] < bwAvg * InpSqueezeRatio);

   //--- Breakout on previous (closed) candle beyond a band
   double close1 = iClose(_Symbol, InpBBTF, 1);
   bool   brokeUp   = (close1 > upper[1]);
   bool   brokeDown = (close1 < lower[1]);

   if(!squeeze)            { g_squeezeHeld = false; return; }
   if(!brokeUp && !brokeDown) return;

   //--- Build the order
   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);

   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = _Symbol;
   req.magic     = InpMagic;
   req.deviation = 10;

   //--- Direction
   bool goingLong = brokeUp;
   req.type = goingLong ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price = SymbolInfoDouble(_Symbol, goingLong ? SYMBOL_ASK : SYMBOL_BID);

   //--- Stop distance from ATR
   double atrVal[1];
   if(CopyBuffer(g_atrHandle, 0, 0, 1, atrVal) <= 0) return;
   double stopDist = atrVal[0] * InpStopATRMult;

   if(goingLong)
   {
      req.sl = req.price - stopDist;
      req.tp = req.price + stopDist * InpRR;
   }
   else
   {
      req.sl = req.price + stopDist;
      req.tp = req.price - stopDist * InpRR;
   }

   //--- Size = 1% of LIVE balance given this stop distance
   double stopPips = stopDist / SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   req.volume = g_risk.LotForPips(stopPips);
   if(req.volume <= 0.0) return;

   if(!OrderSend(req, res))
      return;

   if(res.retcode != TRADE_RETCODE_DONE)
   {
      Print("Order failed rc=", res.retcode, " ", res.comment);
      return;
   }

   string setup = "BBsqueeze " + (goingLong ? "LONG" : "SHORT") +
                  " bwRatio=" + DoubleToString(bwBuf[0] / bwAvg, 2);
   g_log.LogMessage(setup);
}

//+------------------------------------------------------------------+
//| Count open positions on this symbol/magic                        |
//+------------------------------------------------------------------+
int CountOpen(string sym, long magic)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetTicket(i) == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;
      if(PositionGetInteger(POSITION_MAGIC)  != magic) continue;
      count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| Count entry deals today for this magic                           |
//+------------------------------------------------------------------+
int DealsToday(long magic)
{
   int count = 0;
   datetime today = DayStartTime();
   HistorySelect(today, TimeCurrent());
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
//| Start of current trading day (server time)                       |
//+------------------------------------------------------------------+
datetime DayStartTime()
{
   MqlDateTime s;
   TimeToStruct(TimeCurrent(), s);
   s.hour = 0; s.min = 0; s.sec = 0;
   return StructToTime(s);
}