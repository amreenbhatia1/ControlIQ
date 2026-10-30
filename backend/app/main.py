import logging
import uuid
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import assessments, assets, auth, controls, dashboard, demo, evidence, findings, intelligence, platform, reports, risks, services
from app.core.config import get_settings

logger = logging.getLogger("controliq")
settings = get_settings()

app = FastAPI(
    title="ControlIQ API",
    version="1.0.0",
    description="Continuous Technology Controls Monitoring & Risk Intelligence Platform. "
    "Synthetic demonstration environment — no production banking data.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Requested-With"],
    expose_headers=["Content-Disposition", "X-Report-Id", "X-Content-SHA256"],
)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # CSRF defence-in-depth: reject state-changing requests from untrusted browser origins.
    origin = request.headers.get("origin")
    if request.method in UNSAFE_METHODS and origin:
        host = request.headers.get("host", "")
        same_host = urlparse(origin).netloc == host
        if not same_host and origin not in settings.cors_origin_list:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    error_id = uuid.uuid4().hex[:12]
    logger.exception("Unhandled error %s on %s %s", error_id, request.method, request.url.path)
    return JSONResponse({"detail": "An internal error occurred", "error_id": error_id}, status_code=500)


API = "/api/v1"
for module in (auth, dashboard, assets, services, controls, assessments, evidence, risks, intelligence, reports, demo, platform):
    app.include_router(module.router, prefix=API)
app.include_router(findings.router, prefix=API)
app.include_router(findings.remediation_router, prefix=API)


@app.get("/api/health", tags=["Platform"])
def health():
    from sqlalchemy import text

    from app.core.database import SessionLocal

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # pragma: no cover
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "ai_enabled": settings.ai_enabled,
            "environment": "synthetic-demo"}
