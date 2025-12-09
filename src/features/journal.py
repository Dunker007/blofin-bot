"""Session journal for daily trading notes."""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional
import json
from pathlib import Path

from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class JournalEntry:
    """A daily journal entry."""
    date: str  # YYYY-MM-DD
    mood: str = "neutral"  # bullish, bearish, neutral, uncertain
    notes: str = ""
    lessons: str = ""
    plan: str = ""  # Trading plan for the day
    review: str = ""  # End of day review
    tags: List[str] = field(default_factory=list)
    trades_planned: int = 0
    trades_taken: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "date": self.date,
            "mood": self.mood,
            "notes": self.notes,
            "lessons": self.lessons,
            "plan": self.plan,
            "review": self.review,
            "tags": self.tags,
            "trades_planned": self.trades_planned,
            "trades_taken": self.trades_taken,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "JournalEntry":
        return cls(
            date=data["date"],
            mood=data.get("mood", "neutral"),
            notes=data.get("notes", ""),
            lessons=data.get("lessons", ""),
            plan=data.get("plan", ""),
            review=data.get("review", ""),
            tags=data.get("tags", []),
            trades_planned=data.get("trades_planned", 0),
            trades_taken=data.get("trades_taken", 0),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat())),
        )


class SessionJournal:
    """
    Daily session journal for trading notes.
    
    Usage:
        journal = SessionJournal()
        
        # Get/create today's entry
        entry = journal.get_today()
        
        # Update notes
        journal.update_today(notes="Looking bullish", mood="bullish")
        
        # Get history
        entries = journal.get_recent(7)
    """
    
    def __init__(self, storage_path: str = "data/session_journal.json"):
        self.storage_path = Path(storage_path)
        self._entries: Dict[str, JournalEntry] = {}
        self._load()
    
    def get_today(self) -> JournalEntry:
        """Get or create today's journal entry."""
        today = date.today().isoformat()
        
        if today not in self._entries:
            self._entries[today] = JournalEntry(date=today)
            self._save()
        
        return self._entries[today]
    
    def update_today(
        self,
        mood: Optional[str] = None,
        notes: Optional[str] = None,
        lessons: Optional[str] = None,
        plan: Optional[str] = None,
        review: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> JournalEntry:
        """Update today's journal entry."""
        entry = self.get_today()
        
        if mood is not None:
            entry.mood = mood
        if notes is not None:
            entry.notes = notes
        if lessons is not None:
            entry.lessons = lessons
        if plan is not None:
            entry.plan = plan
        if review is not None:
            entry.review = review
        if tags is not None:
            entry.tags = tags
        
        entry.updated_at = datetime.now()
        self._save()
        
        return entry
    
    def increment_trades(self, planned: bool = False) -> None:
        """Increment trade count for today."""
        entry = self.get_today()
        if planned:
            entry.trades_planned += 1
        else:
            entry.trades_taken += 1
        entry.updated_at = datetime.now()
        self._save()
    
    def get_entry(self, date_str: str) -> Optional[JournalEntry]:
        """Get entry for a specific date."""
        return self._entries.get(date_str)
    
    def get_recent(self, days: int = 7) -> List[JournalEntry]:
        """Get recent journal entries."""
        entries = sorted(
            self._entries.values(),
            key=lambda e: e.date,
            reverse=True
        )
        return entries[:days]
    
    def get_all(self) -> List[JournalEntry]:
        """Get all journal entries."""
        return sorted(
            self._entries.values(),
            key=lambda e: e.date,
            reverse=True
        )
    
    def search(self, query: str) -> List[JournalEntry]:
        """Search journal entries."""
        query = query.lower()
        results = []
        
        for entry in self._entries.values():
            if (query in entry.notes.lower() or
                query in entry.lessons.lower() or
                query in entry.plan.lower() or
                query in entry.review.lower() or
                any(query in tag.lower() for tag in entry.tags)):
                results.append(entry)
        
        return sorted(results, key=lambda e: e.date, reverse=True)
    
    def _load(self) -> None:
        """Load journal from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                
                for entry_data in data.get("entries", []):
                    entry = JournalEntry.from_dict(entry_data)
                    self._entries[entry.date] = entry
                
                logger.info(f"Loaded {len(self._entries)} journal entries")
            except Exception as e:
                logger.error(f"Failed to load journal: {e}")
    
    def _save(self) -> None:
        """Save journal to storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "entries": [entry.to_dict() for entry in self._entries.values()],
            "updated_at": datetime.now().isoformat(),
        }
        
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)
