"""Kill switch and manual override controls."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional
import threading

from ..core.client import BlofinClient
from ..core.logger import get_logger

logger = get_logger(__name__)


class OverrideAction(Enum):
    """Types of override actions."""
    KILL_SWITCH = "kill_switch"
    PAUSE_AI = "pause_ai"
    RESUME_AI = "resume_ai"
    CLOSE_POSITION = "close_position"
    CLOSE_ALL = "close_all"
    CANCEL_ORDERS = "cancel_orders"


@dataclass
class OverrideEvent:
    """Record of an override action."""
    action: OverrideAction
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None


class OverrideController:
    """
    Emergency controls and manual overrides.
    
    Features:
    - Kill switch: Close all positions + cancel orders + pause AI
    - Pause/Resume AI trading
    - Manual position closing
    - Panic mode timeout
    
    Usage:
        controller = OverrideController(client)
        
        # Emergency - close everything
        controller.kill_switch()
        
        # Pause AI without closing
        controller.pause_ai()
        
        # Resume
        controller.resume_ai()
    """
    
    def __init__(
        self,
        client: Optional[BlofinClient] = None,
        on_kill_switch: Optional[Callable[[], None]] = None,
        on_pause: Optional[Callable[[], None]] = None,
        on_resume: Optional[Callable[[], None]] = None
    ):
        self.client = client
        self.on_kill_switch = on_kill_switch
        self.on_pause = on_pause
        self.on_resume = on_resume
        
        self._ai_paused = False
        self._panic_mode = False
        self._history: List[OverrideEvent] = []
        self._lock = threading.Lock()
    
    @property
    def is_ai_paused(self) -> bool:
        """Check if AI trading is paused."""
        return self._ai_paused
    
    @property
    def is_panic_mode(self) -> bool:
        """Check if in panic/kill switch mode."""
        return self._panic_mode
    
    def kill_switch(self) -> OverrideEvent:
        """
        EMERGENCY: Close all positions, cancel all orders, pause AI.
        
        Returns:
            OverrideEvent with results
        """
        logger.warning("🚨 KILL SWITCH ACTIVATED 🚨")
        
        event = OverrideEvent(
            action=OverrideAction.KILL_SWITCH,
            details={}
        )
        
        with self._lock:
            self._panic_mode = True
            self._ai_paused = True
        
        try:
            if self.client:
                # Cancel all orders first
                orders_result = self._cancel_all_orders()
                event.details["orders_cancelled"] = orders_result
                
                # Close all positions
                positions_result = self._close_all_positions()
                event.details["positions_closed"] = positions_result
            else:
                event.details["warning"] = "No client configured - cannot execute trades"
            
            # Trigger callback
            if self.on_kill_switch:
                self.on_kill_switch()
            
            event.success = True
            logger.warning("Kill switch complete - all positions closed, AI paused")
            
        except Exception as e:
            event.success = False
            event.error = str(e)
            logger.error(f"Kill switch error: {e}")
        
        self._history.append(event)
        return event
    
    def pause_ai(self, reason: str = "") -> OverrideEvent:
        """
        Pause AI trading without closing positions.
        
        Returns:
            OverrideEvent
        """
        logger.info(f"AI trading paused: {reason or 'Manual pause'}")
        
        with self._lock:
            self._ai_paused = True
        
        event = OverrideEvent(
            action=OverrideAction.PAUSE_AI,
            details={"reason": reason}
        )
        self._history.append(event)
        
        if self.on_pause:
            self.on_pause()
        
        return event
    
    def resume_ai(self) -> OverrideEvent:
        """
        Resume AI trading.
        
        Returns:
            OverrideEvent
        """
        logger.info("AI trading resumed")
        
        with self._lock:
            self._ai_paused = False
            self._panic_mode = False
        
        event = OverrideEvent(
            action=OverrideAction.RESUME_AI,
            details={}
        )
        self._history.append(event)
        
        if self.on_resume:
            self.on_resume()
        
        return event
    
    def close_position(self, symbol: str) -> OverrideEvent:
        """
        Manually close a specific position.
        
        Args:
            symbol: Trading pair to close
        
        Returns:
            OverrideEvent
        """
        logger.info(f"Manual close: {symbol}")
        
        event = OverrideEvent(
            action=OverrideAction.CLOSE_POSITION,
            details={"symbol": symbol}
        )
        
        try:
            if self.client:
                result = self.client.close_position(symbol)
                event.details["result"] = result
                event.success = True
            else:
                event.details["warning"] = "No client configured"
                event.success = False
        except Exception as e:
            event.success = False
            event.error = str(e)
            logger.error(f"Failed to close {symbol}: {e}")
        
        self._history.append(event)
        return event
    
    def cancel_all_orders(self) -> OverrideEvent:
        """
        Cancel all open orders.
        
        Returns:
            OverrideEvent
        """
        logger.info("Cancelling all orders")
        
        event = OverrideEvent(
            action=OverrideAction.CANCEL_ORDERS,
            details={}
        )
        
        try:
            result = self._cancel_all_orders()
            event.details["cancelled"] = result
            event.success = True
        except Exception as e:
            event.success = False
            event.error = str(e)
        
        self._history.append(event)
        return event
    
    def _close_all_positions(self) -> List[Dict]:
        """Close all open positions."""
        results = []
        
        if not self.client:
            return results
        
        try:
            positions = self.client.get_positions()
            for pos in positions:
                if float(pos.get("positions", 0)) != 0:
                    symbol = pos.get("instId")
                    try:
                        result = self.client.close_position(symbol)
                        results.append({"symbol": symbol, "success": True, "result": result})
                        logger.info(f"Closed position: {symbol}")
                    except Exception as e:
                        results.append({"symbol": symbol, "success": False, "error": str(e)})
                        logger.error(f"Failed to close {symbol}: {e}")
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
        
        return results
    
    def _cancel_all_orders(self) -> List[Dict]:
        """Cancel all open orders."""
        results = []
        
        if not self.client:
            return results
        
        try:
            orders = self.client.get_open_orders()
            for order in orders:
                order_id = order.get("orderId")
                try:
                    result = self.client.cancel_order(order_id)
                    results.append({"order_id": order_id, "success": True, "result": result})
                    logger.info(f"Cancelled order: {order_id}")
                except Exception as e:
                    results.append({"order_id": order_id, "success": False, "error": str(e)})
                    logger.error(f"Failed to cancel {order_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
        
        return results
    
    def can_trade(self) -> bool:
        """Check if trading is allowed."""
        return not self._ai_paused and not self._panic_mode
    
    def get_status(self) -> Dict:
        """Get current override status."""
        return {
            "ai_paused": self._ai_paused,
            "panic_mode": self._panic_mode,
            "can_trade": self.can_trade(),
            "total_overrides": len(self._history),
        }
    
    @property
    def history(self) -> List[OverrideEvent]:
        """Get override history."""
        return list(self._history)
