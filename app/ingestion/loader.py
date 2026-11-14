"""Backward-compatible loader interface re-exporting from csv_reader."""
from app.ingestion.csv_reader import (
    REQUIRED_COLUMNS,
    CSVReader,
    FileFormatError,
    compute_content_hash,
    compute_file_hash,
    load_csv,
)

__all__ = [
    "REQUIRED_COLUMNS",
    "CSVReader",
    "FileFormatError",
    "compute_content_hash",
    "compute_file_hash",
    "load_csv",
]
