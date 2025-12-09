"""Claude AI provider for market analysis and trading decisions."""

import json
from typing import Any, Dict, List, Optional

import anthropic

from ..core.config import AIConfig
from ..core.logger import get_ai_logger

logger = get_ai_logger()


# System prompts
SYSTEM_PROMPT = """You are a crypto futures trading analyst for Blofin exchange.

Your job:
- Analyze market data objectively
- Identify high-probability setups
- Quantify confidence in your analysis
- Explain reasoning clearly

Your rules:
- Never chase moves
- Always define invalidation
- Risk:Reward minimum 1.5:1
- Funding rates matter
- Liquidity matters
- You can say "no trade" - that's often the best trade

You will receive market data in structured format.
Respond with structured decisions."""

ANALYSIS_PROMPT = """Analyze the following market data and provide insights:

{market_data}

Provide your analysis in the following JSON format:
{{
    "trend": "bullish" | "bearish" | "neutral",
    "trend_strength": 1-10,
    "key_levels": {{
        "support": [list of support levels],
        "resistance": [list of resistance levels]
    }},
    "signals": [list of notable signals or patterns],
    "sentiment": "bullish" | "bearish" | "neutral",
    "summary": "Brief summary of market conditions"
}}"""

DECISION_PROMPT = """Given the market context, decide on a trade:

{context}

Current positions: {positions}
Account balance: ${balance:.2f}
Risk per trade: {risk_percent}%

Respond in JSON format:
{{
    "action": "long" | "short" | "close" | "wait",
    "confidence": 0-100,
    "entry": price or null,
    "stop_loss": price (required if action is long/short),
    "take_profit": price or null,
    "size_percent": 1-10 (percent of account),
    "reasoning": "2-3 sentences explaining the decision",
    "invalidation": "what would invalidate this trade idea"
}}

If confidence < 60, action MUST be "wait".
If no clear edge, say so."""


class ClaudeProvider:
    """
    Claude API provider for AI analysis and decisions.
    
    Usage:
        config = AIConfig(api_key="...")
        provider = ClaudeProvider(config)
        
        analysis = provider.analyze_market(market_data)
        decision = provider.get_trade_decision(context)
    """
    
    def __init__(self, config: AIConfig):
        self.config = config
        self.model = config.model
        
        if not config.api_key:
            logger.warning("Claude API key not configured")
            self.client = None
        else:
            self.client = anthropic.Anthropic(api_key=config.api_key)
    
    def _call(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024
    ) -> str:
        """
        Make a call to Claude API.
        
        Args:
            prompt: User prompt
            system: Optional system prompt override
            max_tokens: Maximum tokens in response
        
        Returns:
            Response text
        """
        if not self.client:
            logger.error("Claude client not initialized")
            return "{}"
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system or SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            response = message.content[0].text
            logger.debug(f"Claude response: {response[:200]}...")
            return response
            
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return "{}"
        except Exception as e:
            logger.error(f"Claude call failed: {e}")
            return "{}"
    
    def _parse_json(self, response: str) -> Dict[str, Any]:
        """Parse JSON from response, handling markdown code blocks."""
        # Strip markdown code blocks if present
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return {}
    
    def analyze_market(self, market_data: Dict) -> Dict[str, Any]:
        """
        Analyze market data and return insights.
        
        Args:
            market_data: Dict with price_action, funding, orderbook data
        
        Returns:
            Analysis dict with trend, levels, signals, sentiment
        """
        prompt = ANALYSIS_PROMPT.format(market_data=json.dumps(market_data, indent=2))
        response = self._call(prompt)
        
        analysis = self._parse_json(response)
        
        # Add defaults if parsing failed
        if not analysis:
            analysis = {
                "trend": "neutral",
                "trend_strength": 5,
                "key_levels": {"support": [], "resistance": []},
                "signals": [],
                "sentiment": "neutral",
                "summary": "Unable to analyze - using defaults"
            }
        
        return analysis
    
    def get_trade_decision(
        self,
        context: Dict,
        positions: List[Dict],
        balance: float,
        risk_percent: float = 1.0
    ) -> Dict[str, Any]:
        """
        Get a trade decision based on market context.
        
        Args:
            context: Market context from MarketData.get_market_summary()
            positions: Current open positions
            balance: Account balance
            risk_percent: Risk per trade as percentage
        
        Returns:
            Decision dict with action, confidence, entry, stops, reasoning
        """
        prompt = DECISION_PROMPT.format(
            context=json.dumps(context, indent=2),
            positions=json.dumps(positions, indent=2) if positions else "None",
            balance=balance,
            risk_percent=risk_percent
        )
        
        response = self._call(prompt)
        decision = self._parse_json(response)
        
        # Validate and add defaults
        if not decision or "action" not in decision:
            decision = {
                "action": "wait",
                "confidence": 0,
                "entry": None,
                "stop_loss": None,
                "take_profit": None,
                "size_percent": 0,
                "reasoning": "Unable to analyze - defaulting to wait",
                "invalidation": "N/A"
            }
        
        # Enforce confidence threshold
        if decision.get("confidence", 0) < self.config.minimum_to_suggest * 100:
            decision["action"] = "wait"
        
        return decision
    
    def chat(self, message: str, context: Optional[str] = None) -> str:
        """
        Chat with the AI about trading.
        
        Args:
            message: User message
            context: Optional market context
        
        Returns:
            AI response
        """
        if context:
            prompt = f"Current market context:\n{context}\n\nUser question: {message}"
        else:
            prompt = message
        
        return self._call(prompt)
    
    def explain_position(self, position: Dict, market_data: Dict) -> str:
        """
        Get AI explanation of a position.
        
        Args:
            position: Current position data
            market_data: Current market data
        
        Returns:
            Explanation string
        """
        prompt = f"""Explain this position and provide actionable advice:

Position:
{json.dumps(position, indent=2)}

Current Market:
{json.dumps(market_data, indent=2)}

Provide:
1. Current status assessment
2. Key levels to watch
3. Suggested actions (hold, add, reduce, close)
4. Risk considerations"""
        
        return self._call(prompt)
