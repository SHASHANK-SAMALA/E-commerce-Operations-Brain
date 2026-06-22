"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import sys
import uuid
from contextlib import asynccontextmanager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from ecommerce_brain.api.routers import investigate
from ecommerce_brain.db.engine import initialize_database
from ecommerce_brain.api.status_store import reconcile_running_investigations
from ecommerce_brain.observability.setup import setup_all

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    initialize_database()
    setup_all()
    reconcile_running_investigations()
    log.info("ecommerce_brain.startup")
    yield
    log.info("ecommerce_brain.shutdown")


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="E-Commerce Operations Brain",
    description="Multi-agent AI operations analyst for e-commerce",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

from ecommerce_brain.config.settings import settings  # noqa: E402

if settings.otel_enabled:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: E402
    FastAPIInstrumentor.instrument_app(app)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — restricted to local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_context_middleware(request: Request, call_next):
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=str(uuid.uuid4()),
        method=request.method,
        path=request.url.path,
    )
    response = await call_next(request)
    return response

@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=str(request.url), error=str(exc)[:300])
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# Routers
app.include_router(investigate.router, prefix="/api/v1")

