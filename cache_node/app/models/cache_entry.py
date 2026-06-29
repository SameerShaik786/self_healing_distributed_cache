from cache_node.app.core.database import Base
from sqlalchemy import Column, Integer, String, DateTime, Boolean

class CacheEntry(Base):
    __tablename__ = "cache_entries"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    version = Column(Integer,nullable = False, default=1)
    is_deleted = Column(Boolean, default=False)