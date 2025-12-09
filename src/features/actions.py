"""Quick actions for fast trading."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import json
from pathlib import Path

from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class QuickAction:
    """A preset quick action."""
    action_id: str
    name: str
    symbol: str
    side: str  # long/short
    size_percent: float = 1.0  # % of account
    leverage: int = 3
    stop_loss_percent: Optional[float] = None  # % from entry
    take_profit_percent: Optional[float] = None
    hotkey: Optional[str] = None  # e.g., "ctrl+1"
    
    def to_dict(self) -> Dict:
        return {
            "action_id": self.action_id,
            "name": self.name,
            "symbol": self.symbol,
            "side": self.side,
            "size_percent": self.size_percent,
            "leverage": self.leverage,
            "stop_loss_percent": self.stop_loss_percent,
            "take_profit_percent": self.take_profit_percent,
            "hotkey": self.hotkey,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "QuickAction":
        return cls(
            action_id=data["action_id"],
            name=data["name"],
            symbol=data["symbol"],
            side=data["side"],
            size_percent=data.get("size_percent", 1.0),
            leverage=data.get("leverage", 3),
            stop_loss_percent=data.get("stop_loss_percent"),
            take_profit_percent=data.get("take_profit_percent"),
            hotkey=data.get("hotkey"),
        )


# Default quick actions
DEFAULT_ACTIONS = [
    QuickAction(
        action_id="btc_long_small",
        name="🟢 BTC Long (Small)",
        symbol="BTC-USDT",
        side="long",
        size_percent=0.5,
        leverage=3,
        stop_loss_percent=2.0,
        take_profit_percent=4.0,
    ),
    QuickAction(
        action_id="btc_short_small",
        name="🔴 BTC Short (Small)",
        symbol="BTC-USDT",
        side="short",
        size_percent=0.5,
        leverage=3,
        stop_loss_percent=2.0,
        take_profit_percent=4.0,
    ),
    QuickAction(
        action_id="eth_long_small",
        name="🟢 ETH Long (Small)",
        symbol="ETH-USDT",
        side="long",
        size_percent=0.5,
        leverage=3,
        stop_loss_percent=3.0,
        take_profit_percent=6.0,
    ),
    QuickAction(
        action_id="eth_short_small",
        name="🔴 ETH Short (Small)",
        symbol="ETH-USDT",
        side="short",
        size_percent=0.5,
        leverage=3,
        stop_loss_percent=3.0,
        take_profit_percent=6.0,
    ),
]


class QuickActions:
    """
    Quick action presets for fast trading.
    
    Usage:
        actions = QuickActions()
        
        # Get all actions
        all_actions = actions.get_all()
        
        # Add custom action
        actions.add(QuickAction(
            action_id="sol_scalp",
            name="SOL Scalp",
            symbol="SOL-USDT",
            side="long",
            size_percent=1.0,
            leverage=10,
        ))
    """
    
    def __init__(self, storage_path: str = "data/quick_actions.json"):
        self.storage_path = Path(storage_path)
        self._actions: Dict[str, QuickAction] = {}
        self._load()
        
        # Add defaults if empty
        if not self._actions:
            for action in DEFAULT_ACTIONS:
                self._actions[action.action_id] = action
            self._save()
    
    def get(self, action_id: str) -> Optional[QuickAction]:
        """Get a quick action by ID."""
        return self._actions.get(action_id)
    
    def get_all(self) -> List[QuickAction]:
        """Get all quick actions."""
        return list(self._actions.values())
    
    def add(self, action: QuickAction) -> None:
        """Add a quick action."""
        self._actions[action.action_id] = action
        self._save()
    
    def remove(self, action_id: str) -> bool:
        """Remove a quick action."""
        if action_id in self._actions:
            del self._actions[action_id]
            self._save()
            return True
        return False
    
    def update(self, action_id: str, **kwargs) -> Optional[QuickAction]:
        """Update a quick action."""
        if action_id not in self._actions:
            return None
        
        action = self._actions[action_id]
        for key, value in kwargs.items():
            if hasattr(action, key):
                setattr(action, key, value)
        
        self._save()
        return action
    
    def _load(self) -> None:
        """Load actions from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                
                for action_data in data.get("actions", []):
                    action = QuickAction.from_dict(action_data)
                    self._actions[action.action_id] = action
            except Exception as e:
                logger.error(f"Failed to load quick actions: {e}")
    
    def _save(self) -> None:
        """Save actions to storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "actions": [a.to_dict() for a in self._actions.values()],
        }
        
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)
