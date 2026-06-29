from fastapi import FastAPI

from cache_node.app.core.database import Base, engine
from cache_node.app.routes.cache_routes import router

app = FastAPI(title="self-healing distributed cache")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(router)
