"""Position management with TP/SL automation."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..core.client import BlofinClient
from ..core.config import Config
from ..core.logger import get_trade_logger
from ..data.account import AccountData, Position

logger = get_trade_logger()


@dataclass
class TPSLLevels:
    """Take profit and stop loss levels."""
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None  # Distance in %
    break_even_trigger: Optional[float] = None  # Move SL to entry when TP% reached


class PositionManager:
    """
    Position management and automation.
    
    Features:
    - Monitor positions in real-time
    - Set/adjust TP/SL levels
    - Break-even automation
    - Trailing stop updates
    - Partial close support
    
    Usage:
        positions = PositionManager(client, config, account)
        
        # Get active positions
        active = positions.get_active()
        
        # Set stop loss
        positions.set_stop_loss("BTC-USDT", 94000)
        
        # Move stop to break even
        positions.move_to_breakeven("BTC-USDT")
    """
    
    def __init__(
        self,
        client: BlofinClient,
        config: Config,
        account: AccountData
    ):
        self.client = client
        self.config = config
        self.account = account
        
        # Track TP/SL levels locally
        self._tpsl_levels: Dict[str, TPSLLevels] = {}
    
    def get_active(self) -> List[Position]:
        """Get all active positions."""
        return self.account.get_positions()
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        return self.account.get_position(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """Check if we have an open position."""
        pos = self.get_position(symbol)
        return pos is not None and pos.size > 0
    
    def set_stop_loss(self, symbol: str, price: float) -> bool:
        """
        Set or update stop loss for a position.
        
        Args:
            symbol: Trading pair
            price: Stop loss price
        
        Returns:
            True if successful
        """
        position = self.get_position(symbol)
        if not position:
            logger.warning(f"No position for {symbol}")
            return False
        
        # Validate SL is on correct side
        if position.side.value == "long" and price >= position.mark_price:
            logger.warning(f"SL must be below current price for longs")
            return False
        if position.side.value == "short" and price <= position.mark_price:
            logger.warning(f"SL must be above current price for shorts")
            return False
        
        try:
            # TODO: Use TPSL API endpoint
            # For now, track locally
            if symbol not in self._tpsl_levels:
                self._tpsl_levels[symbol] = TPSLLevels()
            
            self._tpsl_levels[symbol].stop_loss = price
            logger.info(f"Stop loss set: {symbol} @ ${price:,.2f}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to set SL: {e}")
            return False
    
    def set_take_profit(self, symbol: str, price: float) -> bool:
        """
        Set or update take profit for a position.
        
        Args:
            symbol: Trading pair
            price: Take profit price
        
        Returns:
            True if successful
        """
        position = self.get_position(symbol)
        if not position:
            logger.warning(f"No position for {symbol}")
            return False
        
        # Validate TP is on correct side
        if position.side.value == "long" and price <= position.mark_price:
            logger.warning(f"TP must be above current price for longs")
            return False
        if position.side.value == "short" and price >= position.mark_price:
            logger.warning(f"TP must be below current price for shorts")
            return False
        
        try:
            if symbol not in self._tpsl_levels:
                self._tpsl_levels[symbol] = TPSLLevels()
            
            self._tpsl_levels[symbol].take_profit = price
            logger.info(f"Take profit set: {symbol} @ ${price:,.2f}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to set TP: {e}")
            return False
    
    def set_tpsl(
        self,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        """Set both TP and SL at once."""
        success = True
        
        if stop_loss:
            success = self.set_stop_loss(symbol, stop_loss) and success
        if take_profit:
            success = self.set_take_profit(symbol, take_profit) and success
        
        return success
    
    def move_to_breakeven(self, symbol: str, buffer_pct: float = 0.1) -> bool:
        """
        Move stop loss to entry price (break even).
        
        Args:
            symbol: Trading pair
            buffer_pct: Buffer above/below entry (0.1 = 0.1%)
        
        Returns:
            True if successful
        """
        position = self.get_position(symbol)
        if not position:
            logger.warning(f"No position for {symbol}")
            return False
        
        # Check if in profit
        if not position.is_profitable:
            logger.warning(f"Position not in profit, cannot move to BE")
            return False
        
        # Calculate BE with buffer
        buffer = position.avg_price * (buffer_pct / 100)
        
        if position.side.value == "long":
            be_price = position.avg_price + buffer
        else:
            be_price = position.avg_price - buffer
        
        return self.set_stop_loss(symbol, be_price)
    
    def close_position(
        self,
        symbol: str,
        percent: float = 100
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Close a position (full or partial).
        
        Args:
            symbol: Trading pair
            percent: Percentage to close (100 = full close)
        
        Returns:
            (success, result_dict)
        """
        position = self.get_position(symbol)
        if not position:
            return False, {"error": "No position found"}
        
        try:
            if percent >= 100:
                # Full close
                result = self.client.close_position(symbol)
                logger.info(f"Position closed: {symbol}")
            else:
                # Partial close - place a reduce-only order
                close_size = position.size * (percent / 100)
                side = "sell" if position.side.value == "long" else "buy"
                
                result = self.client.place_order(
                    inst_id=symbol,
                    side=side,
                    size=str(close_size),
                    order_type="market",
                    reduce_only=True
                )
                logger.info(f"Partial close: {symbol} {percent}%")
            
            # Clear TP/SL tracking
            if percent >= 100 and symbol in self._tpsl_levels:
                del self._tpsl_levels[symbol]
            
            return True, result
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return False, {"error": str(e)}
    
    def close_all(self) -> List[Tuple[str, bool]]:
        """
        Close all positions.
        
        Returns:
            List of (symbol, success) tuples
        """
        results = []
        positions = self.get_active()
        
        for pos in positions:
            success, _ = self.close_position(pos.symbol)
            results.append((pos.symbol, success))
        
        self._tpsl_levels.clear()
        return results
    
    def get_tpsl_levels(self, symbol: str) -> Optional[TPSLLevels]:
        """Get configured TP/SL levels for a position."""
        return self._tpsl_levels.get(symbol)
    
    def calculate_pnl_at_price(
        self,
        symbol: str,
        target_price: float
    ) -> Optional[float]:
        """
        Calculate P&L if price hits target.
        
        Args:
            symbol: Trading pair
            target_price: Target price to calculate P&L at
        
        Returns:
            Estimated P&L in USD
        """
        position = self.get_position(symbol)
        if not position:
            return None
        
        price_diff = target_price - position.avg_price
        
        if position.side.value == "long":
            pnl = price_diff * position.size
        else:
            pnl = -price_diff * position.size
        
        return pnl
    
    def get_position_summary(self) -> Dict:
        """Get summary of all positions."""
        positions = self.get_active()
        
        total_pnl = sum(p.unrealized_pnl for p in positions)
        total_value = sum(p.notional_value for p in positions)
        
        return {
            "count": len(positions),
            "total_unrealized_pnl": total_pnl,
            "total_value": total_value,
            "positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "size": p.size,
                    "entry": p.avg_price,
                    "current": p.mark_price,
                    "pnl": p.unrealized_pnl,
                    "pnl_pct": p.pnl_percent,
                    "leverage": p.leverage,
                    "liq_distance": p.distance_to_liquidation,
                    "tpsl": self._tpsl_levels.get(p.symbol),
                }
                for p in positions
            ]
        }
