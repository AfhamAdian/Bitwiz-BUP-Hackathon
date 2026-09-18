import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "[http] %s %s -> %s in %.2fs",
            request.method,
            request.url.path,
            response.status_code,
            time.perf_counter() - started,
        )
        return response
