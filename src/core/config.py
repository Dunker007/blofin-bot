"""Configuration management with YAML support and environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv

from .exceptions import ConfigError
from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class APIConfig:
    """Blofin API configuration."""
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    demo_mode: bool = True
    
    @property
    def base_url(self) -> str:
        if self.demo_mode:
            return "https://demo-trading-openapi.blofin.com"
        return "https://openapi.blofin.com"
    
    @property
    def ws_public_url(self) -> str:
        if self.demo_mode:
            return "wss://demo-trading-openapi.blofin.com/ws/public"
        return "wss://openapi.blofin.com/ws/public"
    
    @property
    def ws_private_url(self) -> str:
        if self.demo_mode:
            return "wss://demo-trading-openapi.blofin.com/ws/private"
        return "wss://openapi.blofin.com/ws/private"


@dataclass
class AIConfig:
    """AI provider configuration."""
    provider: str = "claude"
    api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    
    # Confidence thresholds
    minimum_to_suggest: float = 0.6
    minimum_to_execute: float = 0.75
    high_confidence: float = 0.85


@dataclass
class AutonomyConfig:
    """Autonomy level settings."""
    level: str = "copilot"  # none | assistant | copilot | autonomous | agent
    
    # Execution rules
    max_positions: int = 3
    max_exposure_percent: float = 30.0
    max_single_position_percent: float = 10.0
    require_stop_loss: bool = True
    max_leverage: int = 10
    
    # Session limits
    max_trades_per_day: int = 10
    max_loss_percent_daily: float = 5.0
    max_loss_streak: int = 3


@dataclass
class TradingPair:
    """Configuration for a single trading pair."""
    symbol: str
    enabled: bool = True
    max_leverage: int = 10
    default_size: float = 0.01
    min_order_size: float = 0.001


@dataclass
class Config:
    """Main configuration container."""
    api: APIConfig = field(default_factory=APIConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    autonomy: AutonomyConfig = field(default_factory=AutonomyConfig)
    pairs: List[TradingPair] = field(default_factory=list)
    
    # Paths
    config_dir: Path = field(default_factory=lambda: Path("config"))
    data_dir: Path = field(default_factory=lambda: Path("data"))
    
    @classmethod
    def load(cls, config_dir: str = "config") -> "Config":
        """
        Load configuration from environment and YAML files.
        
        Args:
            config_dir: Directory containing YAML config files
        
        Returns:
            Populated Config instance
        """
        # Load .env file
        load_dotenv()
        
        config = cls()
        config.config_dir = Path(config_dir)
        
        # API config from environment
        config.api = APIConfig(
            api_key=os.getenv("BLOFIN_API_KEY", ""),
            api_secret=os.getenv("BLOFIN_API_SECRET", ""),
            passphrase=os.getenv("BLOFIN_PASSPHRASE", ""),
            demo_mode=os.getenv("BLOFIN_DEMO", "true").lower() == "true"
        )
        
        # AI config from environment
        config.ai = AIConfig(
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        )
        
        # Load YAML configs if they exist
        config._load_yaml_configs()
        
        logger.info(f"Config loaded - Demo mode: {config.api.demo_mode}, Autonomy: {config.autonomy.level}")
        
        return config
    
    def _load_yaml_configs(self) -> None:
        """Load YAML configuration files."""
        # Autonomy config
        autonomy_file = self.config_dir / "autonomy.yaml"
        if autonomy_file.exists():
            data = self._read_yaml(autonomy_file)
            if "autonomy_level" in data:
                self.autonomy.level = data["autonomy_level"]
            if "execution_rules" in data:
                rules = data["execution_rules"]
                self.autonomy.max_positions = rules.get("max_positions", 3)
                self.autonomy.max_exposure_percent = rules.get("max_exposure_percent", 30.0)
                self.autonomy.max_leverage = rules.get("max_leverage", 10)
        
        # Trading pairs config
        pairs_file = self.config_dir / "pairs.yaml"
        if pairs_file.exists():
            data = self._read_yaml(pairs_file)
            for pair_data in data.get("pairs", []):
                self.pairs.append(TradingPair(**pair_data))
        else:
            # Default pairs
            self.pairs = [
                TradingPair(symbol="BTC-USDT"),
                TradingPair(symbol="ETH-USDT"),
            ]
        
        # AI config
        ai_file = self.config_dir / "ai.yaml"
        if ai_file.exists():
            data = self._read_yaml(ai_file)
            if "confidence_thresholds" in data:
                thresholds = data["confidence_thresholds"]
                self.ai.minimum_to_suggest = thresholds.get("minimum_to_suggest", 0.6)
                self.ai.minimum_to_execute = thresholds.get("minimum_to_execute", 0.75)
    
    def _read_yaml(self, path: Path) -> Dict[str, Any]:
        """Read and parse a YAML file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
            return {}
    
    def validate(self) -> bool:
        """Validate configuration has required values."""
        errors = []
        
        if not self.api.api_key:
            errors.append("BLOFIN_API_KEY not set")
        if not self.api.api_secret:
            errors.append("BLOFIN_API_SECRET not set")
        if not self.api.passphrase:
            errors.append("BLOFIN_PASSPHRASE not set")
        
        if self.autonomy.level not in ["none", "assistant", "copilot", "autonomous", "agent"]:
            errors.append(f"Invalid autonomy level: {self.autonomy.level}")
        
        if errors:
            for error in errors:
                logger.error(f"Config validation: {error}")
            return False
        
        return True
    
    def get_pair(self, symbol: str) -> Optional[TradingPair]:
        """Get configuration for a specific trading pair."""
        for pair in self.pairs:
            if pair.symbol == symbol:
                return pair
        return None
