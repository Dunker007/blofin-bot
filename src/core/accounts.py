"""Multi-account management."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import yaml
import os

from ..core.client import BlofinClient
from ..core.config import Config
from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AccountConfig:
    """Configuration for a single account."""
    name: str
    api_key: str
    api_secret: str
    passphrase: str
    demo_mode: bool = True
    max_leverage: int = 10
    max_position_size: float = 100.0
    daily_loss_limit: float = 5.0
    is_active: bool = True
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "demo_mode": self.demo_mode,
            "max_leverage": self.max_leverage,
            "max_position_size": self.max_position_size,
            "daily_loss_limit": self.daily_loss_limit,
            "is_active": self.is_active,
        }


@dataclass
class AccountBalance:
    """Account balance snapshot."""
    name: str
    equity: float
    available: float
    unrealized_pnl: float
    margin_used: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "equity": self.equity,
            "available": self.available,
            "unrealized_pnl": self.unrealized_pnl,
            "margin_used": self.margin_used,
            "timestamp": self.timestamp.isoformat(),
        }


class AccountManager:
    """
    Manage multiple Blofin accounts.
    
    Usage:
        manager = AccountManager()
        manager.load_accounts("config/accounts.yaml")
        
        # Switch account
        manager.set_active("main")
        
        # Get client for current account
        client = manager.get_client()
        
        # Get all balances
        balances = manager.get_all_balances()
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self._accounts: Dict[str, AccountConfig] = {}
        self._clients: Dict[str, BlofinClient] = {}
        self._current: Optional[str] = None
        
        if config_path:
            self.load_accounts(config_path)
    
    def load_accounts(self, config_path: str) -> None:
        """Load accounts from YAML config file."""
        path = Path(config_path)
        
        if not path.exists():
            logger.warning(f"Accounts config not found: {config_path}")
            self._load_from_env()
            return
        
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)
            
            for name, account_data in data.get("accounts", {}).items():
                # Resolve environment variables
                api_key = self._resolve_env(account_data.get("api_key", ""))
                api_secret = self._resolve_env(account_data.get("api_secret", ""))
                passphrase = self._resolve_env(account_data.get("passphrase", ""))
                
                self._accounts[name] = AccountConfig(
                    name=name,
                    api_key=api_key,
                    api_secret=api_secret,
                    passphrase=passphrase,
                    demo_mode=account_data.get("demo_mode", True),
                    max_leverage=account_data.get("max_leverage", 10),
                    max_position_size=account_data.get("max_position_size", 100.0),
                    daily_loss_limit=account_data.get("daily_loss_limit", 5.0),
                )
            
            # Set default account
            default = data.get("default_account")
            if default and default in self._accounts:
                self._current = default
            elif self._accounts:
                self._current = list(self._accounts.keys())[0]
            
            logger.info(f"Loaded {len(self._accounts)} accounts")
            
        except Exception as e:
            logger.error(f"Failed to load accounts config: {e}")
            self._load_from_env()
    
    def _load_from_env(self) -> None:
        """Load default account from environment variables."""
        api_key = os.getenv("BLOFIN_API_KEY", "")
        api_secret = os.getenv("BLOFIN_API_SECRET", "")
        passphrase = os.getenv("BLOFIN_PASSPHRASE", "")
        
        if api_key:
            self._accounts["default"] = AccountConfig(
                name="default",
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                demo_mode=os.getenv("BLOFIN_DEMO", "true").lower() == "true",
            )
            self._current = "default"
            logger.info("Loaded default account from environment")
    
    def _resolve_env(self, value: str) -> str:
        """Resolve environment variable if value starts with $."""
        if value.startswith("${") and value.endswith("}"):
            env_name = value[2:-1]
            return os.getenv(env_name, "")
        return value
    
    def add_account(self, account: AccountConfig) -> None:
        """Add an account."""
        self._accounts[account.name] = account
        
        if self._current is None:
            self._current = account.name
    
    def remove_account(self, name: str) -> bool:
        """Remove an account."""
        if name in self._accounts:
            del self._accounts[name]
            if name in self._clients:
                del self._clients[name]
            if self._current == name:
                self._current = list(self._accounts.keys())[0] if self._accounts else None
            return True
        return False
    
    def set_active(self, name: str) -> bool:
        """Set the active account."""
        if name in self._accounts:
            self._current = name
            logger.info(f"Switched to account: {name}")
            return True
        return False
    
    def get_active(self) -> Optional[AccountConfig]:
        """Get the active account config."""
        if self._current:
            return self._accounts.get(self._current)
        return None
    
    def get_client(self, name: Optional[str] = None) -> Optional[BlofinClient]:
        """Get BlofinClient for an account."""
        account_name = name or self._current
        
        if not account_name or account_name not in self._accounts:
            return None
        
        # Create client if not exists
        if account_name not in self._clients:
            account = self._accounts[account_name]
            
            self._clients[account_name] = BlofinClient(
                api_key=account.api_key,
                api_secret=account.api_secret,
                passphrase=account.passphrase,
                demo=account.demo_mode,
            )
        
        return self._clients[account_name]
    
    def get_balance(self, name: Optional[str] = None) -> Optional[AccountBalance]:
        """Get balance for an account."""
        client = self.get_client(name)
        account_name = name or self._current
        
        if not client:
            return None
        
        try:
            balance = client.get_balance()
            
            return AccountBalance(
                name=account_name,
                equity=float(balance.get("totalEquity", 0)),
                available=float(balance.get("availableBalance", 0)),
                unrealized_pnl=float(balance.get("unrealizedPnl", 0)),
                margin_used=float(balance.get("marginUsed", 0)),
            )
        except Exception as e:
            logger.error(f"Failed to get balance for {account_name}: {e}")
            return None
    
    def get_all_balances(self) -> List[AccountBalance]:
        """Get balances for all accounts."""
        balances = []
        
        for name in self._accounts:
            balance = self.get_balance(name)
            if balance:
                balances.append(balance)
        
        return balances
    
    def get_total_equity(self) -> float:
        """Get total equity across all accounts."""
        return sum(b.equity for b in self.get_all_balances())
    
    def list_accounts(self) -> List[Dict]:
        """List all accounts (without secrets)."""
        return [
            {
                **account.to_dict(),
                "is_current": name == self._current,
            }
            for name, account in self._accounts.items()
        ]
    
    @property
    def current_name(self) -> Optional[str]:
        """Get name of current account."""
        return self._current
    
    @property
    def account_count(self) -> int:
        """Get number of accounts."""
        return len(self._accounts)
