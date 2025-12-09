"""Backtesting engine for strategy testing."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from enum import Enum
import json
from pathlib import Path

from ..core.client import BlofinClient
from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Candle:
    """OHLCV candle data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass
class BacktestTrade:
    """A simulated trade in backtesting."""
    id: int
    symbol: str
    side: str  # long or short
    entry_time: datetime
    entry_price: float
    size: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl: float = 0
    pnl_percent: float = 0
    reason: str = ""
    
    def close(self, price: float, time: datetime, reason: str = "") -> None:
        """Close the trade."""
        self.exit_time = time
        self.exit_price = price
        self.reason = reason
        
        if self.side == "long":
            self.pnl = (price - self.entry_price) * self.size
            self.pnl_percent = ((price / self.entry_price) - 1) * 100
        else:
            self.pnl = (self.entry_price - price) * self.size
            self.pnl_percent = ((self.entry_price / price) - 1) * 100
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": self.entry_price,
            "size": self.size,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_price": self.exit_price,
            "pnl": round(self.pnl, 2),
            "pnl_percent": round(self.pnl_percent, 2),
            "reason": self.reason,
        }


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    symbol: str
    start_date: str
    end_date: str
    initial_balance: float
    final_balance: float
    
    # Trade stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0
    
    # P&L stats
    total_pnl: float = 0
    gross_profit: float = 0
    gross_loss: float = 0
    profit_factor: float = 0
    
    # Average stats
    avg_win: float = 0
    avg_loss: float = 0
    avg_trade: float = 0
    largest_win: float = 0
    largest_loss: float = 0
    
    # Risk stats
    max_drawdown: float = 0
    max_drawdown_percent: float = 0
    sharpe_ratio: float = 0
    
    # Time stats
    avg_hold_time: timedelta = field(default_factory=lambda: timedelta())
    
    # Trade list
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_balance": self.initial_balance,
            "final_balance": round(self.final_balance, 2),
            "total_return": round(((self.final_balance / self.initial_balance) - 1) * 100, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 1),
            "total_pnl": round(self.total_pnl, 2),
            "profit_factor": round(self.profit_factor, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "largest_win": round(self.largest_win, 2),
            "largest_loss": round(self.largest_loss, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_percent": round(self.max_drawdown_percent, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "avg_hold_time": str(self.avg_hold_time),
            "trades": [t.to_dict() for t in self.trades],
        }
    
    def summary(self) -> str:
        """Generate text summary of results."""
        return f"""
╔══════════════════════════════════════════════════════════════╗
║                    BACKTEST RESULTS                          ║
╠══════════════════════════════════════════════════════════════╣
║  Symbol: {self.symbol:<20} Period: {self.start_date} to {self.end_date}
╠══════════════════════════════════════════════════════════════╣
║  Initial Balance:  ${self.initial_balance:>12,.2f}
║  Final Balance:    ${self.final_balance:>12,.2f}
║  Total Return:     {((self.final_balance/self.initial_balance)-1)*100:>12.2f}%
╠══════════════════════════════════════════════════════════════╣
║  Total Trades:     {self.total_trades:>12}
║  Win Rate:         {self.win_rate:>12.1f}%
║  Profit Factor:    {self.profit_factor:>12.2f}
╠══════════════════════════════════════════════════════════════╣
║  Average Win:      ${self.avg_win:>12.2f}
║  Average Loss:     ${self.avg_loss:>12.2f}
║  Largest Win:      ${self.largest_win:>12.2f}
║  Largest Loss:     ${self.largest_loss:>12.2f}
╠══════════════════════════════════════════════════════════════╣
║  Max Drawdown:     ${self.max_drawdown:>12.2f} ({self.max_drawdown_percent:.1f}%)
║  Sharpe Ratio:     {self.sharpe_ratio:>12.2f}
╚══════════════════════════════════════════════════════════════╝
"""


class Strategy:
    """
    Base strategy class for backtesting.
    
    Subclass this and implement on_candle() to create strategies.
    """
    
    def __init__(self, name: str = "Strategy"):
        self.name = name
    
    def on_candle(
        self,
        candle: Candle,
        position: Optional[BacktestTrade],
        history: List[Candle]
    ) -> Optional[Dict]:
        """
        Called for each candle during backtest.
        
        Args:
            candle: Current candle
            position: Current open position (if any)
            history: Previous candles
        
        Returns:
            None for no action, or dict with:
            - action: "long", "short", "close"
            - size: Position size (optional)
            - stop_loss: Stop loss price (optional)
            - take_profit: Take profit price (optional)
        """
        raise NotImplementedError("Implement on_candle in your strategy")
    
    def indicators(self, history: List[Candle]) -> Dict:
        """Calculate indicators. Override in subclass."""
        return {}


class Backtest:
    """
    Backtesting engine.
    
    Usage:
        class MyStrategy(Strategy):
            def on_candle(self, candle, position, history):
                if not position and candle.close > history[-1].close:
                    return {"action": "long", "stop_loss": candle.close * 0.98}
                return None
        
        bt = Backtest(
            strategy=MyStrategy(),
            symbol="BTC-USDT",
            start="2024-01-01",
            end="2024-12-01",
            initial_balance=10000
        )
        
        result = bt.run()
        print(result.summary())
    """
    
    def __init__(
        self,
        strategy: Strategy,
        symbol: str,
        start: str,
        end: str,
        initial_balance: float = 10000,
        fee_rate: float = 0.0006,  # 0.06% per trade
        client: Optional[BlofinClient] = None,
        candles: Optional[List[Candle]] = None
    ):
        self.strategy = strategy
        self.symbol = symbol
        self.start = start
        self.end = end
        self.initial_balance = initial_balance
        self.fee_rate = fee_rate
        self.client = client
        self._candles = candles
    
    def run(self) -> BacktestResult:
        """Run the backtest."""
        # Get candles
        candles = self._candles or self._fetch_candles()
        
        if not candles:
            logger.error("No candles available for backtest")
            return BacktestResult(
                symbol=self.symbol,
                start_date=self.start,
                end_date=self.end,
                initial_balance=self.initial_balance,
                final_balance=self.initial_balance,
            )
        
        # Initialize state
        balance = self.initial_balance
        position: Optional[BacktestTrade] = None
        trades: List[BacktestTrade] = []
        equity_curve = []
        trade_count = 0
        peak_equity = balance
        max_drawdown = 0
        
        logger.info(f"Running backtest on {len(candles)} candles")
        
        for i, candle in enumerate(candles):
            history = candles[:i] if i > 0 else []
            
            # Check stop loss / take profit
            if position:
                if hasattr(position, 'stop_loss') and position.stop_loss:
                    if (position.side == "long" and candle.low <= position.stop_loss) or \
                       (position.side == "short" and candle.high >= position.stop_loss):
                        position.close(position.stop_loss, candle.timestamp, "stop_loss")
                        balance += position.pnl
                        trades.append(position)
                        position = None
                        continue
                
                if hasattr(position, 'take_profit') and position.take_profit:
                    if (position.side == "long" and candle.high >= position.take_profit) or \
                       (position.side == "short" and candle.low <= position.take_profit):
                        position.close(position.take_profit, candle.timestamp, "take_profit")
                        balance += position.pnl
                        trades.append(position)
                        position = None
                        continue
            
            # Get strategy signal
            signal = self.strategy.on_candle(candle, position, history)
            
            if signal:
                action = signal.get("action")
                
                if action == "close" and position:
                    position.close(candle.close, candle.timestamp, "signal")
                    balance += position.pnl
                    trades.append(position)
                    position = None
                
                elif action in ["long", "short"] and not position:
                    trade_count += 1
                    size = signal.get("size", 1.0)
                    
                    position = BacktestTrade(
                        id=trade_count,
                        symbol=self.symbol,
                        side=action,
                        entry_time=candle.timestamp,
                        entry_price=candle.close,
                        size=size,
                    )
                    
                    # Store SL/TP on position
                    if signal.get("stop_loss"):
                        position.stop_loss = signal["stop_loss"]
                    if signal.get("take_profit"):
                        position.take_profit = signal["take_profit"]
                    
                    # Deduct fee
                    balance -= candle.close * size * self.fee_rate
            
            # Track equity
            current_equity = balance
            if position:
                if position.side == "long":
                    current_equity += (candle.close - position.entry_price) * position.size
                else:
                    current_equity += (position.entry_price - candle.close) * position.size
            
            equity_curve.append({
                "timestamp": candle.timestamp.isoformat(),
                "equity": round(current_equity, 2),
            })
            
            # Track drawdown
            if current_equity > peak_equity:
                peak_equity = current_equity
            drawdown = peak_equity - current_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # Close any remaining position
        if position and candles:
            position.close(candles[-1].close, candles[-1].timestamp, "end_of_test")
            balance += position.pnl
            trades.append(position)
        
        # Calculate results
        return self._calculate_results(trades, balance, equity_curve, max_drawdown)
    
    def _fetch_candles(self) -> List[Candle]:
        """Fetch historical candles."""
        if not self.client:
            logger.warning("No client available, using cached data")
            return self._load_cached_candles()
        
        try:
            raw = self.client.get_candles(
                inst_id=self.symbol,
                bar="1H",
                limit=1000  # Max allowed
            )
            
            candles = []
            for c in raw:
                candles.append(Candle(
                    timestamp=datetime.fromtimestamp(int(c[0]) / 1000),
                    open=float(c[1]),
                    high=float(c[2]),
                    low=float(c[3]),
                    close=float(c[4]),
                    volume=float(c[5]),
                ))
            
            # Sort by time
            candles.sort(key=lambda x: x.timestamp)
            
            # Cache for future use
            self._cache_candles(candles)
            
            return candles
            
        except Exception as e:
            logger.error(f"Failed to fetch candles: {e}")
            return self._load_cached_candles()
    
    def _cache_candles(self, candles: List[Candle]) -> None:
        """Cache candles to disk."""
        cache_dir = Path("data/candles")
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        cache_file = cache_dir / f"{self.symbol.replace('-', '_')}_1h.json"
        
        data = [c.to_dict() for c in candles]
        with open(cache_file, "w") as f:
            json.dump(data, f)
    
    def _load_cached_candles(self) -> List[Candle]:
        """Load candles from cache."""
        cache_file = Path(f"data/candles/{self.symbol.replace('-', '_')}_1h.json")
        
        if not cache_file.exists():
            return []
        
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
            
            return [
                Candle(
                    timestamp=datetime.fromisoformat(c["timestamp"]),
                    open=c["open"],
                    high=c["high"],
                    low=c["low"],
                    close=c["close"],
                    volume=c["volume"],
                )
                for c in data
            ]
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            return []
    
    def _calculate_results(
        self,
        trades: List[BacktestTrade],
        final_balance: float,
        equity_curve: List[Dict],
        max_drawdown: float
    ) -> BacktestResult:
        """Calculate backtest results from trades."""
        result = BacktestResult(
            symbol=self.symbol,
            start_date=self.start,
            end_date=self.end,
            initial_balance=self.initial_balance,
            final_balance=final_balance,
            trades=trades,
            equity_curve=equity_curve,
            max_drawdown=max_drawdown,
        )
        
        if not trades:
            return result
        
        result.total_trades = len(trades)
        
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        
        result.winning_trades = len(wins)
        result.losing_trades = len(losses)
        result.win_rate = (len(wins) / len(trades)) * 100 if trades else 0
        
        result.total_pnl = sum(t.pnl for t in trades)
        result.gross_profit = sum(t.pnl for t in wins) if wins else 0
        result.gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
        result.profit_factor = result.gross_profit / result.gross_loss if result.gross_loss > 0 else 0
        
        result.avg_win = result.gross_profit / len(wins) if wins else 0
        result.avg_loss = result.gross_loss / len(losses) if losses else 0
        result.avg_trade = result.total_pnl / len(trades) if trades else 0
        
        result.largest_win = max(t.pnl for t in wins) if wins else 0
        result.largest_loss = min(t.pnl for t in losses) if losses else 0
        
        result.max_drawdown_percent = (max_drawdown / self.initial_balance) * 100 if max_drawdown > 0 else 0
        
        # Calculate average hold time
        hold_times = [
            t.exit_time - t.entry_time
            for t in trades
            if t.exit_time and t.entry_time
        ]
        if hold_times:
            result.avg_hold_time = sum(hold_times, timedelta()) / len(hold_times)
        
        return result
