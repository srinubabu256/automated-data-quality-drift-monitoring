"""Main FastAPI application entrypoint."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.routes import alerts, batches, metrics, reports
from app.api.schemas import HealthResponse
from app.config import settings
from app.core.logging import get_logger, setup_logging
from app.database import Base, SessionLocal, engine, init_db
from app.database.models import BaselineProfile
from dashboard.app import dashboard_app

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifespan event handler."""
    logger.info("Initializing database schema...")
    init_db(engine)
    db = SessionLocal()
    try:
        baseline = db.query(BaselineProfile).filter_by(version=settings.BASELINE_VERSION).first()
        if not baseline:
            default_baseline = BaselineProfile(
                version=settings.BASELINE_VERSION,
                baseline_name="Initial Production Baseline",
                record_volume=10000,
                null_rate=0.015,
                mean_amount=150.00,
                std_amount=45.00,
                min_amount=5.00,
                max_amount=1200.00,
                median_amount=140.00,
                p95_amount=230.00,
                event_freshness_sec=3600.0,
                is_active=True,
            )
            db.add(default_baseline)
            db.commit()
            logger.info(f"Seeded default baseline profile {settings.BASELINE_VERSION}")
    finally:
        db.close()
    yield
    logger.info("Application shutdown completed.")


app = FastAPI(
    title="YottaFlex AI – Data Engineering Challenge Solution",
    description="Production-grade local data engineering pipeline handling incremental transaction data, historical metric recomputation, data quality quarantine, baseline drift detection, and explainable alerts.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """System health check endpoint."""
    db_type = "sqlite" if settings.DATABASE_URL.startswith("sqlite") else "postgresql"
    return HealthResponse(
        status="UP",
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc),
        database=db_type,
    )


@app.get("/", include_in_schema=False)
def root():
    """Redirect root to Swagger API documentation."""
    return RedirectResponse(url="/docs")


# Register API v1 Routers
app.include_router(batches.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")

# Mount Dashboard Sub-Application
app.mount("/dashboard", dashboard_app)
