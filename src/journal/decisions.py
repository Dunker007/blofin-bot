"""Decision journal for tracking AI decisions and outcomes."""

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..ai.brain import AIDecision
from ..human.approval import PendingApproval, ApprovalStatus
from ..core.logger import get_logger

logger = get_logger(__name__)


class DecisionJournal:
    """
    Persistent journal for AI trading decisions.
    
    Tracks:
    - Every AI decision with market context
    - Human approval/rejection actions
    - Execution results
    - Outcome after position closes
    
    Usage:
        journal = DecisionJournal()
        
        # Log a decision
        journal.log_decision(decision)
        
        # Update with approval
        journal.log_approval(decision_id, "approved", notes="Looks good")
        
        # Update with execution
        journal.log_execution(decision_id, order_id="123", fill_price=95000)
        
        # Update with outcome
        journal.log_outcome(decision_id, pnl=250.0, hold_time="2h 15m")
    """
    
    def __init__(self, db_path: str = "data/decisions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    entry REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    size_percent REAL,
                    reasoning TEXT,
                    invalidation TEXT,
                    market_context TEXT,
                    
                    -- Approval
                    approval_status TEXT,
                    approval_timestamp TEXT,
                    approval_notes TEXT,
                    
                    -- Execution
                    executed INTEGER DEFAULT 0,
                    order_id TEXT,
                    fill_price REAL,
                    fill_size REAL,
                    execution_timestamp TEXT,
                    
                    -- Outcome
                    outcome_result TEXT,
                    outcome_pnl REAL,
                    outcome_r_multiple REAL,
                    outcome_hold_time TEXT,
                    outcome_timestamp TEXT,
                    
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp)
            """)
            
            conn.commit()
    
    def log_decision(self, decision: AIDecision) -> None:
        """
        Log a new AI decision.
        
        Args:
            decision: AIDecision from the AI brain
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO decisions 
                (decision_id, timestamp, symbol, action, confidence, entry, stop_loss, 
                 take_profit, size_percent, reasoning, invalidation, market_context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision.decision_id,
                decision.timestamp.isoformat(),
                decision.symbol,
                decision.action,
                decision.confidence,
                decision.entry,
                decision.stop_loss,
                decision.take_profit,
                decision.size_percent,
                decision.reasoning,
                decision.invalidation,
                json.dumps(decision.market_context)
            ))
            conn.commit()
        
        logger.debug(f"Logged decision: {decision.decision_id}")
    
    def log_approval(
        self,
        decision_id: str,
        status: str,
        notes: str = ""
    ) -> None:
        """
        Log approval/rejection of a decision.
        
        Args:
            decision_id: Decision ID
            status: approved, rejected, expired, etc.
            notes: Optional notes
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE decisions 
                SET approval_status = ?, approval_timestamp = ?, approval_notes = ?
                WHERE decision_id = ?
            """, (status, datetime.now().isoformat(), notes, decision_id))
            conn.commit()
        
        logger.debug(f"Logged approval: {decision_id} -> {status}")
    
    def log_execution(
        self,
        decision_id: str,
        order_id: str,
        fill_price: float,
        fill_size: Optional[float] = None
    ) -> None:
        """
        Log trade execution.
        
        Args:
            decision_id: Decision ID
            order_id: Exchange order ID
            fill_price: Actual fill price
            fill_size: Actual fill size
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE decisions 
                SET executed = 1, order_id = ?, fill_price = ?, fill_size = ?,
                    execution_timestamp = ?
                WHERE decision_id = ?
            """, (order_id, fill_price, fill_size, datetime.now().isoformat(), decision_id))
            conn.commit()
        
        logger.info(f"Logged execution: {decision_id} @ ${fill_price}")
    
    def log_outcome(
        self,
        decision_id: str,
        result: str,
        pnl: float,
        r_multiple: Optional[float] = None,
        hold_time: Optional[str] = None
    ) -> None:
        """
        Log trade outcome after position closes.
        
        Args:
            decision_id: Decision ID
            result: "win", "loss", "breakeven"
            pnl: Profit/loss in USD
            r_multiple: R-multiple (reward/risk)
            hold_time: How long position was held
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE decisions 
                SET outcome_result = ?, outcome_pnl = ?, outcome_r_multiple = ?,
                    outcome_hold_time = ?, outcome_timestamp = ?
                WHERE decision_id = ?
            """, (result, pnl, r_multiple, hold_time, datetime.now().isoformat(), decision_id))
            conn.commit()
        
        logger.info(f"Logged outcome: {decision_id} -> {result} (${pnl:+.2f})")
    
    def get_decision(self, decision_id: str) -> Optional[Dict]:
        """Get a specific decision."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM decisions WHERE decision_id = ?",
                (decision_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_recent(self, limit: int = 50) -> List[Dict]:
        """Get recent decisions."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_by_symbol(self, symbol: str, limit: int = 20) -> List[Dict]:
        """Get decisions for a specific symbol."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM decisions WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
                (symbol, limit)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_executed(self, limit: int = 50) -> List[Dict]:
        """Get executed trades."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM decisions WHERE executed = 1 ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> Dict:
        """Get overall statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_decisions,
                    SUM(CASE WHEN approval_status = 'approved' THEN 1 ELSE 0 END) as approved,
                    SUM(CASE WHEN approval_status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                    SUM(CASE WHEN executed = 1 THEN 1 ELSE 0 END) as executed,
                    SUM(CASE WHEN outcome_result = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome_result = 'loss' THEN 1 ELSE 0 END) as losses,
                    SUM(outcome_pnl) as total_pnl,
                    AVG(confidence) as avg_confidence
                FROM decisions
            """)
            row = cursor.fetchone()
            
            total = row[0] or 0
            executed = row[4] or 0
            wins = row[5] or 0
            losses = row[6] or 0
            
            return {
                "total_decisions": total,
                "approved": row[1] or 0,
                "rejected": row[2] or 0,
                "executed": row[3] or 0,
                "wins": wins,
                "losses": losses,
                "win_rate": (wins / executed * 100) if executed > 0 else 0,
                "total_pnl": row[7] or 0,
                "avg_confidence": row[8] or 0,
            }
    
    def get_performance_by_confidence(self) -> List[Dict]:
        """Analyze performance by confidence level."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT 
                    CASE 
                        WHEN confidence >= 85 THEN 'high (85+)'
                        WHEN confidence >= 75 THEN 'medium (75-84)'
                        ELSE 'low (<75)'
                    END as confidence_level,
                    COUNT(*) as count,
                    SUM(CASE WHEN outcome_result = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(outcome_pnl) as total_pnl
                FROM decisions
                WHERE executed = 1 AND outcome_result IS NOT NULL
                GROUP BY confidence_level
                ORDER BY confidence_level DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
