"""Market analyzer with technical indicators."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..data.market import Candle, MarketData
from ..core.logger import get_ai_logger

logger = get_ai_logger()


@dataclass
class TechnicalAnalysis:
    """Technical analysis results."""
    symbol: str
    trend: str  # bullish, bearish, neutral
    trend_strength: int  # 1-10
    rsi: float
    rsi_signal: str  # oversold, overbought, neutral
    ema_fast: float
    ema_slow: float
    ema_signal: str  # bullish, bearish, neutral
    support_levels: List[float]
    resistance_levels: List[float]
    
    @property
    def summary(self) -> str:
        """Human-readable summary."""
        return (
            f"{self.symbol}: {self.trend.upper()} (strength {self.trend_strength}/10)\n"
            f"RSI: {self.rsi:.1f} ({self.rsi_signal})\n"
            f"EMA: {self.ema_signal} (fast={self.ema_fast:.2f}, slow={self.ema_slow:.2f})"
        )


class MarketAnalyzer:
    """
    Technical analysis and market structure detection.
    
    Usage:
        analyzer = MarketAnalyzer(market_data)
        analysis = analyzer.analyze("BTC-USDT")
    """
    
    def __init__(self, market: MarketData):
        self.market = market
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """
        Calculate Exponential Moving Average.
        
        Args:
            prices: List of prices (oldest to newest)
            period: EMA period
        
        Returns:
            EMA value
        """
        if len(prices) < period:
            return prices[-1] if prices else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Start with SMA
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        Calculate Relative Strength Index.
        
        Args:
            prices: List of prices (oldest to newest)
            period: RSI period
        
        Returns:
            RSI value (0-100)
        """
        if len(prices) < period + 1:
            return 50  # Neutral default
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def find_support_resistance(
        self,
        candles: List[Candle],
        num_levels: int = 3
    ) -> Tuple[List[float], List[float]]:
        """
        Find support and resistance levels from price action.
        
        Args:
            candles: List of candles
            num_levels: Number of levels to find
        
        Returns:
            Tuple of (support_levels, resistance_levels)
        """
        if len(candles) < 10:
            return [], []
        
        # Find swing highs and lows
        highs = []
        lows = []
        
        for i in range(2, len(candles) - 2):
            # Swing high: higher than 2 candles on each side
            if (candles[i].high > candles[i-1].high and 
                candles[i].high > candles[i-2].high and
                candles[i].high > candles[i+1].high and 
                candles[i].high > candles[i+2].high):
                highs.append(candles[i].high)
            
            # Swing low: lower than 2 candles on each side
            if (candles[i].low < candles[i-1].low and 
                candles[i].low < candles[i-2].low and
                candles[i].low < candles[i+1].low and 
                candles[i].low < candles[i+2].low):
                lows.append(candles[i].low)
        
        # Current price for filtering
        current = candles[-1].close
        
        # Filter and sort
        support = sorted([l for l in lows if l < current], reverse=True)[:num_levels]
        resistance = sorted([h for h in highs if h > current])[:num_levels]
        
        return support, resistance
    
    def detect_trend(self, candles: List[Candle]) -> Tuple[str, int]:
        """
        Detect trend direction and strength.
        
        Args:
            candles: List of candles
        
        Returns:
            Tuple of (trend_direction, strength_1_to_10)
        """
        if len(candles) < 20:
            return "neutral", 5
        
        closes = [c.close for c in candles]
        
        # Use EMA crossover for trend
        ema_fast = self.calculate_ema(closes, 8)
        ema_slow = self.calculate_ema(closes, 21)
        
        # Calculate price momentum
        recent_change = (closes[-1] - closes[-10]) / closes[-10] * 100
        
        # Determine trend
        if ema_fast > ema_slow * 1.001:
            trend = "bullish"
            strength = min(10, int(5 + recent_change))
        elif ema_fast < ema_slow * 0.999:
            trend = "bearish"
            strength = min(10, int(5 - recent_change))
        else:
            trend = "neutral"
            strength = 5
        
        # Clamp strength
        strength = max(1, min(10, strength))
        
        return trend, strength
    
    def analyze(self, symbol: str, interval: str = "1H") -> TechnicalAnalysis:
        """
        Perform full technical analysis on a symbol.
        
        Args:
            symbol: Trading pair
            interval: Candle interval
        
        Returns:
            TechnicalAnalysis results
        """
        candles = self.market.get_candles(symbol, interval=interval, limit=100)
        
        if not candles:
            logger.warning(f"No candles for {symbol}")
            return TechnicalAnalysis(
                symbol=symbol,
                trend="neutral",
                trend_strength=5,
                rsi=50,
                rsi_signal="neutral",
                ema_fast=0,
                ema_slow=0,
                ema_signal="neutral",
                support_levels=[],
                resistance_levels=[]
            )
        
        closes = [c.close for c in candles]
        
        # Calculate indicators
        rsi = self.calculate_rsi(closes)
        ema_fast = self.calculate_ema(closes, 8)
        ema_slow = self.calculate_ema(closes, 21)
        
        # Determine signals
        rsi_signal = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
        ema_signal = "bullish" if ema_fast > ema_slow else "bearish" if ema_fast < ema_slow else "neutral"
        
        trend, strength = self.detect_trend(candles)
        support, resistance = self.find_support_resistance(candles)
        
        return TechnicalAnalysis(
            symbol=symbol,
            trend=trend,
            trend_strength=strength,
            rsi=rsi,
            rsi_signal=rsi_signal,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            ema_signal=ema_signal,
            support_levels=support,
            resistance_levels=resistance
        )
    
    def get_context_for_ai(self, symbol: str) -> dict:
        """
        Get comprehensive context for AI decision making.
        
        Args:
            symbol: Trading pair
        
        Returns:
            Dict with all relevant market context
        """
        analysis = self.analyze(symbol)
        market_summary = self.market.get_market_summary(symbol)
        
        return {
            **market_summary,
            "technical": {
                "trend": analysis.trend,
                "trend_strength": analysis.trend_strength,
                "rsi": analysis.rsi,
                "rsi_signal": analysis.rsi_signal,
                "ema_signal": analysis.ema_signal,
                "support": analysis.support_levels,
                "resistance": analysis.resistance_levels,
            }
        }
