"""JSON and NDJSON file reader for transaction ingestion."""
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.core.exceptions import ValidationException
from app.ingestion.csv_reader import REQUIRED_COLUMNS, compute_file_hash


class JSONFormatError(ValidationException):
    """Raised when JSON/NDJSON file is corrupted or lacks mandatory schema fields."""


class JSONReader:
    """Handles structured reading and streaming of JSON and NDJSON transaction payloads."""

    @classmethod
    def read_file(cls, file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Reads a JSON or NDJSON file, returning normalized rows with metadata.
        Supports:
          1. Standard JSON list of objects: [ { ... }, { ... } ]
          2. Newline-delimited JSON (NDJSON): { ... }\n{ ... }
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
                content = f.read().strip()
                if not content:
                    return [], {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "file_size": file_size,
                        "file_hash": file_hash,
                        "record_count": 0,
                        "is_empty": True,
                    }

                # Try parsing as standard JSON array first
                if content.startswith("["):
                    try:
                        parsed_list = json.loads(content)
                        if not isinstance(parsed_list, list):
                            raise JSONFormatError("JSON root must be an array of objects.")

                        for idx, item in enumerate(parsed_list, start=1):
                            if not isinstance(item, dict):
                                continue
                            raw_str = json.dumps(item)
                            rows.append({
                                "line_number": idx,
                                "raw_row": raw_str,
                                "data": item,
                            })
                    except json.JSONDecodeError as e:
                        raise JSONFormatError(f"Malformed JSON document: {e}")
                else:
                    # Parse as NDJSON (line by line)
                    for line_num, line in enumerate(content.splitlines(), start=1):
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            item = json.loads(line_str)
                            if isinstance(item, dict):
                                rows.append({
                                    "line_number": line_num,
                                    "raw_row": line_str,
                                    "data": item,
                                })
                        except json.JSONDecodeError as e:
                            raise JSONFormatError(f"Malformed NDJSON at line {line_num}: {e}")

        except UnicodeDecodeError as e:
            raise JSONFormatError(f"JSON encoding error (UTF-8 required): {e}")

        metadata = {
            "file_name": file_path.name,
            "file_path": str(file_path),
            "file_size": file_size,
            "file_hash": file_hash,
            "record_count": len(rows),
            "is_empty": len(rows) == 0,
        }

        return rows, metadata
