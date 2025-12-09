"""Trade journal for tracking actual trades and performance."""

import csv
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Trade:
    """A completed trade record."""
    trade_id: str
    symbol: str
    side: str  # long/short
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_percent: float
    fees: float = 0
    leverage: int = 1
    entry_time: datetime = field(default_factory=datetime.now)
    exit_time: Optional[datetime] = None
    hold_duration: Optional[str] = None
    decision_id: Optional[str] = None  # Link to AI decision
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    
    @property
    def is_win(self) -> bool:
        return self.pnl > 0
    
    @property
    def risk(self) -> float:
        """Risk in USD (entry * size / leverage)."""
        return (self.entry_price * self.size) / self.leverage
    
    @property
    def r_multiple(self) -> float:
        """R-multiple (reward/risk ratio achieved)."""
        if self.risk == 0:
            return 0
        return self.pnl / self.risk


class TradeJournal:
    """
    Trade journal with SQLite persistence.
    
    Features:
    - Log all trades automatically
    - Performance statistics
    - Export to CSV
    - Filtering and analysis
    
    Usage:
        journal = TradeJournal()
        
        # Log a trade
        journal.add_trade(
            symbol="BTC-USDT",
            side="long",
            entry_price=95000,
            exit_price=96500,
            size=0.1,
            pnl=150.0
        )
        
        # Get stats
        stats = journal.get_performance_stats()
    """
    
    def __init__(self, db_path: str = "data/trades.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    size REAL NOT NULL,
                    pnl REAL NOT NULL,
                    pnl_percent REAL NOT NULL,
                    fees REAL DEFAULT 0,
                    leverage INTEGER DEFAULT 1,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    hold_duration TEXT,
                    decision_id TEXT,
                    notes TEXT,
                    tags TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)
            """)
            
            conn.commit()
    
    def add_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        size: float,
        pnl: float,
        pnl_percent: Optional[float] = None,
        fees: float = 0,
        leverage: int = 1,
        entry_time: Optional[datetime] = None,
        exit_time: Optional[datetime] = None,
        decision_id: Optional[str] = None,
        notes: str = "",
        tags: Optional[List[str]] = None
    ) -> Trade:
        """
        Add a completed trade to the journal.
        
        Returns:
            Trade object
        """
        if pnl_percent is None:
            # Calculate from entry
            pnl_percent = (pnl / (entry_price * size)) * 100 * leverage
        
        trade_id = f"trade_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        entry_time = entry_time or datetime.now()
        exit_time = exit_time or datetime.now()
        
        # Calculate hold duration
        hold_delta = exit_time - entry_time
        hours, remainder = divmod(hold_delta.total_seconds(), 3600)
        mins, _ = divmod(remainder, 60)
        hold_duration = f"{int(hours)}h {int(mins)}m"
        
        trade = Trade(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            pnl=pnl,
            pnl_percent=pnl_percent,
            fees=fees,
            leverage=leverage,
            entry_time=entry_time,
            exit_time=exit_time,
            hold_duration=hold_duration,
            decision_id=decision_id,
            notes=notes,
            tags=tags or []
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO trades 
                (trade_id, symbol, side, entry_price, exit_price, size, pnl, pnl_percent,
                 fees, leverage, entry_time, exit_time, hold_duration, decision_id, notes, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.trade_id, trade.symbol, trade.side, trade.entry_price,
                trade.exit_price, trade.size, trade.pnl, trade.pnl_percent,
                trade.fees, trade.leverage, trade.entry_time.isoformat(),
                trade.exit_time.isoformat() if trade.exit_time else None,
                trade.hold_duration, trade.decision_id, trade.notes,
                json.dumps(trade.tags)
            ))
            conn.commit()
        
        logger.info(f"Trade logged: {symbol} {side} P&L: ${pnl:+.2f} ({pnl_percent:+.2f}%)")
        
        return trade
    
    def get_trades(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get trades with optional filters.
        
        Args:
            symbol: Filter by symbol
            start_date: Filter from date
            end_date: Filter to date
            limit: Max results
        
        Returns:
            List of trade dicts
        """
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        if start_date:
            query += " AND date(entry_time) >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND date(entry_time) <= ?"
            params.append(end_date.isoformat())
        
        query += " ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_trades_today(self) -> List[Dict]:
        """Get all trades from today."""
        return self.get_trades(start_date=date.today(), end_date=date.today())
    
    def get_recent(self, limit: int = 100) -> List[Dict]:
        """Get recent trades (alias for get_trades for compatibility)."""
        trades = self.get_trades(limit=limit)
        # Add close_time field for performance tracker compatibility
        for trade in trades:
            trade["close_time"] = trade.get("exit_time") or trade.get("entry_time")
        return trades
    
    def get_performance_stats(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[date] = None
    ) -> Dict:
        """
        Calculate comprehensive performance statistics.
        
        Returns:
            Dict with win rate, expectancy, etc.
        """
        query = """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN pnl = 0 THEN 1 ELSE 0 END) as breakeven,
                SUM(pnl) as total_pnl,
                AVG(pnl) as avg_pnl,
                AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN pnl END) as avg_loss,
                MAX(pnl) as largest_win,
                MIN(pnl) as largest_loss,
                SUM(fees) as total_fees
            FROM trades
            WHERE 1=1
        """
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        if start_date:
            query += " AND date(entry_time) >= ?"
            params.append(start_date.isoformat())
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            
            total = row[0] or 0
            wins = row[1] or 0
            losses = row[2] or 0
            avg_win = row[6] or 0
            avg_loss = abs(row[7] or 0)
            
            # Calculate derived metrics
            win_rate = (wins / total * 100) if total > 0 else 0
            profit_factor = (avg_win * wins) / (avg_loss * losses) if losses > 0 and avg_loss > 0 else 0
            
            # Expectancy = (Win% * Avg Win) - (Loss% * Avg Loss)
            expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)
            
            return {
                "total_trades": total,
                "wins": wins,
                "losses": losses,
                "breakeven": row[3] or 0,
                "win_rate": win_rate,
                "total_pnl": row[4] or 0,
                "avg_pnl": row[5] or 0,
                "avg_win": avg_win,
                "avg_loss": -avg_loss,
                "largest_win": row[8] or 0,
                "largest_loss": row[9] or 0,
                "profit_factor": profit_factor,
                "expectancy": expectancy,
                "total_fees": row[10] or 0,
            }
    
    def get_daily_summary(self, days: int = 7) -> List[Dict]:
        """Get daily performance summary."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT 
                    date(entry_time) as trade_date,
                    COUNT(*) as trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(pnl) as pnl
                FROM trades
                WHERE date(entry_time) >= date('now', ?)
                GROUP BY date(entry_time)
                ORDER BY trade_date DESC
            """, (f"-{days} days",))
            return [dict(row) for row in cursor.fetchall()]
    
    def export_csv(self, filepath: str, symbol: Optional[str] = None) -> str:
        """
        Export trades to CSV.
        
        Args:
            filepath: Output file path
            symbol: Optional filter
        
        Returns:
            Path to exported file
        """
        trades = self.get_trades(symbol=symbol, limit=10000)
        
        if not trades:
            logger.warning("No trades to export")
            return ""
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=trades[0].keys())
            writer.writeheader()
            writer.writerows(trades)
        
        logger.info(f"Exported {len(trades)} trades to {filepath}")
        return str(filepath)
