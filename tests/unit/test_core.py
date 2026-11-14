"""Unit tests for Core module (exceptions, security, logging)."""
import pytest
from app.core.exceptions import (
    YottaFlexException,
    ValidationException,
    SchemaDriftException,
    DuplicateBatchException,
)
from app.core.security import sanitize_csv_cell, sanitize_filename
from app.core.logging import setup_logging, get_logger


def test_exception_formatting():
    exc = ValidationException("Invalid currency", details="XYZ not in ISO 4217")
    assert "Invalid currency (XYZ not in ISO 4217)" in str(exc)
    assert isinstance(exc, YottaFlexException)


def test_security_cwe1236_formula_sanitization():
    # Formula characters prepended with '
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("+cmd|'/c calc'!A0") == "'+cmd|'/c calc'!A0"
    assert sanitize_csv_cell("-100") == "'-100"
    assert sanitize_csv_cell("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_csv_cell("\tTAB") == "'\tTAB"
    # Normal content remains clean
    assert sanitize_csv_cell("USD") == "USD"
    assert sanitize_csv_cell("150.00") == "150.00"
    assert sanitize_csv_cell(None) == ""


def test_security_filename_sanitization():
    # Strips directory traversal
    assert sanitize_filename("../../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32.csv") == "system32.csv"
    assert sanitize_filename("safe_batch_123.csv") == "safe_batch_123.csv"


def test_core_logging():
    setup_logging(level="DEBUG")
    log = get_logger("test_core")
    assert log is not None
