"""Market data service for price, orderbook, and candles."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from ..core.client import BlofinClient
from ..core.config import Config
from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Ticker:
    """Ticker data for a trading pair."""
    symbol: str
    last: float
    bid: float
    ask: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_24h: float
    timestamp: datetime
    
    @classmethod
    def from_api(cls, data: dict) -> "Ticker":
        """Create Ticker from API response."""
        return cls(
            symbol=data.get("instId", ""),
            last=float(data.get("last", 0)),
            bid=float(data.get("bidPrice", 0)),
            ask=float(data.get("askPrice", 0)),
            high_24h=float(data.get("high24h", 0)),
            low_24h=float(data.get("low24h", 0)),
            volume_24h=float(data.get("volume24h", 0)),
            change_24h=float(data.get("change24h", 0)) * 100,  # Convert to percentage
            timestamp=datetime.now()
        )
    
    @property
    def spread(self) -> float:
        """Bid-ask spread."""
        return self.ask - self.bid
    
    @property
    def spread_pct(self) -> float:
        """Spread as percentage of price."""
        if self.last == 0:
            return 0
        return (self.spread / self.last) * 100


@dataclass
class Candle:
    """OHLCV candlestick data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @classmethod
    def from_api(cls, data: list) -> "Candle":
        """Create Candle from API response [ts, o, h, l, c, vol]."""
        return cls(
            timestamp=datetime.fromtimestamp(int(data[0]) / 1000),
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5]) if len(data) > 5 else 0
        )
    
    @property
    def body(self) -> float:
        """Candle body size."""
        return abs(self.close - self.open)
    
    @property
    def is_bullish(self) -> bool:
        """True if close > open."""
        return self.close >= self.open
    
    @property
    def range(self) -> float:
        """High to low range."""
        return self.high - self.low


@dataclass
class FundingRate:
    """Funding rate data."""
    symbol: str
    current_rate: float
    next_rate: Optional[float]
    next_funding_time: datetime
    
    @classmethod
    def from_api(cls, data: dict) -> "FundingRate":
        """Create FundingRate from API response."""
        next_time = int(data.get("nextFundingTime", 0))
        return cls(
            symbol=data.get("instId", ""),
            current_rate=float(data.get("fundingRate", 0)) * 100,  # Convert to percentage
            next_rate=float(data.get("nextFundingRate", 0)) * 100 if data.get("nextFundingRate") else None,
            next_funding_time=datetime.fromtimestamp(next_time / 1000) if next_time else datetime.now()
        )
    
    @property
    def is_positive(self) -> bool:
        """True if longs pay shorts."""
        return self.current_rate > 0
    
    @property
    def annualized(self) -> float:
        """Annualized funding rate (assuming 3 fundings per day)."""
        return self.current_rate * 3 * 365


@dataclass
class OrderBookLevel:
    """Single level in order book."""
    price: float
    size: float
    
    @property
    def value(self) -> float:
        """Dollar value at this level."""
        return self.price * self.size


@dataclass
class OrderBook:
    """Order book with bids and asks."""
    symbol: str
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    timestamp: datetime
    
    @classmethod
    def from_api(cls, symbol: str, data: dict) -> "OrderBook":
        """Create OrderBook from API response."""
        bids = [
            OrderBookLevel(price=float(b[0]), size=float(b[1]))
            for b in data.get("bids", [])
        ]
        asks = [
            OrderBookLevel(price=float(a[0]), size=float(a[1]))
            for a in data.get("asks", [])
        ]
        return cls(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.now()
        )
    
    @property
    def best_bid(self) -> float:
        """Highest bid price."""
        return self.bids[0].price if self.bids else 0
    
    @property
    def best_ask(self) -> float:
        """Lowest ask price."""
        return self.asks[0].price if self.asks else 0
    
    @property
    def spread(self) -> float:
        """Bid-ask spread."""
        return self.best_ask - self.best_bid
    
    @property
    def mid_price(self) -> float:
        """Mid-point price."""
        return (self.best_bid + self.best_ask) / 2
    
    def bid_depth(self, levels: int = 5) -> float:
        """Total bid depth for top N levels."""
        return sum(b.size for b in self.bids[:levels])
    
    def ask_depth(self, levels: int = 5) -> float:
        """Total ask depth for top N levels."""
        return sum(a.size for a in self.asks[:levels])
    
    @property
    def imbalance(self) -> str:
        """Order book imbalance direction."""
        bid_total = self.bid_depth()
        ask_total = self.ask_depth()
        if bid_total > ask_total * 1.2:
            return "bid_heavy"
        elif ask_total > bid_total * 1.2:
            return "ask_heavy"
        return "balanced"


