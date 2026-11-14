"""CSV File Loader and hashing utilities for transaction ingestion."""
import csv
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple


REQUIRED_COLUMNS = [
    "event_id",
    "transaction_id",
    "customer_id",
    "product_id",
    "event_type",
    "amount",
    "currency",
    "event_timestamp"
]


class FileFormatError(Exception):
    """Raised when CSV format, encoding, or header is invalid."""
    pass


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


def load_csv(file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
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
        with open(file_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader, None)

            if header is None:
                return [], {
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "file_size": file_size,
                    "file_hash": file_hash,
                    "record_count": 0,
                    "is_empty": True,
                }

            # Normalize headers (strip whitespace and lowercase)
            header_clean = [col.strip() for col in header]

            # Verify required columns exist
            missing_cols = [c for c in REQUIRED_COLUMNS if c not in header_clean]
            if missing_cols:
                raise FileFormatError(f"Missing required columns in CSV header: {missing_cols}")

            for line_idx, row in enumerate(reader, start=2):
                # Handle blank lines
                if not row or not any(row):
                    continue

                # Map to dictionary
                if len(row) < len(header_clean):
                    # Pad missing columns with empty string
                    row = row + [""] * (len(header_clean) - len(row))
                elif len(row) > len(header_clean):
                    # Truncate unexpected extra columns or preserve
                    row = row[:len(header_clean)]

                row_dict = dict(zip(header_clean, row))
                rows.append({
                    "line_number": line_idx,
                    "raw_row": ",".join(row),
                    "data": row_dict
                })

    except UnicodeDecodeError as e:
        raise FileFormatError(f"File encoding error: {e}")

    return rows, {
        "file_name": file_path.name,
        "file_path": str(file_path),
        "file_size": file_size,
        "file_hash": file_hash,
        "record_count": len(rows),
        "is_empty": len(rows) == 0,
    }

