"""Trading engine - orchestrates all trading components."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple

from ..core.client import BlofinClient
from ..core.config import Config
from ..core.logger import get_trade_logger
from ..data.market import MarketData
from ..data.account import AccountData
from ..ai.brain import AIBrain, AIDecision
from ..human.approval import ApprovalQueue, PendingApproval
from ..human.override import OverrideController
from ..human.limits import SessionLimits
from ..journal.decisions import DecisionJournal
from ..journal.trades import TradeJournal

from .orders import OrderManager, OrderRequest, OrderResult
from .positions import PositionManager
from .risk import RiskManager, RiskCalculation

logger = get_trade_logger()


@dataclass
class TradeExecution:
    """Complete record of a trade execution."""
    decision: AIDecision
    approval: Optional[PendingApproval]
    risk_calc: RiskCalculation
    order_result: OrderResult
    timestamp: datetime


class TradingEngine:
    """
    Main trading engine - orchestrates all components.
    
    Flow for copilot mode:
    1. AI Brain generates decision
    2. Decision goes to approval queue
    3. User approves/rejects
    4. Risk manager validates
    5. Order manager executes
    6. Position manager sets TP/SL
    7. Journal logs everything
    
    Usage:
        engine = TradingEngine(config, client)
        
        # Get AI decision (doesn't execute)
        decision = engine.get_decision("BTC-USDT")
        
        # In copilot mode, user approves
        engine.approve_and_execute(decision.decision_id)
        
        # Or in autonomous mode
        engine.process_signal("BTC-USDT")  # Auto-executes if confident
    """
    
    def __init__(
        self,
        config: Config,
        client: BlofinClient,
        brain: Optional[AIBrain] = None
    ):
        self.config = config
        self.client = client
        
        # Initialize data layers
        self.market = MarketData(client)
        self.account = AccountData(client)
        
        # Initialize AI (optional)
        self.brain = brain or AIBrain(config, self.market, self.account)
        
        # Initialize human controls
        self.approval_queue = ApprovalQueue(
            expiry_minutes=5,
            on_approval=self._on_approval
        )
        self.override = OverrideController(
            client=client,
            on_kill_switch=self._on_kill_switch
        )
        self.limits = SessionLimits(config.autonomy)
        
        # Initialize trading components
        self.orders = OrderManager(client, config, self.override)
        self.positions = PositionManager(client, config, self.account)
        self.risk = RiskManager(config, self.account)
        
        # Initialize journals
        self.decision_journal = DecisionJournal()
        self.trade_journal = TradeJournal()
        
        # Execution history
        self._executions: list = []
    
    # ==================== Decision Flow ====================
    
    def get_decision(self, symbol: str) -> AIDecision:
        """
        Get AI decision for a symbol (doesn't execute).
        
        Args:
            symbol: Trading pair
        
        Returns:
            AIDecision from the brain
        """
        decision = self.brain.get_decision(symbol)
        
        # Log to journal
        self.decision_journal.log_decision(decision)
        
        # Add to approval queue if actionable
        if decision.action in ["long", "short"]:
            self.approval_queue.add(decision)
        
        return decision
    
    def approve_and_execute(
        self,
        decision_id: str,
        modified_params: Optional[Dict] = None
    ) -> Tuple[bool, Optional[TradeExecution]]:
        """
        Approve a decision and execute the trade.
        
        Args:
            decision_id: ID of the pending decision
            modified_params: Optional parameter overrides
        
        Returns:
            (success, TradeExecution or None)
        """
        # Find pending approval
        approval = self.approval_queue.get_by_id(decision_id)
        if not approval:
            logger.warning(f"Decision not found: {decision_id}")
            return False, None
        
        if approval.is_expired:
            logger.warning(f"Decision expired: {decision_id}")
            return False, None
        
        # Approve
        approval.approve()
        
        # Log approval
        self.decision_journal.log_approval(decision_id, "approved")
        
        # Execute
        return self._execute_decision(approval.decision, approval, modified_params)
    
    def reject_decision(self, decision_id: str, reason: str = "") -> bool:
        """Reject a pending decision."""
        approval = self.approval_queue.get_by_id(decision_id)
        if not approval:
            return False
        
        approval.reject(reason)
        self.decision_journal.log_approval(decision_id, "rejected", reason)
        
        return True
    
    def process_signal(self, symbol: str) -> Optional[TradeExecution]:
        """
        Process a trading signal (for autonomous mode).
        
        - Gets AI decision
        - Auto-executes if confidence meets threshold
        - Respects autonomy level and limits
        
        Args:
            symbol: Trading pair
        
        Returns:
            TradeExecution if executed, None otherwise
        """
        autonomy = self.config.autonomy.level
        
        # Get decision
        decision = self.get_decision(symbol)
        
        # Check if we should auto-execute
        if autonomy == "autonomous" or autonomy == "agent":
            if self.brain.should_act(decision, autonomy):
                # Check limits
                if not self.limits.can_trade():
                    logger.info(f"Limits prevent trade: {self.limits.block_reason}")
                    return None
                
                # Auto-execute
                success, execution = self._execute_decision(decision, None, None)
                return execution if success else None
        
        return None
    
    # ==================== Execution ====================
    
    def _execute_decision(
        self,
        decision: AIDecision,
        approval: Optional[PendingApproval],
        modified_params: Optional[Dict]
    ) -> Tuple[bool, Optional[TradeExecution]]:
        """Execute an approved decision."""
        
        # Check override status
        if not self.override.can_trade():
            logger.warning("Trading blocked by override")
            return False, None
        
        # Check session limits
        if not self.limits.can_trade():
            logger.warning(f"Trading blocked: {self.limits.block_reason}")
            return False, None
        
        # Determine parameters
        entry = modified_params.get("entry", decision.entry) if modified_params else decision.entry
        stop_loss = modified_params.get("stop_loss", decision.stop_loss) if modified_params else decision.stop_loss
        take_profit = modified_params.get("take_profit", decision.take_profit) if modified_params else decision.take_profit
        
        # Calculate position size
        if not entry or not stop_loss:
            logger.error("Entry and stop loss required for execution")
            return False, None
        
        risk_calc = self.risk.calculate_position_size(
            symbol=decision.symbol,
            entry=entry,
            stop_loss=stop_loss,
            risk_percent=1.0  # Default 1% risk
        )
        
        if not risk_calc.is_valid:
            logger.warning(f"Risk validation failed: {risk_calc.rejection_reason}")
            self.decision_journal.log_approval(
                decision.decision_id, "rejected", 
                f"Risk: {risk_calc.rejection_reason}"
            )
            return False, None
        
        # Build order
        side = "buy" if decision.action == "long" else "sell"
        
        order = OrderRequest(
            symbol=decision.symbol,
            side=side,
            size=risk_calc.position_size,
            order_type="market",  # Market for now
            leverage=risk_calc.leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            decision_id=decision.decision_id
        )
        
        # Execute
        result = self.orders.place_order(order)
        
        if result.success:
            # Log execution
            self.decision_journal.log_execution(
                decision.decision_id,
                order_id=result.order_id,
                fill_price=result.fill_price or entry,
                fill_size=result.fill_size or risk_calc.position_size
            )
            
            # Set TP/SL
            if stop_loss or take_profit:
                self.positions.set_tpsl(decision.symbol, stop_loss, take_profit)
            
            logger.info(f"Trade executed: {decision.symbol} {decision.action} x{risk_calc.position_size}")
        else:
            logger.error(f"Trade failed: {result.error}")
        
        execution = TradeExecution(
            decision=decision,
            approval=approval,
            risk_calc=risk_calc,
            order_result=result,
            timestamp=datetime.now()
        )
        
        self._executions.append(execution)
        
        return result.success, execution
    
    # ==================== Manual Trading ====================
    
    def quick_trade(
        self,
        symbol: str,
        side: str,
        size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> OrderResult:
        """
        Quick manual trade without AI decision.
        
        Args:
            symbol: Trading pair
            side: "long" or "short"
            size: Position size
            stop_loss: Optional SL
            take_profit: Optional TP
        
        Returns:
            OrderResult
        """
        order_side = "buy" if side == "long" else "sell"
        
        result = self.orders.place_market_order(
            symbol=symbol,
            side=order_side,
            size=size,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        if result.success and (stop_loss or take_profit):
            self.positions.set_tpsl(symbol, stop_loss, take_profit)
        
        return result
    
    # ==================== Position Management ====================
    
    def close_position(self, symbol: str) -> bool:
        """Close a specific position."""
        success, _ = self.positions.close_position(symbol)
        return success
    
    def close_all_positions(self) -> int:
        """Close all positions. Returns count closed."""
        results = self.positions.close_all()
        return sum(1 for _, success in results if success)
    
    def set_stop_loss(self, symbol: str, price: float) -> bool:
        """Set stop loss for a position."""
        return self.positions.set_stop_loss(symbol, price)
    
    def move_to_breakeven(self, symbol: str) -> bool:
        """Move stop loss to break even."""
        return self.positions.move_to_breakeven(symbol)
    
    # ==================== Controls ====================
    
    def kill_switch(self) -> Dict:
        """Emergency: Close all, cancel all, pause AI."""
        return self.override.kill_switch().details
    
    def pause(self, reason: str = "") -> None:
        """Pause AI trading."""
        self.override.pause_ai(reason)
    
    def resume(self) -> None:
        """Resume AI trading."""
        self.override.resume_ai()
    
    @property
    def is_paused(self) -> bool:
        """Check if trading is paused."""
        return self.override.is_ai_paused
    
    # ==================== Status ====================
    
    def get_status(self) -> Dict:
        """Get trading engine status."""
        # Get positions with error handling
        try:
            positions = self.positions.get_position_summary()
        except Exception:
            positions = {"count": 0, "positions": [], "error": "Auth required"}
        
        # Get open orders with error handling
        try:
            open_orders = len(self.orders.get_open_orders())
        except Exception:
            open_orders = 0
        
        return {
            "autonomy_level": self.config.autonomy.level,
            "is_paused": self.is_paused,
            "can_trade": self.override.can_trade() and self.limits.can_trade(),
            "pending_approvals": self.approval_queue.pending_count,
            "session_limits": self.limits.get_stats(),
            "positions": positions,
            "open_orders": open_orders,
        }
    
    def get_pending_approvals(self) -> list:
        """Get pending approvals as dicts."""
        return [a.to_dict() for a in self.approval_queue.get_pending()]
    
    # ==================== Callbacks ====================
    
    def _on_approval(self, approval: PendingApproval) -> None:
        """Called when an approval is approved."""
        logger.info(f"Approval received for {approval.decision.symbol}")
    
    def _on_kill_switch(self) -> None:
        """Called when kill switch is triggered."""
        logger.warning("Kill switch triggered - all trading stopped")
        self.approval_queue.clear()
