from __future__ import annotations

from datetime import datetime, UTC
from typing import Optional

from sqlalchemy.orm import Session

from cache_node.app.core.database import SessionLocal
from cache_node.app.models.cache_entry import CacheEntry
from cache_node.app.services.version_vector import VersionVector


class StorageEngine:
    def __init__(self, db: Optional[Session] = None) -> None:
        self.db = db or SessionLocal()
        self._memory_cache: dict[str, tuple[str, int]] = {}  # {key: (value, version)}

    def put(self, key: str, value: str, version: Optional[VersionVector] = None) -> tuple[bool, VersionVector]:
        """Put a value with version tracking. Returns (success, version)."""
        now = datetime.now(UTC)
        entry = self.db.query(CacheEntry).filter(CacheEntry.key == key).first()

        if version is None:
            raise ValueError("Version vector required for put")

        # If entry exists, check for conflict
        if entry is not None and not entry.is_deleted:
            existing_version = VersionVector(entry.version, entry.node_id or "unknown")
            comparison = version.compare(existing_version)
            
            # Don't overwrite newer data
            if comparison == "older":
                return False, existing_version

        if entry is None:
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                updated_at=now,
                version=version.timestamp,
                node_id=version.node_id,
                is_deleted=False,
            )
            self.db.add(entry)
        else:
            entry.value = value
            entry.updated_at = now
            entry.version = version.timestamp
            entry.node_id = version.node_id
            entry.is_deleted = False

        self.db.commit()
        # Update in-memory cache
        self._memory_cache[key] = (value, version.timestamp)
        return True, version

    def get(self, key: str) -> Optional[tuple[str, VersionVector]]:
        """Get a value with version. Returns (value, version) or None."""
        # Check in-memory cache first
        if key in self._memory_cache:
            value, ts = self._memory_cache[key]
            return value, VersionVector(ts, "cached")

        # Fall back to DB
        entry = self.db.query(CacheEntry).filter(CacheEntry.key == key).first()
        if entry is None or entry.is_deleted:
            return None
        
        version = VersionVector(entry.version or 0, entry.node_id or "unknown")
        # Update in-memory cache
        self._memory_cache[key] = (entry.value, entry.version or 0)
        return entry.value, version

    def delete(self, key: str, version: Optional[VersionVector] = None) -> bool:
        """Delete a key with version tracking."""
        entry = self.db.query(CacheEntry).filter(CacheEntry.key == key).first()
        if entry is None:
            return False

        if version is None:
            raise ValueError("Version vector required for delete")

        entry.is_deleted = True
        entry.updated_at = datetime.now(UTC)
        entry.version = version.timestamp
        entry.node_id = version.node_id
        self.db.commit()
        # Remove from in-memory cache
        if key in self._memory_cache:
            del self._memory_cache[key]
        return True
