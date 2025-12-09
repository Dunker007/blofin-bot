"""AI Brain - Central coordinator for AI analysis and decisions."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import json

from ..core.config import Config
from ..core.logger import get_ai_logger
from ..data.market import MarketData
from ..data.account import AccountData
from ..providers.claude import ClaudeProvider
from .analyzer import MarketAnalyzer

logger = get_ai_logger()


@dataclass
class AIDecision:
    """Structured AI trading decision."""
    decision_id: str
    timestamp: datetime
    symbol: str
    action: str  # long, short, close, wait
    confidence: float  # 0-100
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    size_percent: float = 0
    reasoning: str = ""
    invalidation: str = ""
    market_context: Dict = field(default_factory=dict)
    
    @property
    def risk_reward(self) -> Optional[float]:
        """Calculate risk/reward ratio."""
        if not self.entry or not self.stop_loss or not self.take_profit:
            return None
        
        risk = abs(self.entry - self.stop_loss)
        reward = abs(self.take_profit - self.entry)
        
        if risk == 0:
            return None
        
        return reward / risk
    
    @property
    def should_execute(self) -> bool:
        """Whether this decision meets execution thresholds."""
        return self.action in ["long", "short"] and self.confidence >= 75
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "action": self.action,
            "confidence": self.confidence,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "size_percent": self.size_percent,
            "reasoning": self.reasoning,
            "invalidation": self.invalidation,
            "risk_reward": self.risk_reward,
        }


class AIBrain:
    """
    Central AI coordinator for market analysis and trading decisions.
    
    Usage:
        config = Config.load()
        brain = AIBrain(config, client)
        
        # Get market analysis
        analysis = brain.analyze_market("BTC-USDT")
        
        # Get trade decision
        decision = brain.get_decision("BTC-USDT")
        
        # Chat about trading
        response = brain.chat("Should I go long here?")
    """
    
    def __init__(
        self,
        config: Config,
        market: MarketData,
        account: AccountData
    ):
        self.config = config
        self.market = market
        self.account = account
        
        # Initialize components
        self.provider = ClaudeProvider(config.ai)
        self.analyzer = MarketAnalyzer(market)
        
        # Decision history
        self.decisions: List[AIDecision] = []
        self._decision_counter = 0
    
    def _generate_decision_id(self) -> str:
        """Generate unique decision ID."""
        self._decision_counter += 1
        return f"dec_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._decision_counter}"
    
    def analyze_market(self, symbol: str) -> Dict[str, Any]:
        """
        Get comprehensive market analysis.
        
        Args:
            symbol: Trading pair
        
        Returns:
            Dict with technical and AI analysis
        """
        # Get technical analysis
        technical = self.analyzer.analyze(symbol)
        
        # Get market data
        context = self.analyzer.get_context_for_ai(symbol)
        
        # Get AI analysis
        ai_analysis = self.provider.analyze_market(context)
        
        return {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "technical": {
                "trend": technical.trend,
                "trend_strength": technical.trend_strength,
                "rsi": technical.rsi,
                "rsi_signal": technical.rsi_signal,
                "ema_signal": technical.ema_signal,
                "support": technical.support_levels,
                "resistance": technical.resistance_levels,
            },
            "ai_analysis": ai_analysis,
            "price": context.get("price_action", {}).get("current"),
            "funding": context.get("funding", {}),
        }
    
    def get_decision(self, symbol: str) -> AIDecision:
        """
        Get AI trade decision for a symbol.
        
        Args:
            symbol: Trading pair
        
        Returns:
            AIDecision with action, confidence, and parameters
        """
        # Gather context
        context = self.analyzer.get_context_for_ai(symbol)
        
        # Get current positions and balance
        account_summary = self.account.get_account_summary()
        positions = account_summary.get("positions", [])
        balance = account_summary.get("balance", {}).get("available", 0)
        
        # Get AI decision
        raw_decision = self.provider.get_trade_decision(
            context=context,
            positions=positions,
            balance=balance,
            risk_percent=1.0  # Default 1% risk per trade
        )
        
        # Create structured decision
        decision = AIDecision(
            decision_id=self._generate_decision_id(),
            timestamp=datetime.now(),
            symbol=symbol,
            action=raw_decision.get("action", "wait"),
            confidence=raw_decision.get("confidence", 0),
            entry=raw_decision.get("entry"),
            stop_loss=raw_decision.get("stop_loss"),
            take_profit=raw_decision.get("take_profit"),
            size_percent=raw_decision.get("size_percent", 0),
            reasoning=raw_decision.get("reasoning", ""),
            invalidation=raw_decision.get("invalidation", ""),
            market_context=context
        )
        
        # Log decision
        self.decisions.append(decision)
        logger.info(f"Decision {decision.decision_id}: {decision.action} {symbol} @ {decision.confidence}% confidence")
        
        return decision
    
    def chat(self, message: str, portfolio_context: Optional[str] = None) -> str:
        """
        Chat with the AI about trading.
        
        Args:
            message: User message
            portfolio_context: Pre-built portfolio context string (positions, etc.)
        
        Returns:
            AI response
        """
        return self.provider.chat(message, portfolio_context)
    
    def explain_position(self, symbol: str) -> str:
        """
        Get AI explanation of a current position.
        
        Args:
            symbol: Trading pair with position
        
        Returns:
            Explanation and advice
        """
        position = self.account.get_position(symbol)
        if not position:
            return f"No open position for {symbol}"
        
        # Get position as dict
        pos_dict = {
            "symbol": position.symbol,
            "side": position.side.value,
            "size": position.size,
            "entry": position.avg_price,
            "current": position.mark_price,
            "pnl": position.unrealized_pnl,
            "pnl_percent": position.pnl_percent,
            "leverage": position.leverage,
            "liq_distance": position.distance_to_liquidation,
        }
        
        market_data = self.market.get_market_summary(symbol)
        
        return self.provider.explain_position(pos_dict, market_data)
    
    def should_act(self, decision: AIDecision, autonomy_level: str) -> bool:
        """
        Determine if a decision should be acted upon based on autonomy level.
        
        Args:
            decision: The AI decision
            autonomy_level: Current autonomy level
        
        Returns:
            True if action should be taken
        """
        if decision.action == "wait":
            return False
        
        if autonomy_level == "none":
            return False
        
        if autonomy_level == "assistant":
            return False  # Only analysis, no execution
        
        if autonomy_level == "copilot":
            return False  # Requires approval
        
        if autonomy_level in ["autonomous", "agent"]:
            # Check confidence threshold for auto-execution
            return decision.confidence >= self.config.ai.minimum_to_execute * 100
        
        return False
    
    def get_decision_history(self, limit: int = 10) -> List[Dict]:
        """Get recent decisions as dicts."""
        return [d.to_dict() for d in self.decisions[-limit:]]
    
    def get_summary(self, symbols: List[str]) -> str:
        """
        Get AI-generated market summary for multiple symbols.
        
        Args:
            symbols: List of trading pairs
        
        Returns:
            Summary string
        """
        summaries = []
        
        for symbol in symbols:
            try:
                analysis = self.analyze_market(symbol)
                tech = analysis.get("technical", {})
                ai = analysis.get("ai_analysis", {})
                
                summaries.append(
                    f"**{symbol}**: ${analysis.get('price', 0):,.2f}\n"
                    f"  Trend: {tech.get('trend', 'N/A')} (strength {tech.get('trend_strength', 'N/A')}/10)\n"
                    f"  RSI: {tech.get('rsi', 0):.1f} ({tech.get('rsi_signal', 'N/A')})\n"
                    f"  AI: {ai.get('summary', 'N/A')}"
                )
            except Exception as e:
                logger.error(f"Failed to analyze {symbol}: {e}")
                summaries.append(f"**{symbol}**: Analysis failed")
        
        return "\n\n".join(summaries)
