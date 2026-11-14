"""CSV reader and hashing utilities for transaction ingestion."""
import csv
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.core.exceptions import ValidationException

REQUIRED_COLUMNS = [
    "event_id",
    "transaction_id",
    "customer_id",
    "product_id",
    "event_type",
    "amount",
    "currency",
    "event_timestamp",
]


class FileFormatError(ValidationException):
    """Raised when CSV format, encoding, or header is invalid."""


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file for idempotency tracking."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_content_hash(content: bytes) -> str:
    """Compute SHA-256 hash from in-memory bytes."""
    return hashlib.sha256(content).hexdigest()


class CSVReader:
    """Handles structured reading and streaming of CSV files."""

    @classmethod
    def read_file(cls, file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Load a CSV file, validate minimum header requirements, and return rows with metadata.
        Each returned row dict contains:
          - 'line_number': line in file (1-based, 2 is first data line)
          - 'raw_row': raw string of the CSV row
          - 'data': Dict of column values
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = file_path.stat().st_size
        file_hash = compute_file_hash(file_path)

        if file_size == 0:
            return [], {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "file_size": 0,
                "file_hash": file_hash,
                "record_count": 0,
                "is_empty": True,
            }

        rows: List[Dict[str, Any]] = []

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                try:
                    header = next(reader)
                except StopIteration:
                    return [], {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "file_size": file_size,
                        "file_hash": file_hash,
                        "record_count": 0,
                        "is_empty": True,
                    }

                header = [col.strip() for col in header]

                missing = [col for col in REQUIRED_COLUMNS if col not in header]
                if missing:
                    raise FileFormatError(
                        f"Missing required columns in CSV header: {missing}. Present: {header}"
                    )

                for line_num, raw_fields in enumerate(reader, start=2):
                    raw_row_str = ",".join(raw_fields)
                    row_data = {}
                    for i, col_name in enumerate(header):
                        val = raw_fields[i] if i < len(raw_fields) else ""
                        row_data[col_name] = val.strip() if val else None

                    rows.append({
                        "line_number": line_num,
                        "raw_row": raw_row_str,
                        "data": row_data,
                    })

        except UnicodeDecodeError as e:
            raise FileFormatError(f"CSV encoding error (UTF-8 required): {e}")

        metadata = {
            "file_name": file_path.name,
            "file_path": str(file_path),
            "file_size": file_size,
            "file_hash": file_hash,
            "record_count": len(rows),
            "is_empty": len(rows) == 0,
        }

        return rows, metadata


# Backward compatibility helper
load_csv = CSVReader.read_file
