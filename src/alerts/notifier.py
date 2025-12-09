"""Alert notification system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional
import json
import threading

from .events import AlertEvent, EventType
from ..core.logger import get_logger

logger = get_logger(__name__)


class AlertLevel(Enum):
    """Alert notification levels."""
    SILENT = "silent"      # Log only
    NORMAL = "normal"      # Standard notifications
    IMPORTANT = "important"  # Important alerts only
    CRITICAL = "critical"  # Critical alerts only


class AlertHandler(ABC):
    """Base class for alert handlers."""
    
    @abstractmethod
    def send(self, event: AlertEvent) -> bool:
        """Send an alert notification."""
        pass


class ConsoleHandler(AlertHandler):
    """Print alerts to console."""
    
    def send(self, event: AlertEvent) -> bool:
        priority_icons = {0: "ℹ️", 1: "⚠️", 2: "🚨"}
        icon = priority_icons.get(event.priority, "•")
        
        print(f"\n{icon} [{event.timestamp.strftime('%H:%M:%S')}] {event.title}")
        print(f"   {event.message}")
        if event.symbol:
            print(f"   Symbol: {event.symbol}")
        
        return True


class LogHandler(AlertHandler):
    """Log alerts to file."""
    
    def send(self, event: AlertEvent) -> bool:
        log_levels = {0: logger.info, 1: logger.warning, 2: logger.critical}
        log_fn = log_levels.get(event.priority, logger.info)
        log_fn(f"[{event.event_type.value}] {event.title}: {event.message}")
        return True


class WebhookHandler(AlertHandler):
    """Send alerts to webhook (Discord, Slack, etc.)."""
    
    def __init__(self, webhook_url: str, format_type: str = "discord"):
        self.webhook_url = webhook_url
        self.format_type = format_type
    
    def send(self, event: AlertEvent) -> bool:
        try:
            import requests
            
            if self.format_type == "discord":
                payload = self._format_discord(event)
            elif self.format_type == "slack":
                payload = self._format_slack(event)
            else:
                payload = {"content": f"{event.title}: {event.message}"}
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            return response.status_code in [200, 204]
            
        except Exception as e:
            logger.error(f"Webhook failed: {e}")
            return False
    
    def _format_discord(self, event: AlertEvent) -> Dict:
        """Format for Discord webhook."""
        colors = {0: 0x3498db, 1: 0xf39c12, 2: 0xe74c3c}
        
        return {
            "embeds": [{
                "title": event.title,
                "description": event.message,
                "color": colors.get(event.priority, 0x3498db),
                "timestamp": event.timestamp.isoformat(),
                "fields": [
                    {"name": "Symbol", "value": event.symbol or "N/A", "inline": True},
                    {"name": "Type", "value": event.event_type.value, "inline": True},
                ]
            }]
        }
    
    def _format_slack(self, event: AlertEvent) -> Dict:
        """Format for Slack webhook."""
        return {
            "text": f"*{event.title}*\n{event.message}",
            "attachments": [{
                "color": "#3498db" if event.priority == 0 else "#f39c12" if event.priority == 1 else "#e74c3c",
                "fields": [
                    {"title": "Symbol", "value": event.symbol or "N/A", "short": True},
                    {"title": "Type", "value": event.event_type.value, "short": True},
                ]
            }]
        }


class Notifier:
    """
    Central notification system for trading alerts.
    
    Features:
    - Multiple notification channels
    - Alert level filtering
    - Event type filtering
    - Rate limiting
    - Event history
    
    Usage:
        notifier = Notifier()
        notifier.add_handler(ConsoleHandler())
        notifier.add_handler(WebhookHandler(url, "discord"))
        
        # Send alert
        event = AlertEvent.order_filled("BTC-USDT", "buy", 95000)
        notifier.notify(event)
        
        # Subscribe to specific events
        notifier.subscribe(EventType.ORDER_FILLED, my_callback)
    """
    
    def __init__(self, level: AlertLevel = AlertLevel.NORMAL):
        self.level = level
        self._handlers: List[AlertHandler] = []
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._history: List[AlertEvent] = []
        self._max_history = 1000
        self._lock = threading.Lock()
        
        # Default handlers
        self._handlers.append(LogHandler())
    
    def add_handler(self, handler: AlertHandler) -> None:
        """Add a notification handler."""
        self._handlers.append(handler)
    
    def remove_handler(self, handler: AlertHandler) -> None:
        """Remove a notification handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)
    
    def subscribe(self, event_type: EventType, callback: Callable[[AlertEvent], None]) -> None:
        """Subscribe to a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: EventType, callback: Callable) -> None:
        """Unsubscribe from an event type."""
        if event_type in self._subscribers:
            if callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)
    
    def notify(self, event: AlertEvent) -> None:
        """
        Send a notification.
        
        Args:
            event: AlertEvent to send
        """
        # Check level filter
        if not self._should_notify(event):
            return
        
        with self._lock:
            # Add to history
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history.pop(0)
        
        # Send to handlers
        for handler in self._handlers:
            try:
                handler.send(event)
            except Exception as e:
                logger.error(f"Handler failed: {e}")
        
        # Notify subscribers
        if event.event_type in self._subscribers:
            for callback in self._subscribers[event.event_type]:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Subscriber callback failed: {e}")
    
    def _should_notify(self, event: AlertEvent) -> bool:
        """Check if event should trigger notification based on level."""
        if self.level == AlertLevel.SILENT:
            return False
        
        if self.level == AlertLevel.CRITICAL:
            return event.priority >= 2
        
        if self.level == AlertLevel.IMPORTANT:
            return event.priority >= 1
        
        return True  # NORMAL shows all
    
    # ==================== Convenience Methods ====================
    
    def order_placed(self, symbol: str, side: str, size: float, order_id: str) -> None:
        """Notify order placed."""
        self.notify(AlertEvent.order_placed(symbol, side, size, order_id))
    
    def order_filled(self, symbol: str, side: str, price: float, pnl: Optional[float] = None) -> None:
        """Notify order filled."""
        self.notify(AlertEvent.order_filled(symbol, side, price, pnl))
    
    def stop_loss_hit(self, symbol: str, pnl: float) -> None:
        """Notify stop loss hit."""
        self.notify(AlertEvent.stop_loss_hit(symbol, pnl))
    
    def take_profit_hit(self, symbol: str, pnl: float) -> None:
        """Notify take profit hit."""
        self.notify(AlertEvent.take_profit_hit(symbol, pnl))
    
    def liquidation_warning(self, symbol: str, distance_pct: float) -> None:
        """Notify liquidation warning."""
        self.notify(AlertEvent.liquidation_warning(symbol, distance_pct))
    
    def ai_suggestion(self, symbol: str, action: str, confidence: float, reasoning: str) -> None:
        """Notify AI suggestion."""
        self.notify(AlertEvent.ai_suggestion(symbol, action, confidence, reasoning))
    
    def approval_required(self, decision_id: str, symbol: str, action: str) -> None:
        """Notify approval required."""
        self.notify(AlertEvent.approval_required(decision_id, symbol, action))
    
    def kill_switch(self) -> None:
        """Notify kill switch triggered."""
        self.notify(AlertEvent.kill_switch_triggered())
    
    def daily_loss_limit(self, loss_pct: float) -> None:
        """Notify daily loss limit hit."""
        self.notify(AlertEvent.daily_loss_limit(loss_pct))
    
    # ==================== History ====================
    
    def get_history(self, limit: int = 50, event_type: Optional[EventType] = None) -> List[AlertEvent]:
        """Get event history."""
        with self._lock:
            history = list(self._history)
        
        if event_type:
            history = [e for e in history if e.event_type == event_type]
        
        return history[-limit:]
    
    def clear_history(self) -> None:
        """Clear event history."""
        with self._lock:
            self._history.clear()
