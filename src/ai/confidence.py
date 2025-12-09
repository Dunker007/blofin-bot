"""Confidence scoring for AI trade decisions."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..core.config import Config
from ..core.logger import get_ai_logger

logger = get_ai_logger()


@dataclass
class ConfidenceFactors:
    """Breakdown of confidence score components."""
    trend_alignment: float = 0  # 0-20 points
    technical_signals: float = 0  # 0-20 points
    risk_reward: float = 0  # 0-20 points
    market_conditions: float = 0  # 0-20 points
    ai_conviction: float = 0  # 0-20 points (from LLM)
    
    @property
    def total(self) -> float:
        """Total confidence score (0-100)."""
        return min(100, max(0, 
            self.trend_alignment + 
            self.technical_signals + 
            self.risk_reward + 
            self.market_conditions + 
            self.ai_conviction
        ))
    
    def to_dict(self) -> Dict:
        return {
            "trend_alignment": self.trend_alignment,
            "technical_signals": self.technical_signals,
            "risk_reward": self.risk_reward,
            "market_conditions": self.market_conditions,
            "ai_conviction": self.ai_conviction,
            "total": self.total,
        }


class ConfidenceScorer:
    """
    Calculates confidence scores for trade decisions.
    
    Scoring breakdown (100 points max):
    - Trend Alignment: 0-20 points
    - Technical Signals: 0-20 points  
    - Risk/Reward: 0-20 points
    - Market Conditions: 0-20 points
    - AI Conviction: 0-20 points
    
    Usage:
        scorer = ConfidenceScorer(config)
        
        factors = scorer.calculate(
            action="long",
            technical=analysis,
            market=market_data,
            ai_confidence=78
        )
        
        print(f"Confidence: {factors.total}%")
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.thresholds = config.ai
    
    def calculate(
        self,
        action: str,
        technical: Dict,
        market: Dict,
        ai_confidence: float,
        entry: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> ConfidenceFactors:
        """
        Calculate comprehensive confidence score.
        
        Args:
            action: Trade action (long/short)
            technical: Technical analysis dict
            market: Market data dict
            ai_confidence: Raw AI confidence (0-100)
            entry: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
        
        Returns:
            ConfidenceFactors with breakdown
        """
        factors = ConfidenceFactors()
        
        # 1. Trend Alignment (0-20)
        factors.trend_alignment = self._score_trend_alignment(action, technical)
        
        # 2. Technical Signals (0-20)
        factors.technical_signals = self._score_technical(technical)
        
        # 3. Risk/Reward (0-20)
        if entry and stop_loss and take_profit:
            factors.risk_reward = self._score_risk_reward(
                action, entry, stop_loss, take_profit
            )
        else:
            factors.risk_reward = 10  # Neutral if not specified
        
        # 4. Market Conditions (0-20)
        factors.market_conditions = self._score_market_conditions(market)
        
        # 5. AI Conviction (0-20)
        factors.ai_conviction = self._normalize_ai_confidence(ai_confidence)
        
        logger.debug(f"Confidence factors: {factors.to_dict()}")
        
        return factors
    
    def _score_trend_alignment(self, action: str, technical: Dict) -> float:
        """Score how well trade aligns with trend."""
        trend = technical.get("trend", "neutral")
        trend_strength = technical.get("trend_strength", 5)
        
        # Perfect alignment
        if (action == "long" and trend == "bullish") or \
           (action == "short" and trend == "bearish"):
            # Scale by trend strength (1-10 -> 10-20)
            return 10 + trend_strength
        
        # Counter-trend
        if (action == "long" and trend == "bearish") or \
           (action == "short" and trend == "bullish"):
            # Penalize but allow for reversals
            return max(0, 10 - trend_strength)
        
        # Neutral trend
        return 10
    
    def _score_technical(self, technical: Dict) -> float:
        """Score technical indicator alignment."""
        score = 10  # Start neutral
        
        rsi = technical.get("rsi", 50)
        rsi_signal = technical.get("rsi_signal", "neutral")
        ema_signal = technical.get("ema_signal", "neutral")
        
        # RSI scoring
        if rsi_signal == "oversold":
            score += 5  # Good for longs
        elif rsi_signal == "overbought":
            score += 5  # Good for shorts (depends on action)
        elif 40 <= rsi <= 60:
            score += 3  # Neutral is okay
        
        # EMA alignment
        if ema_signal in ["bullish", "bearish"]:
            score += 5
        
        return min(20, score)
    
    def _score_risk_reward(
        self,
        action: str,
        entry: float,
        stop_loss: float,
        take_profit: float
    ) -> float:
        """Score risk/reward ratio."""
        # Calculate R:R
        if action == "long":
            risk = entry - stop_loss
            reward = take_profit - entry
        else:
            risk = stop_loss - entry
            reward = entry - take_profit
        
        if risk <= 0:
            return 0  # Invalid stop loss
        
        rr_ratio = reward / risk
        
        # Score based on R:R
        if rr_ratio >= 3:
            return 20
        elif rr_ratio >= 2.5:
            return 18
        elif rr_ratio >= 2:
            return 16
        elif rr_ratio >= 1.5:
            return 12
        elif rr_ratio >= 1:
            return 8
        else:
            return max(0, rr_ratio * 5)
    
    def _score_market_conditions(self, market: Dict) -> float:
        """Score overall market conditions."""
        score = 10  # Start neutral
        
        # Funding rate
        funding = market.get("funding", {})
        funding_rate = funding.get("current", 0)
        
        # Extreme funding is a warning sign
        if abs(funding_rate) > 0.1:
            score -= 3
        elif abs(funding_rate) < 0.01:
            score += 2  # Low funding is healthy
        
        # Order book
        orderbook = market.get("orderbook", {})
        imbalance = orderbook.get("imbalance", "balanced")
        
        if imbalance == "balanced":
            score += 3
        elif imbalance in ["bid_heavy", "ask_heavy"]:
            score += 1  # Some support/resistance
        
        # Spread
        spread_pct = orderbook.get("spread", 0) / market.get("price_action", {}).get("current", 1) * 100
        if spread_pct < 0.01:
            score += 5  # Tight spread is good
        elif spread_pct > 0.1:
            score -= 3  # Wide spread is concerning
        
        return max(0, min(20, score))
    
    def _normalize_ai_confidence(self, ai_confidence: float) -> float:
        """Normalize AI confidence to 0-20 scale."""
        # AI gives 0-100, we want 0-20
        return (ai_confidence / 100) * 20
    
    def should_suggest(self, score: float) -> bool:
        """Check if score meets suggestion threshold."""
        return score >= self.thresholds.minimum_to_suggest * 100
    
    def should_auto_execute(self, score: float) -> bool:
        """Check if score meets auto-execution threshold."""
        return score >= self.thresholds.minimum_to_execute * 100
    
    def is_high_confidence(self, score: float) -> bool:
        """Check if this is a high-confidence trade."""
        return score >= self.thresholds.high_confidence * 100
    
    def get_confidence_level(self, score: float) -> str:
        """Get human-readable confidence level."""
        if score >= 85:
            return "Very High"
        elif score >= 75:
            return "High"
        elif score >= 60:
            return "Medium"
        elif score >= 40:
            return "Low"
        else:
            return "Very Low"
