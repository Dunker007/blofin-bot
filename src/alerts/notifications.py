"""Discord and Telegram notification handlers."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from ..core.config import Config
from ..core.logger import get_logger

logger = get_logger(__name__)


class NotificationType(Enum):
    """Types of notifications."""
    TRADE_OPEN = "trade_open"
    TRADE_CLOSE = "trade_close"
    PRICE_ALERT = "price_alert"
    AI_DECISION = "ai_decision"
    ERROR = "error"
    INFO = "info"
    PNL_UPDATE = "pnl_update"


@dataclass
class Notification:
    """A notification to send."""
    type: NotificationType
    title: str
    message: str
    fields: Dict[str, str] = None
    color: str = None  # Hex color for embeds
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.fields is None:
            self.fields = {}
        if self.color is None:
            self.color = self._default_color()
    
    def _default_color(self) -> str:
        """Get default color based on type."""
        colors = {
            NotificationType.TRADE_OPEN: "#3b82f6",  # Blue
            NotificationType.TRADE_CLOSE: "#22c55e",  # Green
            NotificationType.PRICE_ALERT: "#eab308",  # Yellow
            NotificationType.AI_DECISION: "#8b5cf6",  # Purple
            NotificationType.ERROR: "#ef4444",  # Red
            NotificationType.INFO: "#6b7280",  # Gray
            NotificationType.PNL_UPDATE: "#06b6d4",  # Cyan
        }
        return colors.get(self.type, "#6b7280")


class DiscordNotifier:
    """
    Send notifications to Discord via webhooks.
    
    Usage:
        discord = DiscordNotifier(webhook_url)
        discord.send(Notification(
            type=NotificationType.TRADE_OPEN,
            title="New Long Position",
            message="Opening BTC-USDT long",
            fields={"Size": "0.01", "Entry": "$95,000"}
        ))
    """
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)
    
    def send(self, notification: Notification) -> bool:
        """Send notification to Discord."""
        if not self.enabled:
            return False
        
        if not HAS_REQUESTS:
            logger.warning("requests library not installed")
            return False
        
        try:
            # Build embed
            embed = {
                "title": notification.title,
                "description": notification.message,
                "color": int(notification.color.lstrip("#"), 16),
                "timestamp": notification.timestamp.isoformat(),
            }
            
            # Add fields
            if notification.fields:
                embed["fields"] = [
                    {"name": k, "value": str(v), "inline": True}
                    for k, v in notification.fields.items()
                ]
            
            # Send
            payload = {"embeds": [embed]}
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"Discord notification sent: {notification.title}")
                return True
            else:
                logger.error(f"Discord error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Discord send error: {e}")
            return False
    
    def send_trade_open(
        self,
        symbol: str,
        side: str,
        size: float,
        entry: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        """Send trade open notification."""
        emoji = "🟢" if side.lower() == "long" else "🔴"
        
        fields = {
            "Symbol": symbol,
            "Side": f"{emoji} {side.upper()}",
            "Size": str(size),
            "Entry": f"${entry:,.2f}",
        }
        
        if stop_loss:
            fields["Stop Loss"] = f"${stop_loss:,.2f}"
        if take_profit:
            fields["Take Profit"] = f"${take_profit:,.2f}"
        
        return self.send(Notification(
            type=NotificationType.TRADE_OPEN,
            title=f"{emoji} New {side.upper()} Position",
            message=f"Opening {symbol} {side}",
            fields=fields
        ))
    
    def send_trade_close(
        self,
        symbol: str,
        side: str,
        pnl: float,
        pnl_percent: float
    ) -> bool:
        """Send trade close notification."""
        emoji = "✅" if pnl >= 0 else "❌"
        color = "#22c55e" if pnl >= 0 else "#ef4444"
        
        return self.send(Notification(
            type=NotificationType.TRADE_CLOSE,
            title=f"{emoji} Position Closed",
            message=f"Closed {symbol} {side}",
            fields={
                "Symbol": symbol,
                "P&L": f"${pnl:+,.2f}",
                "Return": f"{pnl_percent:+.2f}%",
            },
            color=color
        ))
    
    def send_price_alert(self, symbol: str, price: float, condition: str) -> bool:
        """Send price alert notification."""
        return self.send(Notification(
            type=NotificationType.PRICE_ALERT,
            title="🔔 Price Alert",
            message=f"{symbol} is now {condition}",
            fields={
                "Symbol": symbol,
                "Price": f"${price:,.2f}",
            }
        ))
    
    def send_error(self, title: str, error: str) -> bool:
        """Send error notification."""
        return self.send(Notification(
            type=NotificationType.ERROR,
            title=f"⚠️ {title}",
            message=error
        ))


class TelegramNotifier:
    """
    Send notifications to Telegram via bot API.
    
    Usage:
        telegram = TelegramNotifier(bot_token, chat_id)
        telegram.send(Notification(
            type=NotificationType.TRADE_OPEN,
            title="New Position",
            message="Opening BTC long"
        ))
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send(self, notification: Notification) -> bool:
        """Send notification to Telegram."""
        if not self.enabled:
            return False
        
        if not HAS_REQUESTS:
            logger.warning("requests library not installed")
            return False
        
        try:
            # Build HTML message
            message = f"<b>{notification.title}</b>\n\n"
            message += f"{notification.message}\n"
            
            if notification.fields:
                message += "\n"
                for key, value in notification.fields.items():
                    message += f"<b>{key}:</b> {value}\n"
            
            # Send
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Telegram notification sent: {notification.title}")
                return True
            else:
                logger.error(f"Telegram error: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False
    
    def send_trade_open(
        self,
        symbol: str,
        side: str,
        size: float,
        entry: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        """Send trade open notification."""
        emoji = "🟢" if side.lower() == "long" else "🔴"
        
        fields = {
            "Symbol": symbol,
            "Side": f"{emoji} {side.upper()}",
            "Size": str(size),
            "Entry": f"${entry:,.2f}",
        }
        
        if stop_loss:
            fields["Stop Loss"] = f"${stop_loss:,.2f}"
        if take_profit:
            fields["Take Profit"] = f"${take_profit:,.2f}"
        
        return self.send(Notification(
            type=NotificationType.TRADE_OPEN,
            title=f"{emoji} New {side.upper()} Position",
            message=f"Opening {symbol} {side}",
            fields=fields
        ))
    
    def send_trade_close(
        self,
        symbol: str,
        side: str,
        pnl: float,
        pnl_percent: float
    ) -> bool:
        """Send trade close notification."""
        emoji = "✅" if pnl >= 0 else "❌"
        
        return self.send(Notification(
            type=NotificationType.TRADE_CLOSE,
            title=f"{emoji} Position Closed",
            message=f"Closed {symbol} {side}",
            fields={
                "P&L": f"${pnl:+,.2f}",
                "Return": f"{pnl_percent:+.2f}%",
            }
        ))


class NotificationManager:
    """
    Unified notification manager for multiple channels.
    
    Usage:
        notifier = NotificationManager()
        notifier.add_discord(webhook_url)
        notifier.add_telegram(bot_token, chat_id)
        
        notifier.notify(Notification(...))
    """
    
    def __init__(self):
        self._discord: Optional[DiscordNotifier] = None
        self._telegram: Optional[TelegramNotifier] = None
    
    def add_discord(self, webhook_url: str) -> None:
        """Add Discord notification channel."""
        self._discord = DiscordNotifier(webhook_url)
        logger.info("Discord notifications enabled")
    
    def add_telegram(self, bot_token: str, chat_id: str) -> None:
        """Add Telegram notification channel."""
        self._telegram = TelegramNotifier(bot_token, chat_id)
        logger.info("Telegram notifications enabled")
    
    def notify(self, notification: Notification) -> Dict[str, bool]:
        """Send notification to all channels."""
        results = {}
        
        if self._discord and self._discord.enabled:
            results["discord"] = self._discord.send(notification)
        
        if self._telegram and self._telegram.enabled:
            results["telegram"] = self._telegram.send(notification)
        
        return results
    
    def trade_open(self, symbol: str, side: str, size: float, entry: float, **kwargs) -> None:
        """Send trade open to all channels."""
        if self._discord:
            self._discord.send_trade_open(symbol, side, size, entry, **kwargs)
        if self._telegram:
            self._telegram.send_trade_open(symbol, side, size, entry, **kwargs)
    
    def trade_close(self, symbol: str, side: str, pnl: float, pnl_percent: float) -> None:
        """Send trade close to all channels."""
        if self._discord:
            self._discord.send_trade_close(symbol, side, pnl, pnl_percent)
        if self._telegram:
            self._telegram.send_trade_close(symbol, side, pnl, pnl_percent)
    
    def price_alert(self, symbol: str, price: float, condition: str) -> None:
        """Send price alert to all channels."""
        if self._discord:
            self._discord.send_price_alert(symbol, price, condition)
        # Telegram version similar
    
    def error(self, title: str, error: str) -> None:
        """Send error to all channels."""
        if self._discord:
            self._discord.send_error(title, error)
