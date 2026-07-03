from __future__ import annotations

from datetime import datetime, UTC
from typing import Optional

from sqlalchemy.orm import Session

from cache_node.app.core.database import SessionLocal
from cache_node.app.models.cache_entry import CacheEntry


class StorageEngine:
    def __init__(self, db: Optional[Session] = None) -> None:
        self.db = db or SessionLocal()
        self._memory_cache: dict[str, tuple[str, int]] = {}  # {key: (value, version)}

    def put(self, key: str, value: str) -> bool:
        now = datetime.now(UTC)
        entry = self.db.query(CacheEntry).filter(CacheEntry.key == key).first()

        if entry is None:
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                updated_at=now,
                version=1,
                is_deleted=False,
            )
            self.db.add(entry)
        else:
            entry.value = value
            entry.updated_at = now
            entry.version = (entry.version or 0) + 1
            entry.is_deleted = False

        self.db.commit()
        # Update in-memory cache
        self._memory_cache[key] = (value, entry.version)
        return True

    def get(self, key: str) -> Optional[str]:
        # Check in-memory cache first
        if key in self._memory_cache:
            value, _ = self._memory_cache[key]
            return value

        # Fall back to DB
        entry = self.db.query(CacheEntry).filter(CacheEntry.key == key).first()
        if entry is None or entry.is_deleted:
            return None
        
        # Update in-memory cache
        self._memory_cache[key] = (entry.value, entry.version)
        return entry.value

    def delete(self, key: str) -> bool:
        entry = self.db.query(CacheEntry).filter(CacheEntry.key == key).first()
        if entry is None:
            return False

        entry.is_deleted = True
        entry.updated_at = datetime.now(UTC)
        entry.version = (entry.version or 0) + 1
        self.db.commit()
        # Remove from in-memory cache
        if key in self._memory_cache:
            del self._memory_cache[key]
        return True
