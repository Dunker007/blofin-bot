"""AI Trading Styles/Personalities for different strategies."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class TradingStyle(Enum):
    """Available trading styles."""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    SCALPER = "scalper"
    SWING = "swing"
    DEGEN = "degen"


@dataclass
class StyleConfig:
    """Configuration for a trading style."""
    name: str
    description: str
    emoji: str
    
    # Risk parameters
    risk_per_trade: float  # % of account
    min_confidence: int  # 0-100
    max_leverage: int
    min_rr_ratio: float  # Risk:Reward
    
    # Trade parameters
    max_positions: int
    max_daily_trades: int
    max_daily_loss: float  # %
    
    # Timeframe preference
    timeframe: str  # "1m", "5m", "1h", "4h", "1d"
    hold_time: str  # Description
    
    # AI prompt modifier
    prompt_modifier: str
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "emoji": self.emoji,
            "risk_per_trade": self.risk_per_trade,
            "min_confidence": self.min_confidence,
            "max_leverage": self.max_leverage,
            "min_rr_ratio": self.min_rr_ratio,
            "max_positions": self.max_positions,
            "max_daily_trades": self.max_daily_trades,
            "max_daily_loss": self.max_daily_loss,
            "timeframe": self.timeframe,
            "hold_time": self.hold_time,
        }


# Predefined trading styles
TRADING_STYLES: Dict[TradingStyle, StyleConfig] = {
    TradingStyle.CONSERVATIVE: StyleConfig(
        name="Conservative",
        description="Low risk, high conviction trades only. Patient and selective.",
        emoji="🛡️",
        risk_per_trade=0.5,
        min_confidence=85,
        max_leverage=3,
        min_rr_ratio=2.5,
        max_positions=2,
        max_daily_trades=3,
        max_daily_loss=3,
        timeframe="4h",
        hold_time="Days to weeks",
        prompt_modifier="""You are a conservative trader. Only take trades with very high confidence.
        Prefer longer timeframes, wait for clear setups. Never chase, never FOMO.
        Risk management is paramount. If in doubt, don't trade."""
    ),
    
    TradingStyle.BALANCED: StyleConfig(
        name="Balanced",
        description="Moderate risk with good conviction. Best for most traders.",
        emoji="⚖️",
        risk_per_trade=1.0,
        min_confidence=75,
        max_leverage=5,
        min_rr_ratio=2.0,
        max_positions=3,
        max_daily_trades=5,
        max_daily_loss=5,
        timeframe="1h",
        hold_time="Hours to days",
        prompt_modifier="""You are a balanced trader. Look for quality setups with good R:R.
        Don't overtrade but don't miss obvious opportunities.
        Manage risk well and cut losers quickly."""
    ),
    
    TradingStyle.AGGRESSIVE: StyleConfig(
        name="Aggressive",
        description="Higher risk, more frequent trades. For experienced traders.",
        emoji="⚡",
        risk_per_trade=2.0,
        min_confidence=65,
        max_leverage=10,
        min_rr_ratio=1.5,
        max_positions=5,
        max_daily_trades=10,
        max_daily_loss=10,
        timeframe="15m",
        hold_time="Minutes to hours",
        prompt_modifier="""You are an aggressive trader. Take more trades, accept more risk.
        Look for momentum and quick moves. Use tight stops but don't be afraid to take shots.
        Cut losers immediately, let winners run."""
    ),
    
    TradingStyle.SCALPER: StyleConfig(
        name="Scalper",
        description="Very short trades, small gains, high frequency.",
        emoji="🎯",
        risk_per_trade=0.5,
        min_confidence=70,
        max_leverage=20,
        min_rr_ratio=1.0,
        max_positions=2,
        max_daily_trades=50,
        max_daily_loss=5,
        timeframe="1m",
        hold_time="Seconds to minutes",
        prompt_modifier="""You are a scalper. Look for very short-term moves.
        Take small profits quickly, use tight stops. Focus on high-volume moments.
        Never hold a scalp that goes against you."""
    ),
    
    TradingStyle.SWING: StyleConfig(
        name="Swing Trader",
        description="Multi-day holds, catching bigger moves.",
        emoji="🌊",
        risk_per_trade=1.5,
        min_confidence=80,
        max_leverage=5,
        min_rr_ratio=3.0,
        max_positions=4,
        max_daily_trades=2,
        max_daily_loss=5,
        timeframe="4h",
        hold_time="Days to weeks",
        prompt_modifier="""You are a swing trader. Look for multi-day opportunities.
        Focus on trend changes, support/resistance, and major levels.
        Give trades room to breathe, use wider stops for bigger targets."""
    ),
    
    TradingStyle.DEGEN: StyleConfig(
        name="Degen Mode",
        description="⚠️ MAXIMUM RISK. For entertainment only. You will probably lose money.",
        emoji="🎰",
        risk_per_trade=5.0,
        min_confidence=50,
        max_leverage=50,
        min_rr_ratio=1.0,
        max_positions=10,
        max_daily_trades=100,
        max_daily_loss=50,
        timeframe="1m",
        hold_time="YOLO",
        prompt_modifier="""You are in DEGEN MODE. Maximum aggression, maximum leverage.
        Take every opportunity, no matter how risky. This is gambling.
        ⚠️ WARNING: This mode will likely result in account liquidation."""
    ),
}


class TradingStyleManager:
    """
    Manage trading styles and apply them to AI decisions.
    
    Usage:
        styles = TradingStyleManager()
        
        # Get current style
        style = styles.get_current()
        
        # Change style
        styles.set_style(TradingStyle.AGGRESSIVE)
        
        # Get style config for AI
        config = styles.get_style_config()
    """
    
    def __init__(self, default: TradingStyle = TradingStyle.BALANCED):
        self._current = default
    
    @property
    def current(self) -> TradingStyle:
        """Get current trading style."""
        return self._current
    
    @property
    def current_config(self) -> StyleConfig:
        """Get current style configuration."""
        return TRADING_STYLES[self._current]
    
    def set_style(self, style: TradingStyle) -> StyleConfig:
        """Set the active trading style."""
        self._current = style
        return self.current_config
    
    def set_style_by_name(self, name: str) -> Optional[StyleConfig]:
        """Set style by name string."""
        try:
            style = TradingStyle(name.lower())
            return self.set_style(style)
        except ValueError:
            return None
    
    def get_all_styles(self) -> Dict[str, Dict]:
        """Get all available styles."""
        return {
            style.value: config.to_dict()
            for style, config in TRADING_STYLES.items()
        }
    
    def get_prompt_modifier(self) -> str:
        """Get AI prompt modifier for current style."""
        return self.current_config.prompt_modifier
    
    def get_risk_params(self) -> Dict:
        """Get risk parameters for current style."""
        config = self.current_config
        return {
            "risk_per_trade": config.risk_per_trade,
            "min_confidence": config.min_confidence,
            "max_leverage": config.max_leverage,
            "min_rr_ratio": config.min_rr_ratio,
            "max_positions": config.max_positions,
            "max_daily_trades": config.max_daily_trades,
            "max_daily_loss": config.max_daily_loss,
        }
