"""Technical indicators for strategy development."""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import statistics


@dataclass
class IndicatorResult:
    """Result from an indicator calculation."""
    value: float
    signal: str = "neutral"  # bullish, bearish, neutral
    strength: float = 0.5  # 0-1


class Indicators:
    """
    Technical indicator calculations.
    
    All methods are static and work on lists of prices/candles.
    
    Usage:
        closes = [100, 102, 101, 103, 105]
        rsi = Indicators.rsi(closes, 14)
        ema = Indicators.ema(closes, 20)
    """
    
    @staticmethod
    def sma(prices: List[float], period: int) -> Optional[float]:
        """Simple Moving Average."""
        if len(prices) < period:
            return None
        return statistics.mean(prices[-period:])
    
    @staticmethod
    def ema(prices: List[float], period: int) -> Optional[float]:
        """Exponential Moving Average."""
        if len(prices) < period:
            return None
        
        multiplier = 2 / (period + 1)
        ema = statistics.mean(prices[:period])  # Start with SMA
        
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    @staticmethod
    def ema_series(prices: List[float], period: int) -> List[float]:
        """EMA as a series (for crossovers)."""
        if len(prices) < period:
            return []
        
        multiplier = 2 / (period + 1)
        ema_values = [statistics.mean(prices[:period])]
        
        for price in prices[period:]:
            ema = (price * multiplier) + (ema_values[-1] * (1 - multiplier))
            ema_values.append(ema)
        
        return ema_values
    
    @staticmethod
    def rsi(prices: List[float], period: int = 14) -> Optional[IndicatorResult]:
        """
        Relative Strength Index.
        
        Returns RSI value (0-100) and signal.
        """
        if len(prices) < period + 1:
            return None
        
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        gains = [c if c > 0 else 0 for c in changes[-period:]]
        losses = [-c if c < 0 else 0 for c in changes[-period:]]
        
        avg_gain = statistics.mean(gains) if gains else 0
        avg_loss = statistics.mean(losses) if losses else 0
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        # Determine signal
        if rsi < 30:
            signal = "oversold"
            strength = (30 - rsi) / 30
        elif rsi > 70:
            signal = "overbought"
            strength = (rsi - 70) / 30
        else:
            signal = "neutral"
            strength = 0.5
        
        return IndicatorResult(value=rsi, signal=signal, strength=min(strength, 1.0))
    
    @staticmethod
    def macd(
        prices: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Optional[dict]:
        """
        MACD (Moving Average Convergence Divergence).
        
        Returns dict with macd_line, signal_line, histogram.
        """
        if len(prices) < slow + signal:
            return None
        
        fast_ema = Indicators.ema_series(prices, fast)
        slow_ema = Indicators.ema_series(prices, slow)
        
        # Align the series
        offset = slow - fast
        macd_line = [
            fast_ema[i + offset] - slow_ema[i] 
            for i in range(len(slow_ema))
        ]
        
        if len(macd_line) < signal:
            return None
        
        signal_line = Indicators.ema_series(macd_line, signal)
        
        # Histogram
        offset = len(macd_line) - len(signal_line)
        histogram = [
            macd_line[i + offset] - signal_line[i]
            for i in range(len(signal_line))
        ]
        
        return {
            "macd": macd_line[-1],
            "signal": signal_line[-1],
            "histogram": histogram[-1],
            "trend": "bullish" if histogram[-1] > 0 else "bearish",
            "crossover": "bullish" if len(histogram) > 1 and histogram[-2] < 0 and histogram[-1] > 0 else
                        "bearish" if len(histogram) > 1 and histogram[-2] > 0 and histogram[-1] < 0 else None
        }
    
    @staticmethod
    def bollinger_bands(
        prices: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Optional[dict]:
        """
        Bollinger Bands.
        
        Returns dict with upper, middle, lower bands and %B.
        """
        if len(prices) < period:
            return None
        
        middle = statistics.mean(prices[-period:])
        stdev = statistics.stdev(prices[-period:])
        
        upper = middle + (std_dev * stdev)
        lower = middle - (std_dev * stdev)
        
        current = prices[-1]
        percent_b = (current - lower) / (upper - lower) if upper != lower else 0.5
        
        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "percent_b": percent_b,
            "bandwidth": (upper - lower) / middle,
            "signal": "oversold" if percent_b < 0 else "overbought" if percent_b > 1 else "neutral"
        }
    
    @staticmethod
    def atr(candles: List[dict], period: int = 14) -> Optional[float]:
        """
        Average True Range (volatility indicator).
        
        Candles need 'high', 'low', 'close' keys.
        """
        if len(candles) < period + 1:
            return None
        
        true_ranges = []
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i-1]["close"]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        return statistics.mean(true_ranges[-period:])
    
    @staticmethod
    def support_resistance(
        candles: List[dict],
        lookback: int = 50,
        threshold: float = 0.02
    ) -> Tuple[List[float], List[float]]:
        """
        Find support and resistance levels.
        
        Returns (support_levels, resistance_levels).
        """
        if len(candles) < lookback:
            lookback = len(candles)
        
        recent = candles[-lookback:]
        highs = [c["high"] for c in recent]
        lows = [c["low"] for c in recent]
        
        # Find local maxima/minima
        resistance = []
        support = []
        
        for i in range(2, len(recent) - 2):
            # Local high
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
               highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                resistance.append(highs[i])
            
            # Local low
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
               lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                support.append(lows[i])
        
        # Cluster nearby levels
        resistance = Indicators._cluster_levels(resistance, threshold)
        support = Indicators._cluster_levels(support, threshold)
        
        return support, resistance
    
    @staticmethod
    def _cluster_levels(levels: List[float], threshold: float) -> List[float]:
        """Cluster nearby price levels."""
        if not levels:
            return []
        
        levels = sorted(levels)
        clustered = [levels[0]]
        
        for level in levels[1:]:
            if (level - clustered[-1]) / clustered[-1] > threshold:
                clustered.append(level)
            else:
                # Average with cluster
                clustered[-1] = (clustered[-1] + level) / 2
        
        return clustered
    
    @staticmethod
    def trend_strength(prices: List[float], period: int = 20) -> IndicatorResult:
        """
        Calculate trend direction and strength.
        
        Uses linear regression slope normalized.
        """
        if len(prices) < period:
            period = len(prices)
        
        recent = prices[-period:]
        n = len(recent)
        
        # Simple linear regression
        x_mean = (n - 1) / 2
        y_mean = statistics.mean(recent)
        
        numerator = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        slope = numerator / denominator if denominator != 0 else 0
        
        # Normalize slope by price
        normalized_slope = slope / y_mean * 100  # As percentage per candle
        
        # Determine signal and strength
        if normalized_slope > 0.1:
            signal = "bullish"
            strength = min(normalized_slope / 0.5, 1.0)
        elif normalized_slope < -0.1:
            signal = "bearish"
            strength = min(abs(normalized_slope) / 0.5, 1.0)
        else:
            signal = "neutral"
            strength = 0.5
        
        return IndicatorResult(value=normalized_slope, signal=signal, strength=strength)
    
    @staticmethod
    def volume_profile(candles: List[dict], bins: int = 10) -> List[dict]:
        """
        Volume profile - volume at price levels.
        
        Returns list of {price, volume, percent} dicts.
        """
        if not candles:
            return []
        
        low = min(c["low"] for c in candles)
        high = max(c["high"] for c in candles)
        
        if high == low:
            return [{"price": low, "volume": sum(c.get("volume", 0) for c in candles), "percent": 100}]
        
        bin_size = (high - low) / bins
        profile = [{"price": low + (i + 0.5) * bin_size, "volume": 0} for i in range(bins)]
        
        total_volume = 0
        for candle in candles:
            vol = candle.get("volume", 0)
            avg_price = (candle["high"] + candle["low"]) / 2
            bin_idx = min(int((avg_price - low) / bin_size), bins - 1)
            profile[bin_idx]["volume"] += vol
            total_volume += vol
        
        # Add percentages
        for p in profile:
            p["percent"] = (p["volume"] / total_volume * 100) if total_volume > 0 else 0
        
        return profile
