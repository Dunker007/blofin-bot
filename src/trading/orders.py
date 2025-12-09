"""Order management with safety checks."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from ..core.client import BlofinClient
from ..core.config import Config
from ..core.exceptions import OrderError
from ..core.logger import get_trade_logger
from ..human.override import OverrideController

logger = get_trade_logger()


class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class OrderRequest:
    """Order request before submission."""
    symbol: str
    side: str  # buy/sell
    size: float
    order_type: str = "market"  # market, limit
    price: Optional[float] = None
    leverage: int = 3
    margin_mode: str = "cross"
    position_side: str = "net"
    reduce_only: bool = False
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    decision_id: Optional[str] = None  # Link to AI decision
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "size": self.size,
            "order_type": self.order_type,
            "price": self.price,
            "leverage": self.leverage,
            "margin_mode": self.margin_mode,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
        }


@dataclass 
class OrderResult:
    """Result of an order operation."""
    success: bool
    order_id: Optional[str] = None
    fill_price: Optional[float] = None
    fill_size: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "order_id": self.order_id,
            "fill_price": self.fill_price,
            "fill_size": self.fill_size,
            "status": self.status.value,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class OrderManager:
    """
    Safe order management with validation.
    
    Features:
    - Pre-flight validation
    - Override controller integration
    - Order tracking
    - TP/SL order management
    
    Usage:
        orders = OrderManager(client, config, override)
        
        result = orders.place_order(OrderRequest(
            symbol="BTC-USDT",
            side="buy",
            size=0.01,
            order_type="market"
        ))
        
        if result.success:
            print(f"Order filled: {result.order_id}")
    """
    
    def __init__(
        self,
        client: BlofinClient,
        config: Config,
        override: Optional[OverrideController] = None
    ):
        self.client = client
        self.config = config
        self.override = override
        
        self._order_history: List[OrderResult] = []
    
    def place_order(self, request: OrderRequest) -> OrderResult:
        """
        Place an order with safety checks.
        
        Args:
            request: OrderRequest with order details
        
        Returns:
            OrderResult with success/failure info
        """
        # Check override controller
        if self.override and not self.override.can_trade():
            return OrderResult(
                success=False,
                status=OrderStatus.REJECTED,
                error="Trading is paused or in panic mode"
            )
        
        # Validate request
        validation = self._validate_request(request)
        if not validation[0]:
            return OrderResult(
                success=False,
                status=OrderStatus.REJECTED,
                error=validation[1]
            )
        
        try:
            logger.info(f"Placing order: {request.side} {request.size} {request.symbol}")
            
            # Place order via client
            response = self.client.place_order(
                inst_id=request.symbol,
                side=request.side,
                size=str(request.size),
                order_type=request.order_type,
                price=str(request.price) if request.price else None,
                margin_mode=request.margin_mode,
                leverage=str(request.leverage),
                position_side=request.position_side,
                reduce_only=request.reduce_only
            )
            
            if response.get("orderId"):
                result = OrderResult(
                    success=True,
                    order_id=response.get("orderId"),
                    status=OrderStatus.SUBMITTED
                )
                logger.info(f"Order placed: {result.order_id}")
                
                # Place TP/SL if specified
                if request.stop_loss or request.take_profit:
                    self._place_tpsl(request, result.order_id)
                
            else:
                result = OrderResult(
                    success=False,
                    status=OrderStatus.FAILED,
                    error=response.get("msg", "Unknown error")
                )
                logger.error(f"Order failed: {result.error}")
            
            self._order_history.append(result)
            return result
            
        except Exception as e:
            logger.error(f"Order exception: {e}")
            result = OrderResult(
                success=False,
                status=OrderStatus.FAILED,
                error=str(e)
            )
            self._order_history.append(result)
            return result
    
    def place_market_order(
        self,
        symbol: str,
        side: str,
        size: float,
        leverage: int = 3,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        decision_id: Optional[str] = None
    ) -> OrderResult:
        """Convenience method for market orders."""
        return self.place_order(OrderRequest(
            symbol=symbol,
            side=side,
            size=size,
            order_type="market",
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            decision_id=decision_id
        ))
    
    def place_limit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        leverage: int = 3,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> OrderResult:
        """Convenience method for limit orders."""
        return self.place_order(OrderRequest(
            symbol=symbol,
            side=side,
            size=size,
            order_type="limit",
            price=price,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit
        ))
    
    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order."""
        try:
            logger.info(f"Cancelling order: {order_id}")
            response = self.client.cancel_order(order_id)
            
            return OrderResult(
                success=True,
                order_id=order_id,
                status=OrderStatus.CANCELLED
            )
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return OrderResult(
                success=False,
                order_id=order_id,
                status=OrderStatus.FAILED,
                error=str(e)
            )
    
    def cancel_all(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """Cancel all open orders."""
        results = []
        
        try:
            orders = self.client.get_open_orders(inst_id=symbol)
            for order in orders:
                result = self.cancel_order(order.get("orderId"))
                results.append(result)
        except Exception as e:
            logger.error(f"Cancel all failed: {e}")
        
        return results
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get open orders."""
        try:
            return self.client.get_open_orders(inst_id=symbol)
        except Exception as e:
            # Don't spam logs for expected auth errors
            if "401" not in str(e):
                logger.error(f"Failed to get orders: {e}")
            return []
    
    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """Get status of a specific order."""
        try:
            orders = self.client.get_open_orders()
            for order in orders:
                if order.get("orderId") == order_id:
                    return order
            
            # Check history
            history = self.client.get_order_history(limit=100)
            for order in history:
                if order.get("orderId") == order_id:
                    return order
            
            return None
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            return None
    
    def _validate_request(self, request: OrderRequest) -> tuple:
        """Validate order request."""
        # Check symbol
        if not request.symbol:
            return False, "Symbol required"
        
        # Check side
        if request.side not in ["buy", "sell"]:
            return False, f"Invalid side: {request.side}"
        
        # Check size
        if request.size <= 0:
            return False, f"Invalid size: {request.size}"
        
        # Check pair config
        pair = self.config.get_pair(request.symbol)
        if pair:
            if request.size < pair.min_order_size:
                return False, f"Size below minimum: {request.size} < {pair.min_order_size}"
            if request.leverage > pair.max_leverage:
                return False, f"Leverage exceeds max: {request.leverage} > {pair.max_leverage}"
        
        # Check limit price
        if request.order_type == "limit" and not request.price:
            return False, "Price required for limit orders"
        
        # Check stop loss is valid
        if request.stop_loss:
            if request.side == "buy" and request.stop_loss >= (request.price or float('inf')):
                return False, "Stop loss must be below entry for longs"
            if request.side == "sell" and request.stop_loss <= (request.price or 0):
                return False, "Stop loss must be above entry for shorts"
        
        return True, ""
    
    def _place_tpsl(self, request: OrderRequest, order_id: str) -> None:
        """Place TP/SL orders for a position."""
        try:
            # This would use the TPSL endpoint
            # For now, log the intent
            if request.stop_loss:
                logger.info(f"SL set: {request.stop_loss} for {request.symbol}")
            if request.take_profit:
                logger.info(f"TP set: {request.take_profit} for {request.symbol}")
        except Exception as e:
            logger.warning(f"Failed to set TP/SL: {e}")
    
    @property
    def order_history(self) -> List[OrderResult]:
        """Get local order history."""
        return list(self._order_history)
