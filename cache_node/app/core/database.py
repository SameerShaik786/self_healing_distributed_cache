from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from python.dotenv import load_dotenv
import os
load_dotenv()

NODE_ID = os.getenv("NODE_ID","node1")


DATABASE_URL = f"sqlite:///./{NODE_ID}.db"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)

def get_db():
    db = SessionLocal()
    try :
        yield db
    finally:
        db.close() 