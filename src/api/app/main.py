from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.exceptions import (
    CospecException,
    cospec_exception_handler,
    generic_exception_handler,
    validation_exception_handler,
)
from app.core.logging import setup_logging
from app.core.middleware import RateLimitMiddleware, TraceIDMiddleware
from app.routers.admin import router as admin_router
from app.routers.ai import router as ai_router
from app.routers.appointments import router as appointments_router
from app.routers.assignments import router as assignments_router
from app.routers.attachments import router as attachments_router
from app.routers.auth import router as auth_router
from app.routers.checklist import router as checklist_router
from app.routers.dashboard import router as dashboard_router
from app.routers.events import router as events_router
from app.routers.exports import router as exports_router
from app.routers.messages import router as messages_router
from app.routers.status import router as status_router
from app.routers.tickets import router as tickets_router
from app.routers.users import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.APP_LOG_LEVEL)
    yield
    # Shutdown cleanup (close DB pool, etc.) handled by SQLAlchemy engine


app = FastAPI(
    title="Cospec Telecomunicaciones API",
    version=settings.APP_VERSION,
    description="Backend API for Cospec Telecomunicaciones field service management",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Middleware (order matters — last added is first executed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TraceIDMiddleware)
app.add_middleware(RateLimitMiddleware)

# Exception handlers
app.add_exception_handler(CospecException, cospec_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_exception_handler)

# Routers — all under /api/v1/
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(tickets_router, prefix="/api/v1")
app.include_router(assignments_router, prefix="/api/v1")
app.include_router(status_router, prefix="/api/v1")
app.include_router(appointments_router, prefix="/api/v1")
app.include_router(messages_router, prefix="/api/v1")
app.include_router(attachments_router, prefix="/api/v1")
app.include_router(checklist_router, prefix="/api/v1")
app.include_router(exports_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "version": settings.APP_VERSION, "env": settings.APP_ENV}
