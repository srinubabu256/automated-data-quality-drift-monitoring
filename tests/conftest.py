"""Pytest fixtures for database isolation and API testing."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.models.database_models import DataSource, BaselineProfile
from app.main import app


@pytest.fixture(scope="function")
def test_db():
    """Provides a fresh, isolated in-memory SQLite database for each test function."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Seed baseline profile v1.0
    baseline = BaselineProfile(
        version="v1.0",
        baseline_name="Test Baseline Profile",
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
    session.add(baseline)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    """FastAPI TestClient with overridden database dependency."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
