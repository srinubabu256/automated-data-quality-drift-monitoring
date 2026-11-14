"""Centralized Security Utilities (CWE-1236 Formula Injection & Path Sanitization)."""
import re
from pathlib import Path
from typing import Any

# Dangerous leading characters in CSV formula injection (CWE-1236)
DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitizes cell content to prevent CSV/Formula injection attacks (CWE-1236).
    Prepends a single quote (') if the field starts with an active formula character.
    """
    if value is None:
        return ""
    val_str = str(value)
    if val_str.startswith(DANGEROUS_FORMULA_PREFIXES):
        return f"'{val_str}"
    return val_str


def sanitize_filename(filename: str) -> str:
    """
    Sanitizes upload filenames by stripping directory traversal sequences (../, ..\\).
    Returns only the secure basename.
    """
    clean_name = Path(filename).name
    # Strip any non-standard or dangerous characters
    clean_name = re.sub(r"[^\w\.\-\_]", "_", clean_name)
    return clean_name or "unnamed_batch.csv"
