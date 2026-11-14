"""Tests for FastAPI endpoints and route handlers."""
import io
import pytest
from fastapi import UploadFile, HTTPException
from app.main import health_check
from app.api.routes import batches, metrics, alerts, reports
from app.models.database_models import ProcessingRun


def test_health_endpoint():
    """Verify /health returns UP status and database type."""
    res = health_check()
    assert res.status == "UP"
    assert res.environment is not None
    assert res.database in ["sqlite", "postgresql"]


def test_batch_upload_and_reporting_lifecycle(test_db):
    """Verify upload route processes CSV, enforces duplicate detection, and reports metrics."""
    csv_content = (
        "event_id,transaction_id,customer_id,product_id,event_type,amount,currency,event_timestamp\n"
        "evt_api_1,TXN_API_1,CUST_001,PROD_001,NEW,150.00,USD,2026-11-10T10:00:00Z\n"
        "evt_api_2,TXN_API_2,CUST_002,PROD_002,NEW,250.00,USD,2026-11-10T10:30:00Z\n"
    )

    # 1. Test POST /upload
    upload_file = UploadFile(
        filename="test_api_batch.csv",
        file=io.BytesIO(csv_content.encode("utf-8"))
    )
    res = batches.upload_batch_file(file=upload_file, allow_rerun=False, db=test_db)
    assert res.status == "COMPLETED"
    assert res.input_count == 2
    assert res.accepted_count == 2
    assert res.reconciliation_passed is True
    run_id = res.run_id

    # 2. Test Duplicate Upload (raises HTTP 409 Conflict)
    upload_file_dup = UploadFile(
        filename="test_api_batch.csv",
        file=io.BytesIO(csv_content.encode("utf-8"))
    )
    with pytest.raises(HTTPException) as exc_info:
        batches.upload_batch_file(file=upload_file_dup, allow_rerun=False, db=test_db)
    assert exc_info.value.status_code == 409

    # 3. Test GET /batches
    batch_list = batches.list_batches(status_filter=None, limit=50, offset=0, db=test_db)
    assert len(batch_list) >= 1
    assert any(b.run_id == run_id for b in batch_list)

    # 4. Test GET /batches/{run_id}
    run_detail = batches.get_batch_by_id(run_id=run_id, db=test_db)
    assert run_detail.run_id == run_id
    assert run_detail.status == "COMPLETED"

    # 5. Test GET /metrics/daily
    daily_list = metrics.get_daily_metrics(start_date=None, end_date=None, dimension="TOTAL", limit=100, db=test_db)
    assert len(daily_list) >= 1
    assert daily_list[0].total_transactions == 2
    assert float(daily_list[0].total_amount) == 400.00

    # 6. Test GET /reports/reconciliation
    recon = reports.get_reconciliation_report(run_id=run_id, db=test_db)
    assert recon["reconciled"] is True
    assert recon["status"] in ["SUCCESS", "BALANCED"]
    assert recon["counts"]["input_count"] == 2

    # 7. Test GET /rejected-records
    rejected = reports.get_rejected_records(run_id=run_id, limit=50, offset=0, db=test_db)
    assert isinstance(rejected, list)

    # 8. Test GET /alerts
    alert_list = alerts.get_alerts(run_id=run_id, severity=None, limit=50, db=test_db)
    assert isinstance(alert_list, list)
