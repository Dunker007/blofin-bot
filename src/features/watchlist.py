"""Watchlist and market scanner functionality."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import json
from pathlib import Path

from ..core.client import BlofinClient
from ..data.market import MarketData, Ticker
from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class WatchlistItem:
    """A symbol on the watchlist."""
    symbol: str
    added_at: datetime = field(default_factory=datetime.now)
    notes: str = ""
    alerts: List[Dict] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "added_at": self.added_at.isoformat(),
            "notes": self.notes,
            "alerts": self.alerts,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "WatchlistItem":
        return cls(
            symbol=data["symbol"],
            added_at=datetime.fromisoformat(data.get("added_at", datetime.now().isoformat())),
            notes=data.get("notes", ""),
            alerts=data.get("alerts", []),
            tags=data.get("tags", []),
        )


class Watchlist:
    """
    User watchlist with persistence and live data.
    
    Usage:
        watchlist = Watchlist(market_data)
        watchlist.add("BTC-USDT", notes="Watching for breakout")
        
        # Get with live prices
        items = watchlist.get_with_prices()
    """
    
    def __init__(self, market: MarketData, storage_path: str = "data/watchlist.json"):
        self.market = market
        self.storage_path = Path(storage_path)
        self._items: Dict[str, WatchlistItem] = {}
        self._load()
    
    def add(self, symbol: str, notes: str = "", tags: Optional[List[str]] = None) -> WatchlistItem:
        """Add symbol to watchlist."""
        if symbol in self._items:
            # Update existing
            self._items[symbol].notes = notes
            if tags:
                self._items[symbol].tags = tags
        else:
            self._items[symbol] = WatchlistItem(
                symbol=symbol,
                notes=notes,
                tags=tags or []
            )
        
        self._save()
        logger.info(f"Added to watchlist: {symbol}")
        return self._items[symbol]
    
    def remove(self, symbol: str) -> bool:
        """Remove symbol from watchlist."""
        if symbol in self._items:
            del self._items[symbol]
            self._save()
            logger.info(f"Removed from watchlist: {symbol}")
            return True
        return False
    
    def get(self, symbol: str) -> Optional[WatchlistItem]:
        """Get a watchlist item."""
        return self._items.get(symbol)
    
    def get_all(self) -> List[WatchlistItem]:
        """Get all watchlist items."""
        return list(self._items.values())
    
    def get_symbols(self) -> List[str]:
        """Get all symbols."""
        return list(self._items.keys())
    
    def get_with_prices(self) -> List[Dict]:
        """Get watchlist items with current prices."""
        symbols = self.get_symbols()
        if not symbols:
            return []
        
        tickers = self.market.get_tickers(symbols)
        ticker_map = {t.symbol: t for t in tickers}
        
        result = []
        for item in self._items.values():
            ticker = ticker_map.get(item.symbol)
            result.append({
                "symbol": item.symbol,
                "notes": item.notes,
                "tags": item.tags,
                "price": ticker.last if ticker else None,
                "change_24h": ticker.change_24h if ticker else None,
                "high_24h": ticker.high_24h if ticker else None,
                "low_24h": ticker.low_24h if ticker else None,
            })
        
        return result
    
    def set_alert(self, symbol: str, condition: str, price: float) -> bool:
        """
        Set a price alert.
        
        Args:
            symbol: Trading pair
            condition: "above" or "below"
            price: Alert trigger price
        """
        if symbol not in self._items:
            return False
        
        self._items[symbol].alerts.append({
            "condition": condition,
            "price": price,
            "created_at": datetime.now().isoformat(),
            "triggered": False,
        })
        
        self._save()
        return True
    
    def check_alerts(self) -> List[Dict]:
        """Check and return triggered alerts."""
        triggered = []
        symbols = self.get_symbols()
        
        if not symbols:
            return triggered
        
        tickers = self.market.get_tickers(symbols)
        ticker_map = {t.symbol: t for t in tickers}
        
        for item in self._items.values():
            ticker = ticker_map.get(item.symbol)
            if not ticker:
                continue
            
            for alert in item.alerts:
                if alert.get("triggered"):
                    continue
                
                condition = alert.get("condition")
                target = alert.get("price")
                
                if condition == "above" and ticker.last >= target:
                    alert["triggered"] = True
                    triggered.append({
                        "symbol": item.symbol,
                        "condition": condition,
                        "target": target,
                        "current": ticker.last,
                    })
                elif condition == "below" and ticker.last <= target:
                    alert["triggered"] = True
                    triggered.append({
                        "symbol": item.symbol,
                        "condition": condition,
                        "target": target,
                        "current": ticker.last,
                    })
        
        if triggered:
            self._save()
        
        return triggered
    
    def clear_alerts(self, symbol: str) -> None:
        """Clear all alerts for a symbol."""
        if symbol in self._items:
            self._items[symbol].alerts = []
            self._save()
    
    def _load(self) -> None:
        """Load watchlist from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                
                for item_data in data.get("items", []):
                    item = WatchlistItem.from_dict(item_data)
                    self._items[item.symbol] = item
                
                logger.info(f"Loaded {len(self._items)} watchlist items")
            except Exception as e:
                logger.error(f"Failed to load watchlist: {e}")
    
    def _save(self) -> None:
        """Save watchlist to storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "items": [item.to_dict() for item in self._items.values()],
            "updated_at": datetime.now().isoformat(),
        }
        
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)


class MarketScanner:
    """
    Scan market for opportunities.
    
    Usage:
        scanner = MarketScanner(market)
        
        movers = scanner.get_top_movers()
        funding = scanner.get_funding_opportunities()
    """
    
    def __init__(self, market: MarketData):
        self.market = market
    
    def get_top_movers(self, limit: int = 10) -> List[Dict]:
        """Get top gaining and losing symbols."""
        tickers = self.market.get_tickers()
        
        # Filter valid tickers with change data
        valid = [t for t in tickers if t.change_24h is not None]
        
        # Sort by absolute change
        sorted_tickers = sorted(valid, key=lambda t: abs(t.change_24h), reverse=True)
        
        return [
            {
                "symbol": t.symbol,
                "price": t.last,
                "change_24h": t.change_24h,
                "direction": "up" if t.change_24h > 0 else "down",
            }
            for t in sorted_tickers[:limit]
        ]
    
    def get_gainers(self, limit: int = 5) -> List[Dict]:
        """Get top gaining symbols."""
        tickers = self.market.get_tickers()
        valid = [t for t in tickers if t.change_24h is not None and t.change_24h > 0]
        sorted_tickers = sorted(valid, key=lambda t: t.change_24h, reverse=True)
        
        return [
            {"symbol": t.symbol, "price": t.last, "change_24h": t.change_24h}
            for t in sorted_tickers[:limit]
        ]
    
    def get_losers(self, limit: int = 5) -> List[Dict]:
        """Get top losing symbols."""
        tickers = self.market.get_tickers()
        valid = [t for t in tickers if t.change_24h is not None and t.change_24h < 0]
        sorted_tickers = sorted(valid, key=lambda t: t.change_24h)
        
        return [
            {"symbol": t.symbol, "price": t.last, "change_24h": t.change_24h}
            for t in sorted_tickers[:limit]
        ]
    
    def get_funding_opportunities(self, threshold: float = 0.05) -> List[Dict]:
        """
        Find symbols with extreme funding rates.
        High positive = potential short opportunity
        High negative = potential long opportunity
        """
        # Get all symbols from tickers
        tickers = self.market.get_tickers()
        opportunities = []
        
        for ticker in tickers[:20]:  # Limit API calls
            try:
                funding = self.market.get_funding_rate(ticker.symbol)
                rate = funding.current
                
                if abs(rate) >= threshold:
                    opportunities.append({
                        "symbol": ticker.symbol,
                        "funding_rate": rate,
                        "direction": "short" if rate > 0 else "long",
                        "next_funding": funding.next_time.isoformat() if funding.next_time else None,
                    })
            except:
                continue
        
        return sorted(opportunities, key=lambda x: abs(x["funding_rate"]), reverse=True)
