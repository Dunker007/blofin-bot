"""Approval queue for copilot mode trade confirmations."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional
from queue import Queue
import threading

from ..ai.brain import AIDecision
from ..core.logger import get_logger

logger = get_logger(__name__)


class ApprovalStatus(Enum):
    """Status of a pending approval."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    EXPIRED = "expired"
    SKIPPED = "skipped"


@dataclass
class PendingApproval:
    """A trade decision awaiting human approval."""
    decision: AIDecision
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    modified_params: Optional[Dict] = None
    notes: str = ""
    
    def __post_init__(self):
        # Default expiry of 5 minutes
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(minutes=5)
    
    @property
    def is_expired(self) -> bool:
        """Check if approval has expired."""
        return datetime.now() > self.expires_at
    
    @property
    def time_remaining(self) -> timedelta:
        """Time until expiry."""
        remaining = self.expires_at - datetime.now()
        return max(remaining, timedelta(0))
    
    @property
    def time_remaining_str(self) -> str:
        """Human-readable time remaining."""
        secs = int(self.time_remaining.total_seconds())
        if secs <= 0:
            return "EXPIRED"
        mins, secs = divmod(secs, 60)
        return f"{mins}:{secs:02d}"
    
    def approve(self, notes: str = "") -> None:
        """Approve the trade."""
        self.status = ApprovalStatus.APPROVED
        self.notes = notes
        logger.info(f"Approved: {self.decision.decision_id} - {self.decision.action} {self.decision.symbol}")
    
    def reject(self, reason: str = "") -> None:
        """Reject the trade."""
        self.status = ApprovalStatus.REJECTED
        self.notes = reason
        logger.info(f"Rejected: {self.decision.decision_id} - {reason}")
    
    def modify(self, params: Dict, notes: str = "") -> None:
        """Approve with modified parameters."""
        self.status = ApprovalStatus.MODIFIED
        self.modified_params = params
        self.notes = notes
        logger.info(f"Modified: {self.decision.decision_id} - {params}")
    
    def skip(self) -> None:
        """Skip this approval for now."""
        self.status = ApprovalStatus.SKIPPED
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "decision_id": self.decision.decision_id,
            "symbol": self.decision.symbol,
            "action": self.decision.action,
            "confidence": self.decision.confidence,
            "entry": self.decision.entry,
            "stop_loss": self.decision.stop_loss,
            "take_profit": self.decision.take_profit,
            "reasoning": self.decision.reasoning,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "time_remaining": self.time_remaining_str,
        }


class ApprovalQueue:
    """
    Queue for managing pending trade approvals in copilot mode.
    
    Usage:
        queue = ApprovalQueue()
        queue.add(decision)
        
        # In approval loop
        pending = queue.get_pending()
        for approval in pending:
            # Show to user, get response
            approval.approve()  # or reject(), modify()
        
        # Process approved trades
        approved = queue.get_approved()
    """
    
    def __init__(
        self,
        expiry_minutes: int = 5,
        max_pending: int = 10,
        on_approval: Optional[Callable[[PendingApproval], None]] = None,
        on_expiry: Optional[Callable[[PendingApproval], None]] = None
    ):
        self.expiry_minutes = expiry_minutes
        self.max_pending = max_pending
        self.on_approval = on_approval
        self.on_expiry = on_expiry
        
        self._pending: List[PendingApproval] = []
        self._history: List[PendingApproval] = []
        self._lock = threading.Lock()
    
    def add(self, decision: AIDecision) -> PendingApproval:
        """
        Add a decision to the approval queue.
        
        Args:
            decision: AI trading decision
        
        Returns:
            PendingApproval object
        """
        with self._lock:
            # Check max pending
            if len(self._pending) >= self.max_pending:
                # Remove oldest
                oldest = self._pending.pop(0)
                oldest.status = ApprovalStatus.EXPIRED
                self._history.append(oldest)
                logger.warning(f"Queue full, expired oldest: {oldest.decision.decision_id}")
            
            approval = PendingApproval(
                decision=decision,
                expires_at=datetime.now() + timedelta(minutes=self.expiry_minutes)
            )
            self._pending.append(approval)
            
            logger.info(f"Queued for approval: {decision.decision_id} - {decision.action} {decision.symbol}")
            
            return approval
    
    def get_pending(self) -> List[PendingApproval]:
        """Get all pending approvals (cleans up expired)."""
        with self._lock:
            self._cleanup_expired()
            return [a for a in self._pending if a.status == ApprovalStatus.PENDING]
    
    def get_next(self) -> Optional[PendingApproval]:
        """Get next pending approval."""
        pending = self.get_pending()
        return pending[0] if pending else None
    
    def get_approved(self) -> List[PendingApproval]:
        """Get all approved (ready to execute) items."""
        with self._lock:
            approved = [
                a for a in self._pending 
                if a.status in [ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED]
            ]
            # Move to history
            for a in approved:
                self._pending.remove(a)
                self._history.append(a)
            return approved
    
    def get_by_id(self, decision_id: str) -> Optional[PendingApproval]:
        """Find approval by decision ID."""
        with self._lock:
            for approval in self._pending:
                if approval.decision.decision_id == decision_id:
                    return approval
        return None
    
    def approve_by_id(self, decision_id: str, notes: str = "") -> bool:
        """Approve a specific decision."""
        approval = self.get_by_id(decision_id)
        if approval:
            approval.approve(notes)
            if self.on_approval:
                self.on_approval(approval)
            return True
        return False
    
    def reject_by_id(self, decision_id: str, reason: str = "") -> bool:
        """Reject a specific decision."""
        approval = self.get_by_id(decision_id)
        if approval:
            approval.reject(reason)
            return True
        return False
    
    def approve_all(self) -> int:
        """Approve all pending. Returns count approved."""
        pending = self.get_pending()
        for approval in pending:
            approval.approve()
            if self.on_approval:
                self.on_approval(approval)
        return len(pending)
    
    def reject_all(self, reason: str = "Bulk reject") -> int:
        """Reject all pending. Returns count rejected."""
        pending = self.get_pending()
        for approval in pending:
            approval.reject(reason)
        return len(pending)
    
    def clear(self) -> None:
        """Clear all pending approvals."""
        with self._lock:
            for approval in self._pending:
                approval.status = ApprovalStatus.EXPIRED
                self._history.append(approval)
            self._pending.clear()
    
    def _cleanup_expired(self) -> None:
        """Move expired approvals to history."""
        expired = [a for a in self._pending if a.is_expired and a.status == ApprovalStatus.PENDING]
        for approval in expired:
            approval.status = ApprovalStatus.EXPIRED
            self._pending.remove(approval)
            self._history.append(approval)
            if self.on_expiry:
                self.on_expiry(approval)
            logger.info(f"Expired: {approval.decision.decision_id}")
    
    @property
    def pending_count(self) -> int:
        """Number of pending approvals."""
        return len(self.get_pending())
    
    @property
    def history(self) -> List[PendingApproval]:
        """Get approval history."""
        return list(self._history)
    
    def get_stats(self) -> Dict:
        """Get queue statistics."""
        all_items = self._pending + self._history
        return {
            "pending": self.pending_count,
            "approved": sum(1 for a in all_items if a.status == ApprovalStatus.APPROVED),
            "rejected": sum(1 for a in all_items if a.status == ApprovalStatus.REJECTED),
            "expired": sum(1 for a in all_items if a.status == ApprovalStatus.EXPIRED),
            "modified": sum(1 for a in all_items if a.status == ApprovalStatus.MODIFIED),
            "total_processed": len(self._history),
        }
