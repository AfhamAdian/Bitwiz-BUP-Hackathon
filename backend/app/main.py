import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.middlewares.logging import LoggingMiddleware
from app.routes import optimize, test
from app.utils.llm import LLMError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s"
)

app = FastAPI(title="Bitwiz Backend")

app.add_middleware(LoggingMiddleware)

app.include_router(optimize.router)
app.include_router(test.router)


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "LLM interpretation unavailable"})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"status": "ok"}
