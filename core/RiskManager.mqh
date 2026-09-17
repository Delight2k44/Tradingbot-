//+------------------------------------------------------------------+
//| core/RiskManager.mqh                                             |
//| Shared risk controls for scalping and swing EAs.                 |
//| Reads LIVE account balance - no hardcoded values.                |
//+------------------------------------------------------------------+
#property strict

//--- Config (extern so you can tweak in MT5 without editing code)
input double InpRiskPerTradePercent = 1.0;  // max risk per trade (% of balance)
input double InpDailyLossPercent   = 3.0;  // stop trading for the day after this loss (%)
input double InpDailyTargetPercent = 0.0;  // 0 = not used; set >0 for a % target instead of fixed R
input double InpFixedDailyTarget   = 300.0;// fixed daily profit target in account currency (R)
input string InpTradeComment       = "exness-bot";

//--- Risk manager state
class CRiskManager
{
private:
   double   m_dayStartBalance;   // balance when today's trading session began
   double   m_dayStartTime;      // start of current trading day (server time)
   double   m_dayPnL;            // today's realized + floating PnL

public:
   CRiskManager() { m_dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE); m_dayStartTime = 0.0; m_dayPnL = 0.0; }

   //--- Called on every tick to refresh day state
   void OnTickMaintenance()
   {
      datetime serverTime = TimeCurrent();
      datetime dayStart   = StringsToTime(TimeToString(serverTime, TIME_DATE));

      if(dayStart != (datetime)m_dayStartTime)
      {
         //--- new trading day: reset balance baseline and PnL
         m_dayStartTime   = (double)dayStart;
         m_dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
         m_dayPnL          = 0.0;
      }
      //--- update realized + floating PnL of all open positions and history today
      m_dayPnL = TodayNetProfit();
   }

   //--- Max loss allowed per trade (currency units)
   double MaxLossPerTrade()
   {
      double bal = AccountInfoDouble(ACCOUNT_BALANCE);
      return bal * InpRiskPerTradePercent / 100.0;
   }

   //--- True if today's loss limit has been hit -> stop all trading
   bool TooManyLossesToday()
   {
      double maxLost = m_dayStartBalance * InpDailyLossPercent / 100.0;
      return (m_dayPnL <= -maxLost);
   }

   //--- True if today's profit target has been reached -> stop trading
   bool TargetReached()
   {
      double target = 0.0;
      if(InpDailyTargetPercent > 0.0)
         target = m_dayStartBalance * InpDailyTargetPercent / 100.0;
      else
         target = InpFixedDailyTarget;

      return (m_dayPnL >= target);
   }

   //--- Position size (lots) so that a stop loss of 'stopPips' pips risks exactly MaxLossPerTrade
   double LotForPips(double stopPips)
   {
      if(stopPips <= 0.0) return 0.0;

      double riskMoney   = MaxLossPerTrade();
      double tickValue   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
      double tickSize    = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      double point       = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

      if(tickValue <= 0.0 || tickSize <= 0.0 || point <= 0.0) return 0.0;

      double lossPerLotPerStopInPips = (tickValue / tickSize) * stopPips * point;
      double lots = riskMoney / lossPerLotPerStopInPips;

      //--- normalize to broker lot step
      double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
      double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
      double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
      if(lotStep > 0.0) lots = MathFloor(lots / lotStep) * lotStep;
      lots = MathMax(minLot, MathMin(maxLot, lots));
      return lots;
   }

   //--- Enforce account-level sanity before any trade
   bool CanTrade()
   {
      if(TargetReached())    return false;  // take the profit, stop
      if(TooManyLossesToday()) return false; // stop bleeding
      if(AccountInfoDouble(ACCOUNT_EQUITY) <= 0.0) return false;
      return true;
   }

   //--- Net PnL since start of today (realized + open)
   double TodayNetProfit()
   {
      double pnl = 0.0;
      datetime dayStart = (datetime)m_dayStartTime;

      //--- open positions
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket > 0 && PositionGetSymbol(i) == _Symbol)
            pnl += PositionGetDouble(POSITION_PROFIT);
      }

      //--- today's closed deals
      HistorySelect(dayStart, TimeCurrent());
      for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket > 0 && HistoryDealGetString(ticket, DEAL_SYMBOL) == _Symbol)
            pnl += HistoryDealGetDouble(ticket, DEAL_PROFIT);
      }
      return pnl;
   }
};