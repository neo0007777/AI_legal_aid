import os
from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Loophole fix #1 (follow-up): this used to run AFTER `from routes import ...`
# below, so by the time utils/auth.py read JWT_SECRET_KEY from the environment,
# .env hadn't been loaded yet. That's exactly what masked the insecure
# fallback in the first place -- the module-level checks that should have
# caught a missing key never saw it as missing, because it had every chance
# to be there by request time (uvicorn --reload, gunicorn workers, etc. often
# re-import lazily). Loading .env before any local imports means the fail-fast
# check in utils/auth.py sees the real environment, not a partially-loaded one.
load_dotenv()

from apscheduler.schedulers.background import BackgroundScheduler
from models.database import create_tables, SessionLocal
from services.compliance_fetcher import refresh_compliance_alerts
from routes import auth, workflow, compliance, documents, cases, legal_aid, review, citations, statutes, admin, translate

app = FastAPI(
    title="LexSetu API",
    description="AI-powered legal assistant — Auth, Workflow, Compliance, Documents, Case Search, Legal Aid, Review Engine",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://nyayasetu.vercel.app",
    ] + [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()],
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app|https://.*\.onrender\.com)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "false").lower() in ("true", "1")
scheduler = BackgroundScheduler() if ENABLE_SCHEDULER else None


@app.on_event("startup")
def on_startup():
    create_tables()
    print("[LexSetu] Database tables ready.")
    print("[LexSetu] Server ready.")

    if ENABLE_SCHEDULER and scheduler:
        def scheduled_refresh():
            db = SessionLocal()
            try:
                refresh_compliance_alerts(db)
            finally:
                db.close()

        scheduler.add_job(scheduled_refresh, "interval", hours=12, id="compliance_refresh")
        scheduler.start()
        print("[LexSetu] Compliance auto-refresh scheduler started (every 12 hours).")
    else:
        print("[LexSetu] Background scheduler disabled on web node (use Render cron or ENABLE_SCHEDULER=true).")


@app.on_event("shutdown")
def on_shutdown():
    if scheduler and scheduler.running:
        scheduler.shutdown()
        print("[LexSetu] Scheduler stopped.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    print(f"[Error] Unhandled exception on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again."},
    )


# ── Route Registration (Dual Mounting: / and /api) ───────────────────────────
# Mounts routers under both root (e.g. /auth/login) and /api (e.g. /api/auth/login)
# so that reverse proxies (Render, Vercel, Vite, Nginx) work seamlessly whether
# they forward with or without stripping the /api prefix.
api_router = APIRouter(prefix="/api")

_ROUTE_REGISTRY = [
    (auth.router,       "/auth",       ["Authentication"]),
    (workflow.router,   "/workflow",   ["Workflow & Tasks"]),
    (compliance.router, "/compliance", ["Compliance Monitor"]),
    (documents.router,  "/documents",  ["Document Automation"]),
    (cases.router,      "/cases",      ["Case Search"]),
    (legal_aid.router,  "/legal-aid",  ["Legal Aid"]),
    (review.router,     "/review",     ["Legal Draft Review"]),
    (citations.router,  "/citations",  ["Citation Verification"]),
    (statutes.router,   "/statutes",   ["Statutes & India Code"]),
    (admin.router,      "/admin",      ["Admin"]),
    (translate.router,  "/translate",  ["Translation"]),
]

for sub_router, prefix, tags in _ROUTE_REGISTRY:
    app.include_router(sub_router, prefix=prefix, tags=tags)
    api_router.include_router(sub_router, prefix=prefix, tags=tags)


@app.get("/", tags=["Health"])
def root():
    return {
        "app": "LexSetu",
        "tagline": "Bridge to Justice",
        "status": "running",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
@api_router.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
@api_router.get("/health/ready", tags=["Health"])
def readiness():
    """
    Readiness probe for zero-downtime deployment: confirms database and vector store connectivity.
    """
    checks = {}
    is_ready = True

    try:
        from models.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {e}"
        is_ready = False

    try:
        from services.rag import get_qdrant
        client = get_qdrant()
        cols = client.get_collections()
        checks["qdrant"] = f"healthy ({len(cols.collections)} collections)"
    except Exception as e:
        checks["qdrant"] = f"unhealthy: {e}"
        is_ready = False

    status_code = 200 if is_ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "not_ready",
            "checks": checks,
            "version": "1.0.0"
        }
    )


app.include_router(api_router)
