"""Account data service for balance, positions, and orders."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from ..core.client import BlofinClient
from ..core.logger import get_logger

logger = get_logger(__name__)


class PositionSide(Enum):
    """Position direction."""
    LONG = "long"
    SHORT = "short"
    NET = "net"


class MarginMode(Enum):
    """Margin mode."""
    CROSS = "cross"
    ISOLATED = "isolated"


@dataclass
class Balance:
    """Account balance information."""
    total_equity: float
    available_balance: float
    used_margin: float
    unrealized_pnl: float
    currency: str = "USDT"
    
    @classmethod
    def from_api(cls, data: dict) -> "Balance":
        """Create Balance from API response."""
        # Handle different API response formats
        # Root level may have totalEquity, details have equity
        equity = float(data.get("totalEquity", 0) or data.get("equity", 0))
        available = float(data.get("availableBalance", 0) or data.get("balance", 0) or data.get("available", 0))
        margin = float(data.get("marginUsed", 0) or data.get("isolatedMargin", 0))
        upnl = float(data.get("unrealizedPnl", 0) or data.get("isolatedUnrealizedPnl", 0))
        
        return cls(
            total_equity=equity,
            available_balance=available,
            used_margin=margin,
            unrealized_pnl=upnl,
            currency=data.get("currency", "USDT")
        )
    
    @property
    def margin_ratio(self) -> float:
        """Used margin as percentage of equity."""
        if self.total_equity == 0:
            return 0
        return (self.used_margin / self.total_equity) * 100
    
    @property
    def exposure(self) -> float:
        """Total exposure (margin + unrealized P&L)."""
        return self.used_margin + self.unrealized_pnl


@dataclass
class Position:
    """Open position information."""
    symbol: str
    side: PositionSide
    size: float
    avg_price: float
    mark_price: float
    liquidation_price: float
    leverage: int
    margin_mode: MarginMode
    unrealized_pnl: float
    realized_pnl: float
    margin: float
    timestamp: datetime
    
    @classmethod
    def from_api(cls, data: dict) -> "Position":
        """Create Position from API response."""
        side_str = data.get("positionSide", "net").lower()
        # Determine actual side from position amount if net mode
        if side_str == "net":
            pos_amt = float(data.get("positions", 0))
            if pos_amt > 0:
                side = PositionSide.LONG
            elif pos_amt < 0:
                side = PositionSide.SHORT
            else:
                side = PositionSide.NET
        else:
            side = PositionSide(side_str)
        
        return cls(
            symbol=data.get("instId", ""),
            side=side,
            size=abs(float(data.get("positions", 0))),
            avg_price=float(data.get("averagePrice", 0)),
            mark_price=float(data.get("markPrice", 0)),
            liquidation_price=float(data.get("liquidationPrice", 0)),
            leverage=int(float(data.get("leverage", 1))),
            margin_mode=MarginMode(data.get("marginMode", "cross").lower()),
            unrealized_pnl=float(data.get("unrealizedPnl", 0)),
            realized_pnl=float(data.get("realizedPnl", 0)),
            margin=float(data.get("margin", 0)),
            timestamp=datetime.now()
        )
    
    @property
    def notional_value(self) -> float:
        """Position notional value."""
        return self.size * self.mark_price
    
    @property
    def pnl_percent(self) -> float:
        """Unrealized P&L as percentage."""
        if self.margin == 0:
            return 0
        return (self.unrealized_pnl / self.margin) * 100
    
    @property
    def distance_to_liquidation(self) -> float:
        """Percentage distance to liquidation price."""
        if self.liquidation_price == 0:
            return 100
        if self.side == PositionSide.LONG:
            return ((self.mark_price - self.liquidation_price) / self.mark_price) * 100
        else:
            return ((self.liquidation_price - self.mark_price) / self.mark_price) * 100
    
    @property
    def is_profitable(self) -> bool:
        """True if position is in profit."""
        return self.unrealized_pnl > 0


@dataclass
class Order:
    """Order information."""
    order_id: str
    symbol: str
    side: str
    order_type: str
    size: float
    price: Optional[float]
    filled_size: float
    status: str
    leverage: int
    margin_mode: str
    created_at: datetime
    
    @classmethod
    def from_api(cls, data: dict) -> "Order":
        """Create Order from API response."""
        created = int(data.get("createTime", 0))
        return cls(
            order_id=data.get("orderId", ""),
            symbol=data.get("instId", ""),
            side=data.get("side", ""),
            order_type=data.get("orderType", ""),
            size=float(data.get("size", 0)),
            price=float(data.get("price", 0)) if data.get("price") else None,
            filled_size=float(data.get("filledSize", 0)),
            status=data.get("state", ""),
            leverage=int(float(data.get("leverage", 1))),
            margin_mode=data.get("marginMode", "cross"),
            created_at=datetime.fromtimestamp(created / 1000) if created else datetime.now()
        )
    
    @property
    def is_filled(self) -> bool:
        """True if order is fully filled."""
        return self.status == "filled"
    
    @property
    def fill_percent(self) -> float:
        """Percentage of order filled."""
        if self.size == 0:
            return 0
        return (self.filled_size / self.size) * 100


class AccountData:
    """
    Account data service providing balance, positions, and orders.
    
    Usage:
        config = Config.load()
        client = BlofinClient(config)
        account = AccountData(client)
        
        balance = account.get_balance()
        positions = account.get_positions()
    """
    
    def __init__(self, client: BlofinClient):
        self.client = client
        self._balance_cache: Optional[Balance] = None
        self._positions_cache: List[Position] = []
    
    def get_balance(self) -> Balance:
        """Get account balance."""
        data = self.client.get_balance()
        
        # Handle nested structure
        if isinstance(data, dict) and "details" in data:
            # Find USDT balance
            for detail in data.get("details", []):
                if detail.get("currency") == "USDT":
                    balance = Balance.from_api(detail)
                    self._balance_cache = balance
                    return balance
        
        balance = Balance.from_api(data)
        self._balance_cache = balance
        return balance
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """
        Get open positions.
        
        Args:
            symbol: Optional symbol filter
        
        Returns:
            List of open positions
        """
        data = self.client.get_positions(inst_id=symbol)
        positions = []
        
        for pos_data in data:
            # Only include positions with actual size
            if float(pos_data.get("positions", 0)) != 0:
                positions.append(Position.from_api(pos_data))
        
        self._positions_cache = positions
        return positions
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        positions = self.get_positions(symbol)
        return positions[0] if positions else None
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get open orders."""
        data = self.client.get_open_orders(inst_id=symbol)
        return [Order.from_api(o) for o in data]
    
    def get_order_history(self, symbol: Optional[str] = None, limit: int = 50) -> List[Order]:
        """Get order history."""
        data = self.client.get_order_history(inst_id=symbol, limit=limit)
        return [Order.from_api(o) for o in data]
    
    def get_total_exposure(self) -> float:
        """Get total exposure across all positions."""
        positions = self.get_positions()
        return sum(p.notional_value for p in positions)
    
    def get_exposure_percent(self) -> float:
        """Get exposure as percentage of equity."""
        balance = self.get_balance()
        exposure = self.get_total_exposure()
        
        if balance.total_equity == 0:
            return 0
        return (exposure / balance.total_equity) * 100
    
    def get_account_summary(self) -> dict:
        """
        Get comprehensive account summary for AI analysis.
        
        Returns:
            Dict with balance, positions, and exposure metrics
        """
        balance = self.get_balance()
        positions = self.get_positions()
        
        return {
            "balance": {
                "total_equity": balance.total_equity,
                "available": balance.available_balance,
                "used_margin": balance.used_margin,
                "unrealized_pnl": balance.unrealized_pnl,
                "margin_ratio": balance.margin_ratio,
            },
            "positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "size": p.size,
                    "pnl": p.unrealized_pnl,
                    "pnl_percent": p.pnl_percent,
                    "leverage": p.leverage,
                    "liq_distance": p.distance_to_liquidation,
                }
                for p in positions
            ],
            "exposure": {
                "total_notional": self.get_total_exposure(),
                "exposure_percent": self.get_exposure_percent(),
                "position_count": len(positions),
            }
        }
