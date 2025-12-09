"""Base strategy interface and signal definitions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class SignalType(Enum):
    """Signal types."""
    LONG = "long"
    SHORT = "short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    CLOSE_ALL = "close_all"


@dataclass
class Signal:
    """Trading signal from a strategy."""
    signal_id: str
    timestamp: datetime
    symbol: str
    signal_type: SignalType
    price: float
    confidence: float = 0.5  # 0-1
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    size_percent: float = 1.0  # % of account
    source: str = "manual"  # strategy name or "manual"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_entry(self) -> bool:
        return self.signal_type in [SignalType.LONG, SignalType.SHORT]
    
    @property
    def is_exit(self) -> bool:
        return self.signal_type in [
            SignalType.CLOSE_LONG, 
            SignalType.CLOSE_SHORT, 
            SignalType.CLOSE_ALL
        ]
    
    def to_dict(self) -> Dict:
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "price": self.price,
            "confidence": self.confidence,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "size_percent": self.size_percent,
            "source": self.source,
            "metadata": self.metadata,
        }


class Strategy(ABC):
    """
    Base class for trading strategies.
    
    Subclass this to create custom strategies:
    
        class MyStrategy(Strategy):
            name = "my_strategy"
            
            def generate_signals(self, candles, context):
                # Your logic here
                return [Signal(...)]
    """
    
    name: str = "base"
    description: str = ""
    timeframe: str = "1h"  # Default timeframe
    symbols: List[str] = []  # Symbols this strategy trades
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.enabled = True
        self._signal_counter = 0
    
    def _generate_signal_id(self) -> str:
        self._signal_counter += 1
        return f"{self.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._signal_counter}"
    
    @abstractmethod
    def generate_signals(
        self, 
        candles: List[Dict], 
        context: Dict[str, Any]
    ) -> List[Signal]:
        """
        Generate signals from candle data.
        
        Args:
            candles: List of OHLCV candles
            context: Additional context (funding, orderbook, etc.)
        
        Returns:
            List of Signal objects
        """
        pass
    
    def on_signal_executed(self, signal: Signal, result: Dict):
        """Called when a signal is executed. Override for tracking."""
        pass
    
    def on_position_update(self, position: Dict):
        """Called when a position updates. Override for management."""
        pass
    
    def get_params(self) -> Dict[str, Any]:
        """Return strategy parameters for logging/display."""
        return self.config.copy()
    
    def set_params(self, params: Dict[str, Any]):
        """Update strategy parameters."""
        self.config.update(params)


class StrategyManager:
    """Manages multiple strategies."""
    
    def __init__(self):
        self.strategies: Dict[str, Strategy] = {}
    
    def register(self, strategy: Strategy):
        """Register a strategy."""
        self.strategies[strategy.name] = strategy
    
    def unregister(self, name: str):
        """Unregister a strategy."""
        self.strategies.pop(name, None)
    
    def get(self, name: str) -> Optional[Strategy]:
        """Get strategy by name."""
        return self.strategies.get(name)
    
    def list_enabled(self) -> List[Strategy]:
        """Get all enabled strategies."""
        return [s for s in self.strategies.values() if s.enabled]
    
    def generate_all_signals(
        self, 
        symbol: str,
        candles: List[Dict],
        context: Dict
    ) -> List[Signal]:
        """Generate signals from all enabled strategies."""
        signals = []
        for strategy in self.list_enabled():
            if not strategy.symbols or symbol in strategy.symbols:
                try:
                    new_signals = strategy.generate_signals(candles, context)
                    signals.extend(new_signals)
                except Exception as e:
                    print(f"Strategy {strategy.name} error: {e}")
        return signals
