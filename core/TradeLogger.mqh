//+------------------------------------------------------------------+
//| core/TradeLogger.mqh                                             |
//| Writes every trade to a CSV for honest post-test review.         |
//+------------------------------------------------------------------+
#property strict

class CTradeLogger
{
private:
   string   m_filename;
   string   m_folder;
   string   m_path;

   string LogPath()
   {
      if(m_path == "")
         m_path = m_folder + "\\" + m_filename;
      return m_path;
   }

public:
   CTradeLogger()
   {
      m_folder   = "exness-bots\\logs";
      m_filename = "trades_" + _Symbol + ".csv";
      m_path     = "";
      InitFile();
   }

   bool InitFile()
   {
      if(FileIsExist(LogPath())) return true;
      int h = FileOpen(LogPath(), FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
      if(h == INVALID_HANDLE) return false;
      FileWrite(h, "Ticket","Time","Type","Volume","Price","StopLoss","TakeProfit","SpreadPoints","Profit","Setup","Comment");
      FileClose(h);
      return true;
   }

   //--- Record a closed deal with strategy context
   void LogDeal(ulong dealTicket, string setup)
   {
      int h = FileOpen(LogPath(), FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
      if(h == INVALID_HANDLE) return;

      //--- jump to end to append (FileWrite on shared handle works with SEEK_END)
      FileSeek(h, 0, SEEK_END);

      string t     = TimeToString((datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME));
      long   posId = HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
      long   type  = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
      string sym   = HistoryDealGetString (dealTicket, DEAL_SYMBOL);
      double vol   = HistoryDealGetDouble (dealTicket, DEAL_VOLUME);
      double price = HistoryDealGetDouble (dealTicket, DEAL_PRICE);
      double sl    = HistoryDealGetDouble (dealTicket, DEAL_SL);
      double tp    = HistoryDealGetDouble (dealTicket, DEAL_TP);
      double prof  = HistoryDealGetDouble (dealTicket, DEAL_PROFIT);
      long   magic = HistoryDealGetInteger(dealTicket, DEAL_MAGIC);
      string comm  = HistoryDealGetString (dealTicket, DEAL_COMMENT);

      FileWrite(h, (long)posId, t, type, sym, vol, price, sl, tp, prof, setup, comm);
      FileClose(h);
   }

   void LogMessage(string msg)
   {
      int h = FileOpen(LogPath(), FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
      if(h == INVALID_HANDLE) return;
      FileSeek(h, 0, SEEK_END);
      FileWrite(h, 0, TimeToString(TimeCurrent()), "NOTE", "", 0.0, 0.0, 0.0, 0.0, 0.0, msg, InpTradeComment);
      FileClose(h);
   }
};