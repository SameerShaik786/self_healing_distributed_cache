from cache_node.app.core.database import Base
from sqlalchemy import Column, Integer, String, DateTime

class WriteLog(Base):
    __tablename__ = "write_logs"

    id = Column(Integer, primary_key=True, index=True)
    operation_id = Column(String, unique=True, index=True, nullable=False)
    operation_type = Column(String, nullable=False)
    key = Column(String,index = True, nullable=False)
    value = Column(String, nullable=True)
    version = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    status = Column(String, nullable=False)