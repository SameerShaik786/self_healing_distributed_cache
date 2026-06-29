from __future__ import annotations

from datetime import datetime, UTC
from typing import Optional

from sqlalchemy.orm import Session

from cache_node.app.core.database import SessionLocal
from cache_node.app.models.cache_entry import CacheEntry


class StorageEngine:
    def __init__(self, db: Optional[Session] = None) -> None:
        self.db = db or SessionLocal()

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
        return True

    def get(self, key: str) -> Optional[str]:
        entry = self.db.query(CacheEntry).filter(CacheEntry.key == key).first()
        if entry is None or entry.is_deleted:
            return None
        return entry.value

    def delete(self, key: str) -> bool:
        entry = self.db.query(CacheEntry).filter(CacheEntry.key == key).first()
        if entry is None:
            return False

        entry.is_deleted = True
        entry.updated_at = datetime.now(UTC)
        entry.version = (entry.version or 0) + 1
        self.db.commit()
        return True
