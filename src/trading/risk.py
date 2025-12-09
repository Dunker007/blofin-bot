"""Risk management and position sizing calculator."""

from dataclasses import dataclass
from typing import Optional, Tuple

from ..core.config import Config, AutonomyConfig
from ..core.logger import get_trade_logger
from ..data.account import AccountData, Balance

logger = get_trade_logger()


@dataclass
class RiskCalculation:
    """Result of a risk calculation."""
    position_size: float
    position_value: float
    risk_amount: float
    risk_percent: float
    leverage: int
    margin_required: float
    liquidation_distance: float
    is_valid: bool
    rejection_reason: str = ""


class RiskManager:
    """
    Risk management and position sizing.
    
    Features:
    - Calculate position size from risk percentage
    - Enforce max position limits
    - Check exposure limits
    - Validate trades against rules
    
    Usage:
        risk = RiskManager(config, account)
        
        # Calculate size for 1% risk
        calc = risk.calculate_position_size(
            symbol="BTC-USDT",
            entry=95000,
            stop_loss=94000,
            risk_percent=1.0
        )
        
        if calc.is_valid:
            print(f"Size: {calc.position_size} contracts")
    """
    
    def __init__(self, config: Config, account: AccountData):
        self.config = config
        self.autonomy = config.autonomy
        self.account = account
    
    def calculate_position_size(
        self,
        symbol: str,
        entry: float,
        stop_loss: float,
        risk_percent: float = 1.0,
        leverage: Optional[int] = None
    ) -> RiskCalculation:
        """
        Calculate position size based on risk percentage.
        
        Args:
            symbol: Trading pair
            entry: Entry price
            stop_loss: Stop loss price
            risk_percent: Percentage of account to risk
            leverage: Leverage to use (default from config)
        
        Returns:
            RiskCalculation with size and validation
        """
        # Get pair config
        pair_config = self.config.get_pair(symbol)
        max_leverage = pair_config.max_leverage if pair_config else self.autonomy.max_leverage
        leverage = min(leverage or max_leverage, max_leverage)
        
        # Get account balance
        try:
            balance = self.account.get_balance()
            equity = balance.total_equity
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return RiskCalculation(
                position_size=0, position_value=0, risk_amount=0,
                risk_percent=0, leverage=leverage, margin_required=0,
                liquidation_distance=0, is_valid=False,
                rejection_reason="Failed to get account balance"
            )
        
        if equity <= 0:
            return RiskCalculation(
                position_size=0, position_value=0, risk_amount=0,
                risk_percent=0, leverage=leverage, margin_required=0,
                liquidation_distance=0, is_valid=False,
                rejection_reason="No account equity"
            )
        
        # Calculate risk amount
        risk_amount = equity * (risk_percent / 100)
        
        # Calculate stop distance
        stop_distance = abs(entry - stop_loss)
        stop_distance_pct = stop_distance / entry
        
        if stop_distance <= 0:
            return RiskCalculation(
                position_size=0, position_value=0, risk_amount=0,
                risk_percent=risk_percent, leverage=leverage, margin_required=0,
                liquidation_distance=0, is_valid=False,
                rejection_reason="Invalid stop loss (must be different from entry)"
            )
        
        # Position size = Risk Amount / Stop Distance (in USD per unit)
        position_value = risk_amount / stop_distance_pct
        position_size = position_value / entry
        
        # Calculate margin required
        margin_required = position_value / leverage
        
        # Estimate liquidation distance (simplified)
        # Liq happens roughly when position loses margin * leverage
        liq_distance_pct = (1 / leverage) * 100 * 0.9  # 90% of max
        
        # Validate against limits
        is_valid, rejection = self._validate_position(
            symbol, position_value, margin_required, equity, balance
        )
        
        calc = RiskCalculation(
            position_size=round(position_size, 6),
            position_value=round(position_value, 2),
            risk_amount=round(risk_amount, 2),
            risk_percent=risk_percent,
            leverage=leverage,
            margin_required=round(margin_required, 2),
            liquidation_distance=round(liq_distance_pct, 2),
            is_valid=is_valid,
            rejection_reason=rejection
        )
        
        logger.debug(f"Risk calc for {symbol}: size={calc.position_size}, risk=${calc.risk_amount}")
        
        return calc
    
    def _validate_position(
        self,
        symbol: str,
        position_value: float,
        margin_required: float,
        equity: float,
        balance: Balance
    ) -> Tuple[bool, str]:
        """Validate position against all risk rules."""
        
        # Check max single position
        max_single_pct = self.autonomy.max_single_position_percent
        position_pct = (position_value / equity) * 100
        
        if position_pct > max_single_pct:
            return False, f"Position too large: {position_pct:.1f}% > {max_single_pct}% max"
        
        # Check available margin
        if margin_required > balance.available_balance:
            return False, f"Insufficient margin: need ${margin_required:.2f}, have ${balance.available_balance:.2f}"
        
        # Check total exposure after this position
        try:
            current_exposure = self.account.get_total_exposure()
            new_exposure = current_exposure + position_value
            new_exposure_pct = (new_exposure / equity) * 100
            
            if new_exposure_pct > self.autonomy.max_exposure_percent:
                return False, f"Would exceed max exposure: {new_exposure_pct:.1f}% > {self.autonomy.max_exposure_percent}%"
        except Exception:
            pass  # Continue if can't check current exposure
        
        # Check max positions
        try:
            positions = self.account.get_positions()
            if len(positions) >= self.autonomy.max_positions:
                return False, f"Max positions reached: {len(positions)} >= {self.autonomy.max_positions}"
        except Exception:
            pass
        
        return True, ""
    
    def calculate_stop_loss(
        self,
        entry: float,
        side: str,
        risk_percent: float = 1.0,
        leverage: int = 10
    ) -> float:
        """
        Calculate stop loss price from risk percentage.
        
        Args:
            entry: Entry price
            side: "long" or "short"
            risk_percent: Risk as percent of position
            leverage: Leverage used
        
        Returns:
            Stop loss price
        """
        # Stop distance = risk% / leverage
        stop_distance_pct = risk_percent / leverage / 100
        
        if side == "long":
            return entry * (1 - stop_distance_pct)
        else:
            return entry * (1 + stop_distance_pct)
    
    def calculate_take_profit(
        self,
        entry: float,
        stop_loss: float,
        side: str,
        rr_ratio: float = 2.0
    ) -> float:
        """
        Calculate take profit from risk/reward ratio.
        
        Args:
            entry: Entry price
            stop_loss: Stop loss price
            side: "long" or "short"
            rr_ratio: Risk/reward ratio (e.g., 2.0 for 2:1)
        
        Returns:
            Take profit price
        """
        risk = abs(entry - stop_loss)
        reward = risk * rr_ratio
        
        if side == "long":
            return entry + reward
        else:
            return entry - reward
    
    def get_position_risk(self, symbol: str) -> Optional[dict]:
        """
        Get current risk metrics for an open position.
        
        Returns:
            Dict with risk metrics or None if no position
        """
        position = self.account.get_position(symbol)
        if not position:
            return None
        
        balance = self.account.get_balance()
        
        return {
            "symbol": symbol,
            "side": position.side.value,
            "size": position.size,
            "entry": position.avg_price,
            "current": position.mark_price,
            "unrealized_pnl": position.unrealized_pnl,
            "pnl_percent": position.pnl_percent,
            "position_value": position.notional_value,
            "position_value_pct": (position.notional_value / balance.total_equity) * 100,
            "liq_distance": position.distance_to_liquidation,
            "margin_used": position.margin,
        }
    
    def check_can_trade(self) -> Tuple[bool, str]:
        """
        Check if trading is allowed based on risk rules.
        
        Returns:
            (can_trade, reason)
        """
        try:
            balance = self.account.get_balance()
            
            # Check margin ratio
            if balance.margin_ratio > 80:
                return False, f"Margin ratio too high: {balance.margin_ratio:.1f}%"
            
            # Check positions
            positions = self.account.get_positions()
            if len(positions) >= self.autonomy.max_positions:
                return False, f"Max positions reached: {len(positions)}"
            
            # Check exposure
            exposure_pct = self.account.get_exposure_percent()
            if exposure_pct >= self.autonomy.max_exposure_percent:
                return False, f"Max exposure reached: {exposure_pct:.1f}%"
            
            return True, ""
            
        except Exception as e:
            return False, f"Risk check failed: {e}"
