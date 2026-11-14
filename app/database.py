"""Backward-compatible database connection interface."""
from app.database.connection import (
    Base,
    SessionLocal,
    engine,
    get_db,
    init_db,
)

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "init_db",
]
