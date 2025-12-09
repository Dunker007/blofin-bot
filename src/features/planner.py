"""Trade planner for planning and paper trading."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import json
from pathlib import Path
import uuid

from ..core.logger import get_logger

logger = get_logger(__name__)


class PlanStatus(Enum):
    """Status of a trade plan."""
    DRAFT = "draft"
    READY = "ready"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class TradePlan:
    """A planned trade before execution."""
    plan_id: str
    symbol: str
    side: str  # long/short
    entry: float
    stop_loss: float
    take_profit: float
    size_percent: float = 1.0
    leverage: int = 3
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    
    @property
    def risk(self) -> float:
        """Risk in price terms."""
        return abs(self.entry - self.stop_loss)
    
    @property
    def reward(self) -> float:
        """Reward in price terms."""
        return abs(self.take_profit - self.entry)
    
    @property
    def risk_reward(self) -> float:
        """Risk:Reward ratio."""
        if self.risk == 0:
            return 0
        return self.reward / self.risk
    
    @property
    def risk_percent(self) -> float:
        """Risk as percentage of entry."""
        return (self.risk / self.entry) * 100
    
    @property
    def reward_percent(self) -> float:
        """Reward as percentage of entry."""
        return (self.reward / self.entry) * 100
    
    def validate(self) -> tuple:
        """Validate the trade plan."""
        errors = []
        
        if self.side == "long":
            if self.stop_loss >= self.entry:
                errors.append("Stop loss must be below entry for longs")
            if self.take_profit <= self.entry:
                errors.append("Take profit must be above entry for longs")
        else:
            if self.stop_loss <= self.entry:
                errors.append("Stop loss must be above entry for shorts")
            if self.take_profit >= self.entry:
                errors.append("Take profit must be below entry for shorts")
        
        if self.risk_reward < 1:
            errors.append(f"R:R ratio {self.risk_reward:.2f} is less than 1:1")
        
        if self.leverage > 20:
            errors.append(f"Leverage {self.leverage}x is very high")
        
        return len(errors) == 0, errors
    
    def to_dict(self) -> Dict:
        return {
            "plan_id": self.plan_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "size_percent": self.size_percent,
            "leverage": self.leverage,
            "notes": self.notes,
            "tags": self.tags,
            "status": self.status.value,
            "risk": self.risk,
            "reward": self.reward,
            "risk_reward": self.risk_reward,
            "risk_percent": self.risk_percent,
            "reward_percent": self.reward_percent,
            "created_at": self.created_at.isoformat(),
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "TradePlan":
        return cls(
            plan_id=data["plan_id"],
            symbol=data["symbol"],
            side=data["side"],
            entry=data["entry"],
            stop_loss=data["stop_loss"],
            take_profit=data["take_profit"],
            size_percent=data.get("size_percent", 1.0),
            leverage=data.get("leverage", 3),
            notes=data.get("notes", ""),
            tags=data.get("tags", []),
            status=PlanStatus(data.get("status", "draft")),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            executed_at=datetime.fromisoformat(data["executed_at"]) if data.get("executed_at") else None,
        )


class TradePlanner:
    """
    Trade planning with R:R calculation and paper mode.
    
    Usage:
        planner = TradePlanner()
        
        # Create a plan
        plan = planner.create_plan(
            symbol="BTC-USDT",
            side="long",
            entry=95000,
            stop_loss=94000,
            take_profit=98000
        )
        
        # Mark as ready
        planner.set_ready(plan.plan_id)
        
        # Execute later
        planner.mark_executed(plan.plan_id)
    """
    
    def __init__(self, storage_path: str = "data/trade_plans.json"):
        self.storage_path = Path(storage_path)
        self._plans: Dict[str, TradePlan] = {}
        self._load()
    
    def create_plan(
        self,
        symbol: str,
        side: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        size_percent: float = 1.0,
        leverage: int = 3,
        notes: str = "",
        tags: Optional[List[str]] = None
    ) -> TradePlan:
        """Create a new trade plan."""
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        
        plan = TradePlan(
            plan_id=plan_id,
            symbol=symbol,
            side=side,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size_percent=size_percent,
            leverage=leverage,
            notes=notes,
            tags=tags or [],
        )
        
        self._plans[plan_id] = plan
        self._save()
        
        logger.info(f"Trade plan created: {plan_id} - {side} {symbol}")
        return plan
    
    def calculate_rr(
        self,
        entry: float,
        stop_loss: float,
        take_profit: float,
        side: str = "long"
    ) -> Dict:
        """
        Calculate R:R without creating a plan.
        
        Returns dict with risk, reward, ratio, and percentages.
        """
        if side == "long":
            risk = entry - stop_loss
            reward = take_profit - entry
        else:
            risk = stop_loss - entry
            reward = entry - take_profit
        
        rr_ratio = reward / risk if risk > 0 else 0
        
        return {
            "risk": abs(risk),
            "reward": abs(reward),
            "risk_reward": rr_ratio,
            "risk_percent": (abs(risk) / entry) * 100,
            "reward_percent": (abs(reward) / entry) * 100,
            "valid": risk > 0 and reward > 0,
        }
    
    def get_plan(self, plan_id: str) -> Optional[TradePlan]:
        """Get a specific plan."""
        return self._plans.get(plan_id)
    
    def get_all_plans(self, status: Optional[PlanStatus] = None) -> List[TradePlan]:
        """Get all plans, optionally filtered by status."""
        plans = list(self._plans.values())
        if status:
            plans = [p for p in plans if p.status == status]
        return sorted(plans, key=lambda p: p.created_at, reverse=True)
    
    def get_ready_plans(self) -> List[TradePlan]:
        """Get plans ready for execution."""
        return self.get_all_plans(PlanStatus.READY)
    
    def set_ready(self, plan_id: str) -> bool:
        """Mark a plan as ready for execution."""
        plan = self._plans.get(plan_id)
        if plan and plan.status == PlanStatus.DRAFT:
            plan.status = PlanStatus.READY
            self._save()
            return True
        return False
    
    def mark_executed(self, plan_id: str) -> bool:
        """Mark a plan as executed."""
        plan = self._plans.get(plan_id)
        if plan:
            plan.status = PlanStatus.EXECUTED
            plan.executed_at = datetime.now()
            self._save()
            return True
        return False
    
    def cancel_plan(self, plan_id: str) -> bool:
        """Cancel a plan."""
        plan = self._plans.get(plan_id)
        if plan and plan.status in [PlanStatus.DRAFT, PlanStatus.READY]:
            plan.status = PlanStatus.CANCELLED
            self._save()
            return True
        return False
    
    def delete_plan(self, plan_id: str) -> bool:
        """Delete a plan entirely."""
        if plan_id in self._plans:
            del self._plans[plan_id]
            self._save()
            return True
        return False
    
    def update_plan(
        self,
        plan_id: str,
        entry: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        notes: Optional[str] = None
    ) -> Optional[TradePlan]:
        """Update a draft plan."""
        plan = self._plans.get(plan_id)
        if not plan or plan.status != PlanStatus.DRAFT:
            return None
        
        if entry is not None:
            plan.entry = entry
        if stop_loss is not None:
            plan.stop_loss = stop_loss
        if take_profit is not None:
            plan.take_profit = take_profit
        if notes is not None:
            plan.notes = notes
        
        self._save()
        return plan
    
    def _load(self) -> None:
        """Load plans from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                
                for plan_data in data.get("plans", []):
                    plan = TradePlan.from_dict(plan_data)
                    self._plans[plan.plan_id] = plan
                
                logger.info(f"Loaded {len(self._plans)} trade plans")
            except Exception as e:
                logger.error(f"Failed to load plans: {e}")
    
    def _save(self) -> None:
        """Save plans to storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "plans": [plan.to_dict() for plan in self._plans.values()],
            "updated_at": datetime.now().isoformat(),
        }
        
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)
