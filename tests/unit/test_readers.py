"""Unit tests for CSV and JSON/NDJSON readers."""
import json
import tempfile
from pathlib import Path
import pytest

from app.ingestion.csv_reader import CSVReader, FileFormatError
from app.ingestion.json_reader import JSONReader, JSONFormatError


def test_csv_reader_valid_file():
    content = (
        "event_id,transaction_id,customer_id,product_id,event_type,amount,currency,event_timestamp\n"
        "evt_1,tx_1,cust_1,prod_1,NEW,100.00,USD,2026-11-14T10:00:00Z\n"
    )
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        rows, meta = CSVReader.read_file(tmp_path)
        assert len(rows) == 1
        assert rows[0]["data"]["transaction_id"] == "tx_1"
        assert meta["record_count"] == 1
        assert meta["is_empty"] is False
    finally:
        tmp_path.unlink()


def test_csv_reader_missing_columns():
    content = "event_id,transaction_id,amount\nevt_1,tx_1,100.00\n"
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        with pytest.raises(FileFormatError) as exc_info:
            CSVReader.read_file(tmp_path)
        assert "Missing required columns" in str(exc_info.value)
    finally:
        tmp_path.unlink()


def test_json_reader_array_format():
    data = [
        {"event_id": "evt_1", "transaction_id": "tx_1", "amount": 100.0},
        {"event_id": "evt_2", "transaction_id": "tx_2", "amount": 200.0},
    ]
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
        json.dump(data, tmp)
        tmp_path = Path(tmp.name)

    try:
        rows, meta = JSONReader.read_file(tmp_path)
        assert len(rows) == 2
        assert rows[0]["data"]["transaction_id"] == "tx_1"
        assert rows[1]["data"]["transaction_id"] == "tx_2"
        assert meta["record_count"] == 2
    finally:
        tmp_path.unlink()


def test_json_reader_ndjson_format():
    lines = (
        '{"event_id": "evt_1", "transaction_id": "tx_1", "amount": 50.0}\n'
        '{"event_id": "evt_2", "transaction_id": "tx_2", "amount": 75.0}\n'
    )
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
        tmp.write(lines)
        tmp_path = Path(tmp.name)

    try:
        rows, meta = JSONReader.read_file(tmp_path)
        assert len(rows) == 2
        assert rows[0]["data"]["amount"] == 50.0
        assert rows[1]["data"]["amount"] == 75.0
    finally:
        tmp_path.unlink()


def test_json_reader_empty_file():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
        tmp_path = Path(tmp.name)

    try:
        rows, meta = JSONReader.read_file(tmp_path)
        assert len(rows) == 0
        assert meta["is_empty"] is True
    finally:
        tmp_path.unlink()
