"""Webhook receiver for external trading signals."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Callable
from enum import Enum
import hmac
import hashlib
import json

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel

from ..core.logger import get_logger

logger = get_logger(__name__)


class SignalAction(Enum):
    """Signal action types."""
    LONG = "long"
    SHORT = "short"
    CLOSE = "close"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


class WebhookSignal(BaseModel):
    """Incoming webhook signal."""
    secret: Optional[str] = None
    symbol: str
    action: str  # long, short, close
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    size_percent: Optional[float] = None
    leverage: Optional[int] = None
    source: Optional[str] = "webhook"
    message: Optional[str] = None


@dataclass
class ProcessedSignal:
    """Validated and processed signal."""
    id: str
    symbol: str
    action: SignalAction
    price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    size_percent: float
    leverage: int
    source: str
    message: str
    timestamp: datetime
    valid: bool
    errors: List[str]
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "action": self.action.value,
            "price": self.price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "size_percent": self.size_percent,
            "leverage": self.leverage,
            "source": self.source,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "valid": self.valid,
            "errors": self.errors,
        }


class SignalProcessor:
    """
    Process and validate incoming signals.
    
    Usage:
        processor = SignalProcessor(
            secret="your_webhook_secret",
            default_size=1.0,
            default_leverage=3
        )
        
        signal = processor.process(webhook_data)
        if signal.valid:
            # Execute the trade
            pass
    """
    
    def __init__(
        self,
        secret: str = "",
        default_size: float = 1.0,
        default_leverage: int = 3,
        allowed_symbols: Optional[List[str]] = None,
        max_size_percent: float = 10.0
    ):
        self.secret = secret
        self.default_size = default_size
        self.default_leverage = default_leverage
        self.allowed_symbols = allowed_symbols or []
        self.max_size_percent = max_size_percent
        
        self._signal_count = 0
        self._signal_history: List[ProcessedSignal] = []
    
    def process(self, data: WebhookSignal) -> ProcessedSignal:
        """Process and validate a webhook signal."""
        self._signal_count += 1
        signal_id = f"SIG-{self._signal_count:06d}"
        
        errors = []
        
        # Validate secret if configured
        if self.secret and data.secret != self.secret:
            errors.append("Invalid secret")
        
        # Validate action
        try:
            action = SignalAction(data.action.lower())
        except ValueError:
            errors.append(f"Invalid action: {data.action}")
            action = SignalAction.CLOSE
        
        # Validate symbol
        symbol = data.symbol.upper()
        if self.allowed_symbols and symbol not in self.allowed_symbols:
            errors.append(f"Symbol not allowed: {symbol}")
        
        # Validate size
        size_percent = data.size_percent or self.default_size
        if size_percent > self.max_size_percent:
            errors.append(f"Size {size_percent}% exceeds max {self.max_size_percent}%")
            size_percent = self.max_size_percent
        
        # Validate leverage
        leverage = data.leverage or self.default_leverage
        if leverage < 1 or leverage > 100:
            errors.append(f"Invalid leverage: {leverage}")
            leverage = self.default_leverage
        
        # Validate stop loss direction
        if data.stop_loss and data.price:
            if action == SignalAction.LONG and data.stop_loss >= data.price:
                errors.append("Stop loss must be below entry for longs")
            elif action == SignalAction.SHORT and data.stop_loss <= data.price:
                errors.append("Stop loss must be above entry for shorts")
        
        signal = ProcessedSignal(
            id=signal_id,
            symbol=symbol,
            action=action,
            price=data.price,
            stop_loss=data.stop_loss,
            take_profit=data.take_profit,
            size_percent=size_percent,
            leverage=leverage,
            source=data.source or "webhook",
            message=data.message or "",
            timestamp=datetime.now(),
            valid=len(errors) == 0,
            errors=errors
        )
        
        self._signal_history.append(signal)
        
        if signal.valid:
            logger.info(f"Signal processed: {signal_id} - {action.value} {symbol}")
        else:
            logger.warning(f"Invalid signal {signal_id}: {errors}")
        
        return signal
    
    def get_history(self, limit: int = 50) -> List[ProcessedSignal]:
        """Get recent signal history."""
        return self._signal_history[-limit:]


class WebhookReceiver:
    """
    FastAPI router for receiving webhook signals.
    
    Usage:
        receiver = WebhookReceiver(processor, execute_callback)
        app.include_router(receiver.router, prefix="/webhook")
    """
    
    def __init__(
        self,
        processor: SignalProcessor,
        execute_callback: Optional[Callable[[ProcessedSignal], Dict]] = None
    ):
        self.processor = processor
        self.execute_callback = execute_callback
        self.router = APIRouter()
        
        self._setup_routes()
    
    def _setup_routes(self) -> None:
        """Set up webhook routes."""
        
        @self.router.post("/signal")
        async def receive_signal(signal: WebhookSignal):
            """Receive and process a trading signal."""
            processed = self.processor.process(signal)
            
            result = {
                "received": True,
                "signal": processed.to_dict(),
            }
            
            # Execute if valid and callback provided
            if processed.valid and self.execute_callback:
                try:
                    execution = self.execute_callback(processed)
                    result["executed"] = execution.get("success", False)
                    result["execution"] = execution
                except Exception as e:
                    result["executed"] = False
                    result["error"] = str(e)
            
            return result
        
        @self.router.get("/history")
        async def get_signal_history(limit: int = 50):
            """Get recent signal history."""
            signals = self.processor.get_history(limit)
            return [s.to_dict() for s in signals]
        
        @self.router.post("/test")
        async def test_webhook(signal: WebhookSignal):
            """Test webhook without executing."""
            processed = self.processor.process(signal)
            return {
                "test": True,
                "valid": processed.valid,
                "signal": processed.to_dict(),
            }


# TradingView alert format helper
TRADINGVIEW_TEMPLATE = """
{
    "secret": "YOUR_SECRET",
    "symbol": "{{ticker}}",
    "action": "{{strategy.order.action}}",
    "price": {{close}},
    "message": "{{strategy.order.alert_message}}"
}
"""
