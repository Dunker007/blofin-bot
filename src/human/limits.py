"""Session limits for autonomous trading safety."""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional

from ..core.config import AutonomyConfig
from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TradeRecord:
    """Record of a trade for session tracking."""
    symbol: str
    side: str  # long/short
    pnl: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def is_win(self) -> bool:
        return self.pnl > 0
    
    @property
    def is_loss(self) -> bool:
        return self.pnl < 0


class SessionLimits:
    """
    Tracks and enforces session trading limits.
    
    Limits (from autonomy.yaml):
    - max_trades_per_day
    - max_loss_percent_daily
    - max_loss_streak
    - mandatory_review_after
    
    Usage:
        limits = SessionLimits(config.autonomy, initial_balance=10000)
        
        # Before each trade
        if not limits.can_trade():
            print(f"Trading blocked: {limits.block_reason}")
        
        # After each trade
        limits.record_trade("BTC-USDT", "long", pnl=50.0)
    """
    
    def __init__(self, config: AutonomyConfig, initial_balance: float = 0):
        self.config = config
        self.initial_balance = initial_balance
        
        self._trades: List[TradeRecord] = []
        self._session_start = datetime.now()
        self._last_review = datetime.now()
        self._review_required = False
        self._manually_blocked = False
        self._block_reason = ""
    
    def record_trade(self, symbol: str, side: str, pnl: float) -> None:
        """
        Record a completed trade.
        
        Args:
            symbol: Trading pair
            side: Trade direction (long/short)
            pnl: Profit/loss in USD
        """
        trade = TradeRecord(symbol=symbol, side=side, pnl=pnl)
        self._trades.append(trade)
        
        logger.info(f"Trade recorded: {symbol} {side} P&L: ${pnl:+.2f}")
        
        # Check if review is required
        if self.trades_since_review >= self.config.max_trades_per_day:
            self._review_required = True
            logger.warning(f"Review required after {self.config.max_trades_per_day} trades")
    
    def mark_reviewed(self) -> None:
        """Mark that human has reviewed recent trades."""
        self._last_review = datetime.now()
        self._review_required = False
        logger.info("Session reviewed, limits reset")
    
    def block(self, reason: str) -> None:
        """Manually block trading."""
        self._manually_blocked = True
        self._block_reason = reason
        logger.warning(f"Trading manually blocked: {reason}")
    
    def unblock(self) -> None:
        """Remove manual block."""
        self._manually_blocked = False
        self._block_reason = ""
        logger.info("Trading unblocked")
    
    def reset_daily(self) -> None:
        """Reset daily limits (call at start of new day)."""
        today = date.today()
        self._trades = [t for t in self._trades if t.timestamp.date() == today]
        self._review_required = False
        logger.info("Daily limits reset")
    
    # ==================== Limit Checks ====================
    
    @property
    def trades_today(self) -> int:
        """Number of trades today."""
        today = date.today()
        return sum(1 for t in self._trades if t.timestamp.date() == today)
    
    @property
    def trades_since_review(self) -> int:
        """Trades since last review."""
        return sum(1 for t in self._trades if t.timestamp > self._last_review)
    
    @property
    def daily_pnl(self) -> float:
        """Total P&L for today."""
        today = date.today()
        return sum(t.pnl for t in self._trades if t.timestamp.date() == today)
    
    @property
    def daily_pnl_percent(self) -> float:
        """Daily P&L as percentage of initial balance."""
        if self.initial_balance == 0:
            return 0
        return (self.daily_pnl / self.initial_balance) * 100
    
    @property
    def current_loss_streak(self) -> int:
        """Current consecutive losses."""
        streak = 0
        for trade in reversed(self._trades):
            if trade.is_loss:
                streak += 1
            else:
                break
        return streak
    
    @property
    def win_rate_today(self) -> float:
        """Win rate for today."""
        today = date.today()
        today_trades = [t for t in self._trades if t.timestamp.date() == today]
        if not today_trades:
            return 0
        wins = sum(1 for t in today_trades if t.is_win)
        return (wins / len(today_trades)) * 100
    
    # ==================== Can Trade Check ====================
    
    def can_trade(self) -> bool:
        """
        Check if trading is allowed based on all limits.
        
        Returns:
            True if trading allowed, False if blocked
        """
        if self._manually_blocked:
            self._block_reason = f"Manually blocked: {self._block_reason}"
            return False
        
        # Check max trades per day
        if self.trades_today >= self.config.max_trades_per_day:
            self._block_reason = f"Max daily trades reached ({self.config.max_trades_per_day})"
            return False
        
        # Check daily loss limit
        if self.daily_pnl_percent <= -self.config.max_loss_percent_daily:
            self._block_reason = f"Daily loss limit reached ({self.config.max_loss_percent_daily}%)"
            return False
        
        # Check loss streak
        if self.current_loss_streak >= self.config.max_loss_streak:
            self._block_reason = f"Max loss streak reached ({self.config.max_loss_streak})"
            return False
        
        # Check review required
        if self._review_required:
            self._block_reason = "Human review required"
            return False
        
        self._block_reason = ""
        return True
    
    @property
    def block_reason(self) -> str:
        """Reason trading is blocked."""
        if not self._block_reason:
            self.can_trade()  # Updates block reason
        return self._block_reason
    
    # ==================== Reporting ====================
    
    def get_stats(self) -> Dict:
        """Get session statistics."""
        return {
            "trades_today": self.trades_today,
            "trades_since_review": self.trades_since_review,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_percent": self.daily_pnl_percent,
            "loss_streak": self.current_loss_streak,
            "win_rate_today": self.win_rate_today,
            "review_required": self._review_required,
            "can_trade": self.can_trade(),
            "block_reason": self.block_reason,
            "limits": {
                "max_trades_per_day": self.config.max_trades_per_day,
                "max_loss_percent": self.config.max_loss_percent_daily,
                "max_loss_streak": self.config.max_loss_streak,
            }
        }
    
    def get_trades_today(self) -> List[TradeRecord]:
        """Get all trades from today."""
        today = date.today()
        return [t for t in self._trades if t.timestamp.date() == today]
