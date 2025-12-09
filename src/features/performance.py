"""Performance tracking and statistics."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum

from ..journal.trades import TradeJournal


class StreakType(Enum):
    WIN = "win"
    LOSS = "loss"
    NONE = "none"


@dataclass
class PerformanceStats:
    """Trading performance statistics."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    total_pnl: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    profit_factor: float = 0.0  # gross profit / gross loss
    expectancy: float = 0.0  # avg win * win% - avg loss * loss%
    
    current_streak: int = 0
    streak_type: StreakType = StreakType.NONE
    max_win_streak: int = 0
    max_loss_streak: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 1),
            "total_pnl": round(self.total_pnl, 2),
            "average_win": round(self.average_win, 2),
            "average_loss": round(self.average_loss, 2),
            "largest_win": round(self.largest_win, 2),
            "largest_loss": round(self.largest_loss, 2),
            "profit_factor": round(self.profit_factor, 2),
            "expectancy": round(self.expectancy, 2),
            "current_streak": self.current_streak,
            "streak_type": self.streak_type.value,
            "max_win_streak": self.max_win_streak,
            "max_loss_streak": self.max_loss_streak,
        }


class PerformanceTracker:
    """
    Track and analyze trading performance.
    
    Usage:
        tracker = PerformanceTracker(trade_journal)
        
        # Get overall stats
        stats = tracker.get_stats()
        
        # Get stats for specific period
        weekly = tracker.get_stats(days=7)
        
        # Get daily P&L for charting
        daily = tracker.get_daily_pnl(days=30)
    """
    
    def __init__(self, trade_journal: TradeJournal):
        self.journal = trade_journal
    
    def get_stats(self, days: Optional[int] = None, symbol: Optional[str] = None) -> PerformanceStats:
        """
        Calculate performance statistics.
        
        Args:
            days: Limit to last N days (None = all time)
            symbol: Filter by symbol (None = all)
        
        Returns:
            PerformanceStats dataclass
        """
        # Get trades from journal
        trades = self.journal.get_recent(limit=1000)
        
        # Filter by date if specified
        if days:
            cutoff = datetime.now() - timedelta(days=days)
            trades = [t for t in trades if datetime.fromisoformat(t["close_time"]) > cutoff]
        
        # Filter by symbol if specified
        if symbol:
            trades = [t for t in trades if t["symbol"] == symbol]
        
        if not trades:
            return PerformanceStats()
        
        # Calculate stats
        stats = PerformanceStats()
        stats.total_trades = len(trades)
        
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] < 0]
        
        stats.winning_trades = len(wins)
        stats.losing_trades = len(losses)
        stats.win_rate = (stats.winning_trades / stats.total_trades) * 100 if stats.total_trades > 0 else 0
        
        # P&L stats
        stats.total_pnl = sum(t["pnl"] for t in trades)
        
        if wins:
            stats.average_win = sum(t["pnl"] for t in wins) / len(wins)
            stats.largest_win = max(t["pnl"] for t in wins)
        
        if losses:
            stats.average_loss = sum(t["pnl"] for t in losses) / len(losses)
            stats.largest_loss = min(t["pnl"] for t in losses)
        
        # Profit factor
        gross_profit = sum(t["pnl"] for t in wins) if wins else 0
        gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0
        stats.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Expectancy
        win_rate = stats.win_rate / 100
        loss_rate = 1 - win_rate
        stats.expectancy = (win_rate * abs(stats.average_win)) - (loss_rate * abs(stats.average_loss))
        
        # Streaks
        self._calculate_streaks(trades, stats)
        
        return stats
    
    def _calculate_streaks(self, trades: List[Dict], stats: PerformanceStats) -> None:
        """Calculate win/loss streaks."""
        if not trades:
            return
        
        # Sort by close time
        sorted_trades = sorted(trades, key=lambda t: t["close_time"])
        
        current_streak = 0
        current_type = StreakType.NONE
        max_win = 0
        max_loss = 0
        
        for trade in sorted_trades:
            if trade["pnl"] > 0:
                if current_type == StreakType.WIN:
                    current_streak += 1
                else:
                    current_streak = 1
                    current_type = StreakType.WIN
                max_win = max(max_win, current_streak)
            elif trade["pnl"] < 0:
                if current_type == StreakType.LOSS:
                    current_streak += 1
                else:
                    current_streak = 1
                    current_type = StreakType.LOSS
                max_loss = max(max_loss, current_streak)
            else:
                # Breakeven, doesn't affect streak
                pass
        
        stats.current_streak = current_streak
        stats.streak_type = current_type
        stats.max_win_streak = max_win
        stats.max_loss_streak = max_loss
    
    def get_daily_pnl(self, days: int = 30) -> List[Dict]:
        """
        Get daily P&L for charting.
        
        Returns list of {date, pnl, cumulative} dicts.
        """
        cutoff = datetime.now() - timedelta(days=days)
        trades = self.journal.get_recent(limit=1000)
        trades = [t for t in trades if datetime.fromisoformat(t["close_time"]) > cutoff]
        
        # Group by date
        daily: Dict[str, float] = {}
        for trade in trades:
            date_str = trade["close_time"][:10]  # YYYY-MM-DD
            daily[date_str] = daily.get(date_str, 0) + trade["pnl"]
        
        # Build result with cumulative
        result = []
        cumulative = 0
        for date_str in sorted(daily.keys()):
            pnl = daily[date_str]
            cumulative += pnl
            result.append({
                "date": date_str,
                "pnl": round(pnl, 2),
                "cumulative": round(cumulative, 2),
            })
        
        return result
    
    def get_by_symbol(self) -> Dict[str, PerformanceStats]:
        """Get performance stats grouped by symbol."""
        trades = self.journal.get_recent(limit=1000)
        
        symbols = set(t["symbol"] for t in trades)
        
        return {
            symbol: self.get_stats(symbol=symbol)
            for symbol in symbols
        }
    
    def get_summary(self) -> Dict:
        """Get a quick performance summary."""
        stats = self.get_stats()
        weekly = self.get_stats(days=7)
        
        return {
            "all_time": stats.to_dict(),
            "last_7_days": weekly.to_dict(),
            "daily_pnl": self.get_daily_pnl(14),  # 2 weeks for chart
        }
