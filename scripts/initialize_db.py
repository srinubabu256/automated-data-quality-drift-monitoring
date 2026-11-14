"""Database initialization script: creates tables, indexes, and seeds baseline profiles."""
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.database import engine, init_db, SessionLocal
from app.models.database_models import DataSource, BaselineProfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("initialize_db")


def seed_defaults(session):
    """Seed initial data sources and baseline profile."""
    # Seed default data source
    existing_source = session.query(DataSource).filter_by(name="CSV_BATCH_DEFAULT").first()
    if not existing_source:
        default_source = DataSource(
            name="CSV_BATCH_DEFAULT",
            system_type="CSV_BATCH",
            created_at=datetime.now(timezone.utc),
        )
        session.add(default_source)
        logger.info("Seeded default data source 'CSV_BATCH_DEFAULT'.")

    # Seed initial baseline profile v1.0
    existing_baseline = session.query(BaselineProfile).filter_by(version=settings.BASELINE_VERSION).first()
    if not existing_baseline:
        baseline = BaselineProfile(
            version=settings.BASELINE_VERSION,
            baseline_name="Standard Production Baseline",
            record_volume=1000,
            null_rate=0.02,
            mean_amount=150.0,
            std_amount=50.0,
            min_amount=5.0,
            max_amount=500.0,
            median_amount=140.0,
            p95_amount=300.0,
            event_freshness_sec=3600.0,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(baseline)
        logger.info(f"Seeded baseline profile: {settings.BASELINE_VERSION}")

    session.commit()


def main():
    logger.info("Initializing database...")
    settings.resolve_paths()
    init_db()
    logger.info("Tables created or verified successfully.")

    session = SessionLocal()
    try:
        seed_defaults(session)
        logger.info("Database initialization completed successfully.")
    except Exception as e:
        session.rollback()
        logger.error(f"Error seeding database: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
