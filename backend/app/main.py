import time
import uuid
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.routers.scout_liq import router as scout_liq_router
from app.database import SessionLocal
from app.database import engine

_logger = logging.getLogger("afiliator")

app = FastAPI(
    title="Liquidador de Calidad Scouts Yego",
    description="API para liquidacion de pagos a scouts segun calidad de conversion",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request Logging Middleware ───────────────────────────────────────

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        _logger.info(
            f"req_id={request_id} method={request.method} path={request.url.path} "
            f"status={response.status_code} elapsed_ms={elapsed_ms}"
        )
        response.headers["X-Request-Id"] = request_id
        return response
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        _logger.error(
            f"req_id={request_id} method={request.method} path={request.url.path} "
            f"status=500 elapsed_ms={elapsed_ms} error={e}"
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor", "request_id": request_id},
        )


# ── Global Exception Handler ─────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", "?")
    _logger.error(f"req_id={rid} unhandled_error={exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Error interno del servidor",
            "request_id": rid,
            "type": type(exc).__name__,
        } if settings.ENVIRONMENT == "dev" else {
            "detail": "Error interno del servidor",
            "request_id": rid,
        },
    )


app.include_router(scout_liq_router)


# ── Health Check ─────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    checks = {"api": "ok", "environment": settings.ENVIRONMENT}
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        return JSONResponse(status_code=503, content={"status": "unhealthy", "checks": checks})
    return {"status": "ok", "checks": checks}


@app.get("/")
def root():
    return {
        "app": "Liquidador de Calidad Scouts Yego",
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
    }
