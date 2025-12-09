"""Signal generation and external signal ingestion."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .base import Signal, SignalType, Strategy
from .indicators import Indicators
from ..core.logger import get_logger

logger = get_logger("signals")


class SignalGenerator:
    """
    Generate and manage trading signals.
    
    Supports:
    - Built-in indicator-based signals
    - External signals via webhook/file
    - AI-generated signals
    - Manual signals
    """
    
    def __init__(self):
        self.signals: List[Signal] = []
        self.callbacks: List[Callable[[Signal], None]] = []
        self._signal_counter = 0
    
    def _next_id(self) -> str:
        self._signal_counter += 1
        return f"sig_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._signal_counter}"
    
    def on_signal(self, callback: Callable[[Signal], None]):
        """Register callback for new signals."""
        self.callbacks.append(callback)
    
    def _emit(self, signal: Signal):
        """Emit signal to all callbacks."""
        self.signals.append(signal)
        for callback in self.callbacks:
            try:
                callback(signal)
            except Exception as e:
                logger.error(f"Signal callback error: {e}")
    
    def create_signal(
        self,
        symbol: str,
        signal_type: SignalType,
        price: float,
        confidence: float = 0.5,
        stop_loss: float = None,
        take_profit: float = None,
        size_percent: float = 1.0,
        source: str = "manual",
        metadata: Dict = None
    ) -> Signal:
        """Create and emit a new signal."""
        signal = Signal(
            signal_id=self._next_id(),
            timestamp=datetime.now(),
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size_percent=size_percent,
            source=source,
            metadata=metadata or {}
        )
        self._emit(signal)
        logger.info(f"Signal: {signal.signal_type.value} {symbol} @ {price} ({source})")
        return signal
    
    # Built-in signal generators
    
    def from_rsi(
        self,
        symbol: str,
        prices: List[float],
        current_price: float,
        oversold: float = 30,
        overbought: float = 70,
        period: int = 14
    ) -> Optional[Signal]:
        """Generate signal from RSI."""
        result = Indicators.rsi(prices, period)
        if not result:
            return None
        
        if result.value < oversold:
            return self.create_signal(
                symbol=symbol,
                signal_type=SignalType.LONG,
                price=current_price,
                confidence=result.strength,
                source="rsi_oversold",
                metadata={"rsi": result.value}
            )
        elif result.value > overbought:
            return self.create_signal(
                symbol=symbol,
                signal_type=SignalType.SHORT,
                price=current_price,
                confidence=result.strength,
                source="rsi_overbought",
                metadata={"rsi": result.value}
            )
        return None
    
    def from_ema_cross(
        self,
        symbol: str,
        prices: List[float],
        current_price: float,
        fast_period: int = 9,
        slow_period: int = 21
    ) -> Optional[Signal]:
        """Generate signal from EMA crossover."""
        if len(prices) < slow_period + 2:
            return None
        
        fast = Indicators.ema_series(prices, fast_period)
        slow = Indicators.ema_series(prices, slow_period)
        
        # Align series
        offset = slow_period - fast_period
        if len(fast) <= offset + 1 or len(slow) < 2:
            return None
        
        # Check for crossover
        fast_curr = fast[-1]
        fast_prev = fast[-2]
        slow_curr = slow[-1]
        slow_prev = slow[-(1 + (len(fast) - len(slow)))] if len(fast) > len(slow) else slow[-1]
        
        # Bullish cross
        if fast_prev <= slow_prev and fast_curr > slow_curr:
            return self.create_signal(
                symbol=symbol,
                signal_type=SignalType.LONG,
                price=current_price,
                confidence=0.6,
                source="ema_cross_bullish",
                metadata={"fast_ema": fast_curr, "slow_ema": slow_curr}
            )
        # Bearish cross
        elif fast_prev >= slow_prev and fast_curr < slow_curr:
            return self.create_signal(
                symbol=symbol,
                signal_type=SignalType.SHORT,
                price=current_price,
                confidence=0.6,
                source="ema_cross_bearish",
                metadata={"fast_ema": fast_curr, "slow_ema": slow_curr}
            )
        return None
    
    def from_macd(
        self,
        symbol: str,
        prices: List[float],
        current_price: float
    ) -> Optional[Signal]:
        """Generate signal from MACD crossover."""
        result = Indicators.macd(prices)
        if not result or not result.get("crossover"):
            return None
        
        if result["crossover"] == "bullish":
            return self.create_signal(
                symbol=symbol,
                signal_type=SignalType.LONG,
                price=current_price,
                confidence=0.65,
                source="macd_cross_bullish",
                metadata=result
            )
        elif result["crossover"] == "bearish":
            return self.create_signal(
                symbol=symbol,
                signal_type=SignalType.SHORT,
                price=current_price,
                confidence=0.65,
                source="macd_cross_bearish",
                metadata=result
            )
        return None
    
    def from_bollinger(
        self,
        symbol: str,
        prices: List[float],
        current_price: float,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Optional[Signal]:
        """Generate signal from Bollinger Band touch."""
        result = Indicators.bollinger_bands(prices, period, std_dev)
        if not result:
            return None
        
        # Price below lower band
        if current_price < result["lower"]:
            return self.create_signal(
                symbol=symbol,
                signal_type=SignalType.LONG,
                price=current_price,
                confidence=0.55,
                stop_loss=result["lower"] * 0.99,
                take_profit=result["middle"],
                source="bb_oversold",
                metadata=result
            )
        # Price above upper band
        elif current_price > result["upper"]:
            return self.create_signal(
                symbol=symbol,
                signal_type=SignalType.SHORT,
                price=current_price,
                confidence=0.55,
                stop_loss=result["upper"] * 1.01,
                take_profit=result["middle"],
                source="bb_overbought",
                metadata=result
            )
        return None
    
    # External signal ingestion
    
    def from_webhook(self, data: Dict[str, Any]) -> Optional[Signal]:
        """
        Parse signal from webhook payload.
        
        Expected format:
        {
            "symbol": "BTC-USDT",
            "action": "long" | "short" | "close",
            "price": 50000,
            "stop_loss": 49000,
            "take_profit": 52000,
            "confidence": 0.75,
            "source": "tradingview"
        }
        """
        try:
            action_map = {
                "long": SignalType.LONG,
                "short": SignalType.SHORT,
                "close": SignalType.CLOSE_ALL,
                "close_long": SignalType.CLOSE_LONG,
                "close_short": SignalType.CLOSE_SHORT,
            }
            
            signal_type = action_map.get(data.get("action", "").lower())
            if not signal_type:
                logger.warning(f"Invalid webhook action: {data.get('action')}")
                return None
            
            return self.create_signal(
                symbol=data["symbol"],
                signal_type=signal_type,
                price=float(data["price"]),
                confidence=float(data.get("confidence", 0.5)),
                stop_loss=float(data["stop_loss"]) if data.get("stop_loss") else None,
                take_profit=float(data["take_profit"]) if data.get("take_profit") else None,
                size_percent=float(data.get("size_percent", 1.0)),
                source=data.get("source", "webhook"),
                metadata=data.get("metadata", {})
            )
        except Exception as e:
            logger.error(f"Webhook parse error: {e}")
            return None
    
    def from_file(self, filepath: str) -> List[Signal]:
        """
        Load signals from JSON file.
        
        File format: list of signal objects or single signal.
        """
        signals = []
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            
            if isinstance(data, list):
                for item in data:
                    sig = self.from_webhook(item)
                    if sig:
                        signals.append(sig)
            else:
                sig = self.from_webhook(data)
                if sig:
                    signals.append(sig)
                    
        except Exception as e:
            logger.error(f"File load error: {e}")
        
        return signals
    
    def get_recent(self, limit: int = 20) -> List[Signal]:
        """Get recent signals."""
        return self.signals[-limit:]
    
    def get_by_symbol(self, symbol: str, limit: int = 10) -> List[Signal]:
        """Get signals for a symbol."""
        return [s for s in self.signals if s.symbol == symbol][-limit:]


# Built-in strategies

class RSIStrategy(Strategy):
    """Simple RSI overbought/oversold strategy."""
    
    name = "rsi"
    description = "RSI overbought/oversold signals"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.period = self.config.get("period", 14)
        self.oversold = self.config.get("oversold", 30)
        self.overbought = self.config.get("overbought", 70)
    
    def generate_signals(self, candles: List[Dict], context: Dict) -> List[Signal]:
        signals = []
        if len(candles) < self.period + 1:
            return signals
        
        prices = [c["close"] for c in candles]
        current_price = prices[-1]
        symbol = context.get("symbol", "UNKNOWN")
        
        result = Indicators.rsi(prices, self.period)
        if not result:
            return signals
        
        if result.value < self.oversold:
            signals.append(Signal(
                signal_id=self._generate_signal_id(),
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.LONG,
                price=current_price,
                confidence=result.strength,
                source=self.name,
                metadata={"rsi": result.value}
            ))
        elif result.value > self.overbought:
            signals.append(Signal(
                signal_id=self._generate_signal_id(),
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.SHORT,
                price=current_price,
                confidence=result.strength,
                source=self.name,
                metadata={"rsi": result.value}
            ))
        
        return signals


class EMACrossStrategy(Strategy):
    """EMA crossover strategy."""
    
    name = "ema_cross"
    description = "EMA crossover signals"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.fast_period = self.config.get("fast_period", 9)
        self.slow_period = self.config.get("slow_period", 21)
    
    def generate_signals(self, candles: List[Dict], context: Dict) -> List[Signal]:
        signals = []
        if len(candles) < self.slow_period + 2:
            return signals
        
        prices = [c["close"] for c in candles]
        current_price = prices[-1]
        symbol = context.get("symbol", "UNKNOWN")
        
        fast = Indicators.ema_series(prices, self.fast_period)
        slow = Indicators.ema_series(prices, self.slow_period)
        
        if len(fast) < 2 or len(slow) < 2:
            return signals
        
        # Bullish cross
        if fast[-2] <= slow[-2] and fast[-1] > slow[-1]:
            signals.append(Signal(
                signal_id=self._generate_signal_id(),
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.LONG,
                price=current_price,
                confidence=0.6,
                source=self.name,
                metadata={"fast_ema": fast[-1], "slow_ema": slow[-1]}
            ))
        # Bearish cross
        elif fast[-2] >= slow[-2] and fast[-1] < slow[-1]:
            signals.append(Signal(
                signal_id=self._generate_signal_id(),
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.SHORT,
                price=current_price,
                confidence=0.6,
                source=self.name,
                metadata={"fast_ema": fast[-1], "slow_ema": slow[-1]}
            ))
        
        return signals
