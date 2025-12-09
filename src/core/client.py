"""Blofin API client with authentication and error handling."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

import requests

from .config import Config
from .exceptions import APIError, AuthenticationError, RateLimitError
from .logger import get_api_logger

logger = get_api_logger()


class BlofinClient:
    """
    Blofin REST API client with HMAC-SHA256 authentication.
    
    Usage:
        config = Config.load()
        client = BlofinClient(config)
        ticker = client.get_ticker("BTC-USDT")
    
    Note: Public market data always uses production API.
          Private/trading endpoints use demo mode when configured.
    """
    
    # Production API for public market data
    PUBLIC_URL = "https://openapi.blofin.com"
    
    def __init__(self, config: Config):
        self.config = config
        self.api = config.api
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
    
    # ==================== Authentication ====================
    
    def _sign(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """
        Generate authentication headers for a request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            body: Request body as JSON string
        
        Returns:
            Dictionary of authentication headers
        """
        timestamp = str(int(time.time() * 1000))
        nonce = timestamp  # Using timestamp as nonce
        
        # Create signature string: path + method + timestamp + nonce + body
        msg = f"{path}{method}{timestamp}{nonce}{body}"
        
        # HMAC-SHA256 signature
        signature = hmac.new(
            self.api.api_secret.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        # Base64 encode the hex signature
        sign = base64.b64encode(signature.encode("utf-8")).decode()
        
        return {
            "ACCESS-KEY": self.api.api_key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-NONCE": nonce,
            "ACCESS-PASSPHRASE": self.api.passphrase,
        }
    
    # ==================== Request Methods ====================
    
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        auth: bool = False
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the Blofin API.
        
        Args:
            method: HTTP method
            path: API endpoint path
            params: Query parameters
            data: Request body data
            auth: Whether to include authentication headers
        
        Returns:
            Parsed JSON response
        
        Raises:
            APIError: If the request fails
        """
        # Use production API for public endpoints, configured URL for private
        base_url = self.api.base_url if auth else self.PUBLIC_URL
        url = f"{base_url}{path}"
        headers = {}
        body = ""
        
        if data:
            body = json.dumps(data)
        
        if auth:
            headers.update(self._sign(method.upper(), path, body))
        
        try:
            logger.debug(f"{method} {path}")
            
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                data=body if body else None,
                headers=headers,
                timeout=30
            )
            
            result = response.json()
            
            # Check for API errors
            if "code" in result and result["code"] != "0":
                self._handle_error(result)
            
            return result
            
        except requests.exceptions.Timeout:
            raise APIError("Request timed out")
        except requests.exceptions.RequestException as e:
            raise APIError(f"Request failed: {e}")
    
    def _handle_error(self, response: Dict) -> None:
        """Handle API error responses."""
        code = response.get("code", "")
        msg = response.get("msg", "Unknown error")
        
        # Authentication errors
        if code in ["50111", "50112", "50113", "50114"]:
            raise AuthenticationError(msg, code, response)
        
        # Rate limit errors
        if code == "50011":
            raise RateLimitError(msg, code, response)
        
        raise APIError(msg, code, response)
    
    def get(self, path: str, params: Optional[Dict] = None, auth: bool = False) -> Dict:
        """GET request."""
        return self._request("GET", path, params=params, auth=auth)
    
    def post(self, path: str, data: Optional[Dict] = None, auth: bool = True) -> Dict:
        """POST request (authenticated by default)."""
        return self._request("POST", path, data=data, auth=auth)
    
    # ==================== Public Endpoints ====================
    
    def get_ticker(self, inst_id: str) -> Dict:
        """
        Get ticker for a single instrument.
        
        Args:
            inst_id: Instrument ID (e.g., "BTC-USDT")
        
        Returns:
            Ticker data
        """
        # Filter from all tickers since single ticker endpoint may not exist
        tickers = self.get_tickers()
        for ticker in tickers:
            if ticker.get("instId") == inst_id:
                return ticker
        return {}
    
    def get_tickers(self) -> list:
        """Get all tickers."""
        result = self.get("/api/v1/market/tickers")
        return result.get("data", [])
    
    def get_orderbook(self, inst_id: str, size: int = 20) -> Dict:
        """
        Get order book depth.
        
        Args:
            inst_id: Instrument ID
            size: Number of levels (max 400)
        
        Returns:
            Order book with bids and asks
        """
        result = self.get("/api/v1/market/books", params={"instId": inst_id, "size": str(size)})
        return result.get("data", [{}])[0] if result.get("data") else {}
    
    def get_candles(self, inst_id: str, bar: str = "1H", limit: int = 100) -> list:
        """
        Get candlestick data.
        
        Args:
            inst_id: Instrument ID
            bar: Candle interval (1m, 5m, 15m, 30m, 1H, 4H, 1D, etc.)
            limit: Number of candles (max 300)
        
        Returns:
            List of candles [ts, open, high, low, close, vol]
        """
        result = self.get(
            "/api/v1/market/candles",
            params={"instId": inst_id, "bar": bar, "limit": str(limit)}
        )
        return result.get("data", [])
    
    def get_funding_rate(self, inst_id: str) -> Dict:
        """Get current funding rate."""
        result = self.get("/api/v1/market/funding-rate", params={"instId": inst_id})
        return result.get("data", [{}])[0] if result.get("data") else {}
    
    def get_instruments(self) -> list:
        """Get all available trading instruments."""
        result = self.get("/api/v1/market/instruments")
        return result.get("data", [])
    
    # ==================== Account Endpoints ====================
    
    def get_balance(self) -> Dict:
        """Get account balance."""
        result = self.get("/api/v1/account/balance", auth=True)
        return result.get("data", {})
    
    def get_futures_balance(self) -> Dict:
        """Get futures account balance."""
        result = self.get("/api/v1/asset/balances", auth=True)
        return result.get("data", [{}])[0] if result.get("data") else {}
    
    def get_positions(self, inst_id: Optional[str] = None) -> list:
        """
        Get open positions.
        
        Args:
            inst_id: Optional instrument ID to filter
        
        Returns:
            List of positions
        """
        params = {}
        if inst_id:
            params["instId"] = inst_id
        result = self.get("/api/v1/account/positions", params=params, auth=True)
        return result.get("data", [])
    
    def get_leverage(self, inst_id: str, margin_mode: str = "cross") -> Dict:
        """Get leverage info for an instrument."""
        result = self.get(
            "/api/v1/account/batch-leverage-info",
            params={"instId": inst_id, "marginMode": margin_mode},
            auth=True
        )
        return result.get("data", [{}])[0] if result.get("data") else {}
    
    # ==================== Trading Endpoints ====================
    
    def place_order(
        self,
        inst_id: str,
        side: str,
        size: str,
        order_type: str = "market",
        price: Optional[str] = None,
        margin_mode: str = "cross",
        leverage: str = "3",
        position_side: str = "net",
        reduce_only: bool = False,
        client_order_id: Optional[str] = None
    ) -> Dict:
        """
        Place an order.
        
        Args:
            inst_id: Instrument ID (e.g., "BTC-USDT")
            side: "buy" or "sell"
            size: Order size in contracts
            order_type: "market", "limit", "post_only", "fok", "ioc"
            price: Limit price (required for limit orders)
            margin_mode: "cross" or "isolated"
            leverage: Leverage multiplier
            position_side: "net", "long", or "short"
            reduce_only: If true, only reduce position
            client_order_id: Optional client-generated order ID
        
        Returns:
            Order response with orderId
        """
        data = {
            "instId": inst_id,
            "marginMode": margin_mode,
            "side": side,
            "orderType": order_type,
            "size": size,
            "leverage": leverage,
            "positionSide": position_side,
        }
        
        if price:
            data["price"] = price
        if reduce_only:
            data["reduceOnly"] = "true"
        if client_order_id:
            data["clientOrderId"] = client_order_id
        
        logger.info(f"Placing {order_type} {side} order: {inst_id} x{size}")
        result = self.post("/api/v1/trade/order", data=data)
        return result.get("data", [{}])[0] if result.get("data") else {}
    
    def cancel_order(self, order_id: str) -> Dict:
        """Cancel an order by ID."""
        logger.info(f"Cancelling order: {order_id}")
        result = self.post("/api/v1/trade/cancel-order", data={"orderId": order_id})
        return result.get("data", [{}])[0] if result.get("data") else {}
    
    def get_open_orders(self, inst_id: Optional[str] = None) -> list:
        """Get open orders."""
        params = {}
        if inst_id:
            params["instId"] = inst_id
        result = self.get("/api/v1/trade/orders-pending", params=params, auth=True)
        return result.get("data", [])
    
    def get_order_history(self, inst_id: Optional[str] = None, limit: int = 50) -> list:
        """Get order history."""
        params = {"limit": str(limit)}
        if inst_id:
            params["instId"] = inst_id
        result = self.get("/api/v1/trade/orders-history", params=params, auth=True)
        return result.get("data", [])
    
    def close_position(self, inst_id: str, margin_mode: str = "cross", position_side: str = "net") -> Dict:
        """Close a position."""
        logger.info(f"Closing position: {inst_id}")
        data = {
            "instId": inst_id,
            "marginMode": margin_mode,
            "positionSide": position_side,
        }
        result = self.post("/api/v1/trade/close-position", data=data)
        return result.get("data", {})
    
    # ==================== Utility Methods ====================
    
    def test_connection(self) -> bool:
        """Test API connection."""
        try:
            ticker = self.get_ticker("BTC-USDT")
            return bool(ticker.get("last"))
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def test_auth(self) -> bool:
        """Test authenticated endpoints."""
        try:
            self.get_balance()
            return True
        except AuthenticationError as e:
            logger.error(f"Auth test failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Auth test error: {e}")
            return False
