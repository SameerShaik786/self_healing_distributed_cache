from fastapi import FastAPI
from app.core.database import Base, engine
app = FastAPI()

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.get("/")
def read_root():
    return {"message" : "Hello World!"}