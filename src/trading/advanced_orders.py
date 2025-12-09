"""Advanced order types."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
import asyncio

from ..core.client import BlofinClient
from ..core.logger import get_logger

logger = get_logger(__name__)


class TrailingStopStatus(Enum):
    """Trailing stop status."""
    INACTIVE = "inactive"
    ACTIVE = "active"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"


@dataclass
class TrailingStop:
    """
    Trailing stop order that follows price.
    
    For longs: Stop trails below the highest price
    For shorts: Stop trails above the lowest price
    """
    symbol: str
    side: str  # long or short
    distance: float  # Distance in price
    distance_percent: Optional[float] = None  # Distance as %
    activation_price: Optional[float] = None  # Price to activate trailing
    
    # State
    status: TrailingStopStatus = TrailingStopStatus.INACTIVE
    best_price: Optional[float] = None
    stop_price: Optional[float] = None
    trigger_price: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.now)
    triggered_at: Optional[datetime] = None
    
    def update(self, current_price: float) -> Optional[float]:
        """
        Update trailing stop with current price.
        
        Returns trigger price if stop was hit, None otherwise.
        """
        # Check activation
        if self.status == TrailingStopStatus.INACTIVE:
            if self.activation_price:
                if self.side == "long" and current_price >= self.activation_price:
                    self.status = TrailingStopStatus.ACTIVE
                    logger.info(f"Trailing stop activated for {self.symbol}")
                elif self.side == "short" and current_price <= self.activation_price:
                    self.status = TrailingStopStatus.ACTIVE
                    logger.info(f"Trailing stop activated for {self.symbol}")
            else:
                self.status = TrailingStopStatus.ACTIVE
        
        if self.status != TrailingStopStatus.ACTIVE:
            return None
        
        # Calculate distance
        distance = self.distance
        if self.distance_percent:
            distance = current_price * (self.distance_percent / 100)
        
        # Update for long position
        if self.side == "long":
            if self.best_price is None or current_price > self.best_price:
                self.best_price = current_price
                self.stop_price = self.best_price - distance
            
            if current_price <= self.stop_price:
                self.status = TrailingStopStatus.TRIGGERED
                self.trigger_price = current_price
                self.triggered_at = datetime.now()
                logger.info(f"Trailing stop triggered for {self.symbol} at {current_price}")
                return self.stop_price
        
        # Update for short position
        elif self.side == "short":
            if self.best_price is None or current_price < self.best_price:
                self.best_price = current_price
                self.stop_price = self.best_price + distance
            
            if current_price >= self.stop_price:
                self.status = TrailingStopStatus.TRIGGERED
                self.trigger_price = current_price
                self.triggered_at = datetime.now()
                logger.info(f"Trailing stop triggered for {self.symbol} at {current_price}")
                return self.stop_price
        
        return None
    
    def cancel(self) -> None:
        """Cancel the trailing stop."""
        self.status = TrailingStopStatus.CANCELLED
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "distance": self.distance,
            "distance_percent": self.distance_percent,
            "activation_price": self.activation_price,
            "status": self.status.value,
            "best_price": self.best_price,
            "stop_price": self.stop_price,
            "trigger_price": self.trigger_price,
            "created_at": self.created_at.isoformat(),
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
        }


@dataclass
class ScaledOrder:
    """
    Scaled entry/exit with multiple orders at different prices.
    
    Example: Enter with 3 limit orders at different levels
    """
    symbol: str
    side: str  # buy or sell
    total_size: float
    num_orders: int
    start_price: float
    end_price: float
    distribution: str = "linear"  # linear, exponential
    
    # State
    order_ids: List[str] = field(default_factory=list)
    filled_size: float = 0
    status: str = "pending"
    
    def get_order_prices(self) -> List[float]:
        """Calculate prices for each order."""
        prices = []
        step = (self.end_price - self.start_price) / (self.num_orders - 1) if self.num_orders > 1 else 0
        
        for i in range(self.num_orders):
            if self.distribution == "linear":
                price = self.start_price + (step * i)
            else:
                # Exponential - more size at better prices
                ratio = i / (self.num_orders - 1) if self.num_orders > 1 else 0
                price = self.start_price + (self.end_price - self.start_price) * (ratio ** 2)
            prices.append(round(price, 2))
        
        return prices
    
    def get_order_sizes(self) -> List[float]:
        """Calculate size for each order."""
        sizes = []
        base_size = self.total_size / self.num_orders
        
        for i in range(self.num_orders):
            if self.distribution == "linear":
                size = base_size
            else:
                # Exponential - more size at better prices
                weight = (i + 1) / sum(range(1, self.num_orders + 1))
                size = self.total_size * weight
            sizes.append(round(size, 6))
        
        return sizes
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "total_size": self.total_size,
            "num_orders": self.num_orders,
            "start_price": self.start_price,
            "end_price": self.end_price,
            "distribution": self.distribution,
            "order_ids": self.order_ids,
            "filled_size": self.filled_size,
            "status": self.status,
        }


class AdvancedOrderManager:
    """
    Manager for advanced order types.
    
    Usage:
        manager = AdvancedOrderManager(client)
        
        # Create trailing stop
        ts = manager.create_trailing_stop(
            symbol="BTC-USDT",
            side="long",
            distance=500,  # $500 trail
            activation_price=96000
        )
        
        # Update with price (call this from price feed)
        trigger = manager.update_trailing_stops(95500)
        if trigger:
            # Close position
            pass
    """
    
    def __init__(self, client: BlofinClient):
        self.client = client
        self._trailing_stops: Dict[str, TrailingStop] = {}
        self._scaled_orders: Dict[str, ScaledOrder] = {}
    
    # ==================== Trailing Stops ====================
    
    def create_trailing_stop(
        self,
        symbol: str,
        side: str,
        distance: float = 0,
        distance_percent: float = None,
        activation_price: float = None
    ) -> TrailingStop:
        """Create a new trailing stop."""
        ts = TrailingStop(
            symbol=symbol,
            side=side,
            distance=distance,
            distance_percent=distance_percent,
            activation_price=activation_price
        )
        
        key = f"{symbol}_{side}"
        self._trailing_stops[key] = ts
        logger.info(f"Created trailing stop for {symbol} {side}")
        
        return ts
    
    def update_trailing_stops(self, symbol: str, current_price: float) -> Optional[str]:
        """
        Update all trailing stops for a symbol with current price.
        
        Returns side of triggered stop if any, None otherwise.
        """
        for key, ts in list(self._trailing_stops.items()):
            if ts.symbol != symbol:
                continue
            
            if ts.status not in [TrailingStopStatus.ACTIVE, TrailingStopStatus.INACTIVE]:
                continue
            
            trigger = ts.update(current_price)
            if trigger:
                return ts.side
        
        return None
    
    def get_trailing_stop(self, symbol: str, side: str) -> Optional[TrailingStop]:
        """Get trailing stop for symbol/side."""
        key = f"{symbol}_{side}"
        return self._trailing_stops.get(key)
    
    def cancel_trailing_stop(self, symbol: str, side: str) -> bool:
        """Cancel a trailing stop."""
        key = f"{symbol}_{side}"
        if key in self._trailing_stops:
            self._trailing_stops[key].cancel()
            del self._trailing_stops[key]
            return True
        return False
    
    def get_all_trailing_stops(self) -> List[TrailingStop]:
        """Get all active trailing stops."""
        return list(self._trailing_stops.values())
    
    # ==================== Scaled Orders ====================
    
    def create_scaled_order(
        self,
        symbol: str,
        side: str,
        total_size: float,
        num_orders: int,
        start_price: float,
        end_price: float,
        distribution: str = "linear"
    ) -> ScaledOrder:
        """Create a scaled entry/exit order."""
        scaled = ScaledOrder(
            symbol=symbol,
            side=side,
            total_size=total_size,
            num_orders=num_orders,
            start_price=start_price,
            end_price=end_price,
            distribution=distribution
        )
        
        key = f"{symbol}_{side}_{datetime.now().timestamp()}"
        self._scaled_orders[key] = scaled
        
        logger.info(f"Created scaled order for {symbol}: {num_orders} orders from {start_price} to {end_price}")
        
        return scaled
    
    def execute_scaled_order(self, scaled: ScaledOrder) -> List[Dict]:
        """Execute a scaled order by placing all limit orders."""
        prices = scaled.get_order_prices()
        sizes = scaled.get_order_sizes()
        results = []
        
        for price, size in zip(prices, sizes):
            try:
                response = self.client.place_order(
                    inst_id=scaled.symbol,
                    side=scaled.side,
                    size=str(size),
                    order_type="limit",
                    price=str(price)
                )
                
                if response.get("orderId"):
                    scaled.order_ids.append(response["orderId"])
                    results.append({"success": True, "order_id": response["orderId"], "price": price, "size": size})
                else:
                    results.append({"success": False, "error": response.get("msg"), "price": price})
                    
            except Exception as e:
                results.append({"success": False, "error": str(e), "price": price})
        
        scaled.status = "placed" if any(r["success"] for r in results) else "failed"
        return results
    
    def cancel_scaled_order(self, scaled: ScaledOrder) -> int:
        """Cancel all orders in a scaled order. Returns count of cancelled."""
        cancelled = 0
        
        for order_id in scaled.order_ids:
            try:
                self.client.cancel_order(order_id)
                cancelled += 1
            except Exception:
                pass
        
        scaled.status = "cancelled"
        return cancelled