class MarketData:
    """
    Market data service providing tickers, candles, and orderbooks.
    
    Usage:
        config = Config.load()
        client = BlofinClient(config)
        market = MarketData(client)
        
        ticker = market.get_ticker("BTC-USDT")
        print(f"BTC: ${ticker.last:,.2f} ({ticker.change_24h:+.2f}%)")
    """
    
    def __init__(self, client: BlofinClient):
        self.client = client
        self._ticker_cache: dict = {}
    
    def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker for a symbol."""
        data = self.client.get_ticker(symbol)
        ticker = Ticker.from_api(data)
        self._ticker_cache[symbol] = ticker
        return ticker
    
    def get_tickers(self, symbols: Optional[List[str]] = None) -> List[Ticker]:
        """Get tickers for multiple symbols or all if none specified."""
        all_tickers = self.client.get_tickers()
        tickers = [Ticker.from_api(t) for t in all_tickers]
        
        if symbols:
            tickers = [t for t in tickers if t.symbol in symbols]
        
        for t in tickers:
            self._ticker_cache[t.symbol] = t
        
        return tickers
    
    def get_candles(self, symbol: str, interval: str = "1H", limit: int = 100) -> List[Candle]:
        """
        Get candlestick data.
        
        Args:
            symbol: Trading pair
            interval: Candle interval (1m, 5m, 15m, 30m, 1H, 4H, 1D)
            limit: Number of candles (max 300)
        
        Returns:
            List of candles, oldest first
        """
        data = self.client.get_candles(symbol, bar=interval, limit=limit)
        candles = [Candle.from_api(c) for c in data]
        return sorted(candles, key=lambda c: c.timestamp)
    
    def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate."""
        data = self.client.get_funding_rate(symbol)
        return FundingRate.from_api(data)
    
    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBook:
        """Get order book."""
        data = self.client.get_orderbook(symbol, size=depth)
        return OrderBook.from_api(symbol, data)
    
    def get_price(self, symbol: str) -> float:
        """Quick method to get current price."""
        if symbol in self._ticker_cache:
            cache_age = (datetime.now() - self._ticker_cache[symbol].timestamp).seconds
            if cache_age < 5:
                return self._ticker_cache[symbol].last
        
        ticker = self.get_ticker(symbol)
        return ticker.last
    
    def get_market_summary(self, symbol: str) -> dict:
        """
        Get comprehensive market summary for AI analysis.
        
        Returns:
            Dict with price action, structure, and market data
        """
        ticker = self.get_ticker(symbol)
        funding = self.get_funding_rate(symbol)
        orderbook = self.get_orderbook(symbol, depth=10)
        
        return {
            "symbol": symbol,
            "price_action": {
                "current": ticker.last,
                "bid": ticker.bid,
                "ask": ticker.ask,
                "change_24h": ticker.change_24h,
                "high_24h": ticker.high_24h,
                "low_24h": ticker.low_24h,
            },
            "funding": {
                "current": funding.current_rate,
                "next": funding.next_rate,
                "sentiment": "long_heavy" if funding.is_positive else "short_heavy"
            },
            "orderbook": {
                "spread": orderbook.spread,
                "mid_price": orderbook.mid_price,
                "imbalance": orderbook.imbalance,
                "bid_depth": orderbook.bid_depth(),
                "ask_depth": orderbook.ask_depth(),
            }
        }
