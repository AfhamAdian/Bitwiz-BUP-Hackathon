from fastapi import FastAPI

from app.middlewares.logging import LoggingMiddleware
from app.routes import optimize

app = FastAPI(title="Bitwiz Backend")

app.add_middleware(LoggingMiddleware)

app.include_router(optimize.router)


@app.get("/")
async def root():
    return {"status": "ok"}
