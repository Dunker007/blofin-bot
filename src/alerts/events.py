"""Alert events and types."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class EventType(Enum):
    """Types of trading events."""
    # Trading events
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_FAILED = "order_failed"
    
    # Position events
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    LIQUIDATION_WARNING = "liquidation_warning"
    
    # AI events
    AI_DECISION = "ai_decision"
    AI_SUGGESTION = "ai_suggestion"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_EXPIRED = "approval_expired"
    
    # Risk events
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_POSITIONS = "max_positions"
    EXPOSURE_WARNING = "exposure_warning"
    
    # System events
    KILL_SWITCH = "kill_switch"
    AI_PAUSED = "ai_paused"
    AI_RESUMED = "ai_resumed"
    SESSION_REVIEW = "session_review"
    
    # Market events
    PRICE_ALERT = "price_alert"
    FUNDING_ALERT = "funding_alert"


@dataclass
class AlertEvent:
    """A trading alert event."""
    event_type: EventType
    title: str
    message: str
    data: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    symbol: Optional[str] = None
    priority: int = 0  # 0=info, 1=warning, 2=critical
    
    def to_dict(self) -> Dict:
        return {
            "event_type": self.event_type.value,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "priority": self.priority,
        }
    
    @classmethod
    def order_placed(cls, symbol: str, side: str, size: float, order_id: str) -> "AlertEvent":
        """Create order placed event."""
        return cls(
            event_type=EventType.ORDER_PLACED,
            title="Order Placed",
            message=f"{side.upper()} {size} {symbol}",
            symbol=symbol,
            data={"side": side, "size": size, "order_id": order_id},
            priority=0
        )
    
    @classmethod
    def order_filled(cls, symbol: str, side: str, price: float, pnl: Optional[float] = None) -> "AlertEvent":
        """Create order filled event."""
        msg = f"{side.upper()} filled @ ${price:,.2f}"
        if pnl is not None:
            msg += f" (P&L: ${pnl:+,.2f})"
        return cls(
            event_type=EventType.ORDER_FILLED,
            title="Order Filled",
            message=msg,
            symbol=symbol,
            data={"side": side, "price": price, "pnl": pnl},
            priority=0
        )
    
    @classmethod
    def stop_loss_hit(cls, symbol: str, pnl: float) -> "AlertEvent":
        """Create stop loss hit event."""
        return cls(
            event_type=EventType.STOP_LOSS_HIT,
            title="⚠️ Stop Loss Hit",
            message=f"{symbol} closed at stop loss (${pnl:+,.2f})",
            symbol=symbol,
            data={"pnl": pnl},
            priority=1
        )
    
    @classmethod
    def take_profit_hit(cls, symbol: str, pnl: float) -> "AlertEvent":
        """Create take profit hit event."""
        return cls(
            event_type=EventType.TAKE_PROFIT_HIT,
            title="✅ Take Profit Hit",
            message=f"{symbol} closed at TP (${pnl:+,.2f})",
            symbol=symbol,
            data={"pnl": pnl},
            priority=0
        )
    
    @classmethod
    def liquidation_warning(cls, symbol: str, distance_pct: float) -> "AlertEvent":
        """Create liquidation warning event."""
        return cls(
            event_type=EventType.LIQUIDATION_WARNING,
            title="🚨 Liquidation Warning",
            message=f"{symbol} - {distance_pct:.1f}% from liquidation!",
            symbol=symbol,
            data={"distance_pct": distance_pct},
            priority=2
        )
    
    @classmethod
    def ai_suggestion(cls, symbol: str, action: str, confidence: float, reasoning: str) -> "AlertEvent":
        """Create AI suggestion event."""
        return cls(
            event_type=EventType.AI_SUGGESTION,
            title="🤖 AI Suggestion",
            message=f"{action.upper()} {symbol} ({confidence:.0f}% confidence)",
            symbol=symbol,
            data={"action": action, "confidence": confidence, "reasoning": reasoning},
            priority=0
        )
    
    @classmethod
    def approval_required(cls, decision_id: str, symbol: str, action: str) -> "AlertEvent":
        """Create approval required event."""
        return cls(
            event_type=EventType.APPROVAL_REQUIRED,
            title="📋 Approval Required",
            message=f"{action.upper()} {symbol} awaiting approval",
            symbol=symbol,
            data={"decision_id": decision_id, "action": action},
            priority=1
        )
    
    @classmethod
    def kill_switch_triggered(cls) -> "AlertEvent":
        """Create kill switch event."""
        return cls(
            event_type=EventType.KILL_SWITCH,
            title="🚨 KILL SWITCH ACTIVATED",
            message="All positions closed, trading stopped",
            priority=2
        )
    
    @classmethod
    def daily_loss_limit(cls, loss_pct: float) -> "AlertEvent":
        """Create daily loss limit event."""
        return cls(
            event_type=EventType.DAILY_LOSS_LIMIT,
            title="⚠️ Daily Loss Limit",
            message=f"Trading paused - {loss_pct:.1f}% daily loss",
            priority=2
        )
