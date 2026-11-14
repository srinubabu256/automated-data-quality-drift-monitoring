"""Tests for ingestion engine, CSV parsing, file hashing, and empty input handling."""
import pytest
from pathlib import Path
from app.ingestion.loader import load_csv, compute_file_hash, FileFormatError
from app.ingestion.batch_manager import BatchManager, DuplicateFileError
from app.models.enums import BatchStatus


def test_normal_ingestion_csv(tmp_path):
    """Test standard valid CSV parsing with line numbering and hashing."""
    csv_file = tmp_path / "valid.csv"
    csv_file.write_text(
        "event_id,transaction_id,customer_id,product_id,event_type,amount,currency,event_timestamp,source_system\n"
        "evt_001,TXN_001,CUST_001,PROD_001,NEW,100.50,USD,2026-11-10T10:00:00Z,PAYMENT_GATEWAY_V1\n"
        "evt_002,TXN_002,CUST_002,PROD_002,NEW,250.00,USD,2026-11-10T10:05:00Z,PAYMENT_GATEWAY_V1\n",
        encoding="utf-8"
    )

    rows, meta = load_csv(csv_file)
    assert len(rows) == 2
    assert meta["record_count"] == 2
    assert meta["is_empty"] is False
    assert len(meta["file_hash"]) == 64
    assert rows[0]["line_number"] == 2
    assert rows[0]["data"]["transaction_id"] == "TXN_001"
    assert rows[1]["data"]["amount"] == "250.00"


def test_empty_input_file(tmp_path):
    """Test ingestion of completely empty file (0 bytes)."""
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("", encoding="utf-8")

    rows, meta = load_csv(empty_file)
    assert len(rows) == 0
    assert meta["record_count"] == 0
    assert meta["is_empty"] is True


def test_empty_headers_only_file(tmp_path):
    """Test ingestion of file with header but 0 data rows."""
    header_file = tmp_path / "header_only.csv"
    header_file.write_text(
        "event_id,transaction_id,customer_id,product_id,event_type,amount,currency,event_timestamp\n",
        encoding="utf-8"
    )

    rows, meta = load_csv(header_file)
    assert len(rows) == 0
    assert meta["record_count"] == 0
    assert meta["is_empty"] is True


def test_missing_required_headers(tmp_path):
    """Test error when required column is missing in CSV header."""
    bad_header_file = tmp_path / "bad_headers.csv"
    bad_header_file.write_text(
        "event_id,transaction_id,amount,currency\n"
        "evt_1,TXN_1,50.00,USD\n",
        encoding="utf-8"
    )

    with pytest.raises(FileFormatError) as exc_info:
        load_csv(bad_header_file)
    assert "Missing required columns" in str(exc_info.value)


def test_batch_manager_run_lifecycle(test_db):
    """Test run creation, state transition, and execution duration calculation."""
    run, is_new = BatchManager.get_or_create_run(
        db=test_db,
        source_file="test.csv",
        file_hash="hash_12345",
        input_count=100
    )
    assert is_new is True
    assert run.status == BatchStatus.PROCESSING
    assert run.input_count == 100

    completed = BatchManager.complete_run(
        db=test_db,
        run_id=run.run_id,
        accepted_count=90,
        rejected_count=5,
        duplicate_count=5,
        processed_count=90
    )
    assert completed.status == BatchStatus.COMPLETED
    assert completed.execution_duration_sec is not None

