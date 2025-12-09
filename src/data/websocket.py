"""WebSocket manager for real-time data streams."""

import asyncio
import json
import hmac
import base64
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    WebSocketClientProtocol = None

from ..core.config import Config
from ..core.logger import get_logger

logger = get_logger(__name__)


# WebSocket URLs
PUBLIC_WS_URL = "wss://openapi.blofin.com/ws/public"
PRIVATE_WS_URL = "wss://openapi.blofin.com/ws/private"


@dataclass
class TickerUpdate:
    """Real-time ticker update."""
    symbol: str
    last: float
    bid: float
    ask: float
    high_24h: float
    low_24h: float
    volume_24h: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TradeUpdate:
    """Real-time trade update."""
    symbol: str
    price: float
    size: float
    side: str  # buy/sell
    timestamp: datetime


@dataclass
class OrderUpdate:
    """Real-time order status update."""
    order_id: str
    symbol: str
    side: str
    status: str
    filled_size: float
    avg_price: float
    timestamp: datetime


class WebSocketManager:
    """
    Real-time WebSocket data manager.
    
    Handles both public (prices, trades) and private (orders, positions) streams.
    
    Usage:
        ws = WebSocketManager(config)
        
        # Subscribe to tickers
        await ws.subscribe_tickers(["BTC-USDT", "ETH-USDT"])
        
        # Add callback
        ws.on_ticker(lambda t: print(f"{t.symbol}: ${t.last}"))
        
        # Start streaming
        await ws.connect()
    """
    
    def __init__(self, config: Config):
        if not HAS_WEBSOCKETS:
            logger.warning("websockets library not installed. Run: pip install websockets")
        
        self.config = config
        self._public_ws: Optional[WebSocketClientProtocol] = None
        self._private_ws: Optional[WebSocketClientProtocol] = None
        
        self._subscriptions: Dict[str, Set[str]] = {
            "tickers": set(),
            "trades": set(),
            "books": set(),
        }
        
        self._callbacks: Dict[str, List[Callable]] = {
            "ticker": [],
            "trade": [],
            "order": [],
            "position": [],
            "error": [],
        }
        
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
    
    # ==================== Subscription Methods ====================
    
    def subscribe_tickers(self, symbols: List[str]) -> None:
        """Subscribe to ticker updates for symbols."""
        for symbol in symbols:
            self._subscriptions["tickers"].add(symbol)
    
    def subscribe_trades(self, symbols: List[str]) -> None:
        """Subscribe to trade updates for symbols."""
        for symbol in symbols:
            self._subscriptions["trades"].add(symbol)
    
    def subscribe_orderbook(self, symbols: List[str]) -> None:
        """Subscribe to orderbook updates for symbols."""
        for symbol in symbols:
            self._subscriptions["books"].add(symbol)
    
    # ==================== Callback Registration ====================
    
    def on_ticker(self, callback: Callable[[TickerUpdate], None]) -> None:
        """Register ticker update callback."""
        self._callbacks["ticker"].append(callback)
    
    def on_trade(self, callback: Callable[[TradeUpdate], None]) -> None:
        """Register trade update callback."""
        self._callbacks["trade"].append(callback)
    
    def on_order(self, callback: Callable[[OrderUpdate], None]) -> None:
        """Register order update callback."""
        self._callbacks["order"].append(callback)
    
    def on_error(self, callback: Callable[[Exception], None]) -> None:
        """Register error callback."""
        self._callbacks["error"].append(callback)
    
    # ==================== Connection Management ====================
    
    async def connect(self) -> None:
        """Start WebSocket connections."""
        if not HAS_WEBSOCKETS:
            logger.error("Cannot connect: websockets library not installed")
            return
        
        self._running = True
        
        # Start public connection
        asyncio.create_task(self._run_public())
        
        # Start private connection if we have credentials
        if self.config.api_key:
            asyncio.create_task(self._run_private())
    
    async def disconnect(self) -> None:
        """Stop WebSocket connections."""
        self._running = False
        
        if self._public_ws:
            await self._public_ws.close()
        if self._private_ws:
            await self._private_ws.close()
    
    async def _run_public(self) -> None:
        """Run public WebSocket connection with auto-reconnect."""
        while self._running:
            try:
                async with websockets.connect(PUBLIC_WS_URL) as ws:
                    self._public_ws = ws
                    self._reconnect_delay = 1.0
                    logger.info("Public WebSocket connected")
                    
                    # Send subscriptions
                    await self._send_subscriptions(ws)
                    
                    # Handle messages
                    async for message in ws:
                        await self._handle_public_message(message)
                        
            except Exception as e:
                logger.error(f"Public WebSocket error: {e}")
                self._emit_error(e)
                
                if self._running:
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2,
                        self._max_reconnect_delay
                    )
    
    async def _run_private(self) -> None:
        """Run private WebSocket connection with auto-reconnect."""
        while self._running:
            try:
                async with websockets.connect(PRIVATE_WS_URL) as ws:
                    self._private_ws = ws
                    logger.info("Private WebSocket connected")
                    
                    # Authenticate
                    await self._authenticate(ws)
                    
                    # Subscribe to private channels
                    await self._subscribe_private(ws)
                    
                    # Handle messages
                    async for message in ws:
                        await self._handle_private_message(message)
                        
            except Exception as e:
                logger.error(f"Private WebSocket error: {e}")
                self._emit_error(e)
                
                if self._running:
                    await asyncio.sleep(self._reconnect_delay)
    
    async def _send_subscriptions(self, ws: WebSocketClientProtocol) -> None:
        """Send subscription messages."""
        # Ticker subscriptions
        for symbol in self._subscriptions["tickers"]:
            msg = {
                "op": "subscribe",
                "args": [{"channel": "tickers", "instId": symbol}]
            }
            await ws.send(json.dumps(msg))
        
        # Trade subscriptions
        for symbol in self._subscriptions["trades"]:
            msg = {
                "op": "subscribe",
                "args": [{"channel": "trades", "instId": symbol}]
            }
            await ws.send(json.dumps(msg))
        
        # Orderbook subscriptions
        for symbol in self._subscriptions["books"]:
            msg = {
                "op": "subscribe",
                "args": [{"channel": "books5", "instId": symbol}]
            }
            await ws.send(json.dumps(msg))
    
    async def _authenticate(self, ws: WebSocketClientProtocol) -> None:
        """Authenticate private WebSocket."""
        timestamp = str(int(time.time()))
        
        # Create signature
        message = timestamp + "GET" + "/users/self/verify"
        signature = hmac.new(
            self.config.api_secret.encode(),
            message.encode(),
            digestmod="sha256"
        )
        sign = base64.b64encode(signature.digest()).decode()
        
        auth_msg = {
            "op": "login",
            "args": [{
                "apiKey": self.config.api_key,
                "passphrase": self.config.passphrase,
                "timestamp": timestamp,
                "sign": sign
            }]
        }
        
        await ws.send(json.dumps(auth_msg))
        
        # Wait for auth response
        response = await ws.recv()
        data = json.loads(response)
        
        if data.get("event") == "login" and data.get("code") == "0":
            logger.info("Private WebSocket authenticated")
        else:
            raise Exception(f"Auth failed: {data}")
    
    async def _subscribe_private(self, ws: WebSocketClientProtocol) -> None:
        """Subscribe to private channels."""
        # Orders
        await ws.send(json.dumps({
            "op": "subscribe",
            "args": [{"channel": "orders"}]
        }))
        
        # Positions
        await ws.send(json.dumps({
            "op": "subscribe",
            "args": [{"channel": "positions"}]
        }))
    
    async def _handle_public_message(self, message: str) -> None:
        """Handle public WebSocket message."""
        try:
            data = json.loads(message)
            
            # Skip system messages
            if "event" in data:
                return
            
            channel = data.get("arg", {}).get("channel")
            
            if channel == "tickers" and "data" in data:
                for tick in data["data"]:
                    update = TickerUpdate(
                        symbol=tick.get("instId", ""),
                        last=float(tick.get("last", 0)),
                        bid=float(tick.get("bidPx", 0)),
                        ask=float(tick.get("askPx", 0)),
                        high_24h=float(tick.get("high24h", 0)),
                        low_24h=float(tick.get("low24h", 0)),
                        volume_24h=float(tick.get("vol24h", 0)),
                    )
                    self._emit_ticker(update)
            
            elif channel == "trades" and "data" in data:
                for trade in data["data"]:
                    update = TradeUpdate(
                        symbol=trade.get("instId", ""),
                        price=float(trade.get("px", 0)),
                        size=float(trade.get("sz", 0)),
                        side=trade.get("side", ""),
                        timestamp=datetime.now(),
                    )
                    self._emit_trade(update)
                    
        except Exception as e:
            logger.error(f"Error handling public message: {e}")
    
    async def _handle_private_message(self, message: str) -> None:
        """Handle private WebSocket message."""
        try:
            data = json.loads(message)
            
            if "event" in data:
                return
            
            channel = data.get("arg", {}).get("channel")
            
            if channel == "orders" and "data" in data:
                for order in data["data"]:
                    update = OrderUpdate(
                        order_id=order.get("orderId", ""),
                        symbol=order.get("instId", ""),
                        side=order.get("side", ""),
                        status=order.get("state", ""),
                        filled_size=float(order.get("fillSz", 0)),
                        avg_price=float(order.get("avgPx", 0) or 0),
                        timestamp=datetime.now(),
                    )
                    self._emit_order(update)
                    
        except Exception as e:
            logger.error(f"Error handling private message: {e}")
    
    # ==================== Event Emission ====================
    
    def _emit_ticker(self, update: TickerUpdate) -> None:
        """Emit ticker update to callbacks."""
        for callback in self._callbacks["ticker"]:
            try:
                callback(update)
            except Exception as e:
                logger.error(f"Ticker callback error: {e}")
    
    def _emit_trade(self, update: TradeUpdate) -> None:
        """Emit trade update to callbacks."""
        for callback in self._callbacks["trade"]:
            try:
                callback(update)
            except Exception as e:
                logger.error(f"Trade callback error: {e}")
    
    def _emit_order(self, update: OrderUpdate) -> None:
        """Emit order update to callbacks."""
        for callback in self._callbacks["order"]:
            try:
                callback(update)
            except Exception as e:
                logger.error(f"Order callback error: {e}")
    
    def _emit_error(self, error: Exception) -> None:
        """Emit error to callbacks."""
        for callback in self._callbacks["error"]:
            try:
                callback(error)
            except Exception as e:
                logger.error(f"Error callback error: {e}")
