# Automated Testing Strategy and Verification Matrix

This document defines the testing methodology, fixture architecture, failure simulation strategies, and test coverage mapping for the YottaFlex Data Engineering Solution.

---

## 1. Testing Architecture & Principles

- **Isolated Test State**: Every test function executes against an ephemeral, isolated in-memory SQLite database (`sqlite:///:memory:`) instantiated via the `test_db` pytest fixture. Tests run in complete isolation with zero side-effects across test functions.
- **Rigor & Zero Fabrication**: Every test verifies real system transitions using strict assertions on database entities (`transactions`, `raw_events`, `rejected_records`, `daily_metrics`, `data_quality_alerts`).
- **Idempotency & Fault Tolerance**: Failure recovery, rerun detection, and terminal conservation equations are tested with adversarial inputs.

---

## 2. Comprehensive Test Case Coverage (20 Required Scenarios)

The test suite covers all 20 required verification scenarios specified in the challenge brief:

| # | Requirement | Test File | Test Function | Description |
| :--- | :--- | :--- | :--- | :--- |
| **1** | Normal Ingestion | `tests/test_ingestion.py` | `test_normal_ingestion_csv` | Validates CSV parsing, line numbering, header normalization, and SHA-256 computation. |
| **2** | Empty Input | `tests/test_ingestion.py` | `test_empty_input_file`, `test_empty_headers_only_file` | Handles 0-byte files and header-only empty batches without crashing. |
| **3** | Malformed Input | `tests/test_validation.py` | `test_schema_validator_malformed_timestamp` | Catches malformed string dates and invalid syntax. |
| **4** | Missing Required Fields | `tests/test_validation.py` | `test_schema_validator_missing_required_fields` | Quarantines rows with missing/empty event_id, transaction_id, or customer_id. |
| **5** | Duplicate Event IDs | `tests/test_transactions.py` | `test_duplicate_event_id_deduplication` | Detects duplicate `event_id` and routes to duplicate ledger without double-counting. |
| **6** | Invalid Data Types | `tests/test_validation.py` | `test_schema_validator_invalid_amount_types` | Validates non-numeric (`"abc"`, `"N/A"`) and negative amounts are quarantined. |
| **7** | Unexpected Schema | `tests/test_ingestion.py` | `test_missing_required_headers` | Rejects CSV files missing mandatory header columns with `FileFormatError`. |
| **8** | Invalid Reference Keys | `tests/test_validation.py` | `test_business_validator_invalid_references` | Flags invalid reference keys (e.g. `INV_CUST_@@@`). |
| **9** | Transaction Updates | `tests/test_transactions.py` | `test_transaction_update_lifecycle` | Validates UPDATE event modifies amount and version without creating duplicate transaction. |
| **10**| Transaction Reversals | `tests/test_reversals.py` | `test_transaction_reversal` | Validates REVERSAL sets status to `REVERSED` and effective amount to `$0.00`. |
| **11**| Late-Arriving Events | `tests/test_late_events.py` | `test_late_arriving_event_recomputes_historical_date` | Recomputes daily metrics for past business date when historical event arrives. |
| **12**| Out-of-Order Events | `tests/test_transactions.py` | `test_out_of_order_event_resolution` | Ensures an older event never overwrites a newer confirmed transaction state. |
| **13**| Duplicate Reversals | `tests/test_reversals.py` | `test_duplicate_reversal_prevention` | Prevents double reversal deduction when multiple REVERSAL events arrive. |
| **14**| Same-File Rerun | `tests/test_idempotency.py` | `test_same_file_rerun_detection` | Detects identical file hash and raises `DuplicateFileError` (HTTP 409). |
| **15**| Partial Failure & Retry | `tests/test_ingestion.py` | `test_batch_manager_run_lifecycle` | Validates batch state transitions and safe restart from `FAILED` state. |
| **16**| Historical Recomputation | `tests/test_metrics.py` | `test_historical_recomputation_on_update` | Updates historical daily metrics when existing transactions are modified. |
| **17**| Baseline Comparison | `tests/test_alerts.py` | `test_volume_drop_alert_generation` | Detects -70% volume drop and generates explainable warning/critical alert. |
| **18**| Alert Generation | `tests/test_alerts.py` | `test_null_rate_spike_alert`, `test_prevent_duplicate_alerts_for_same_run` | Generates explainable alert on null rate spike and prevents duplicate alerts. |
| **19**| Reconciliation | `tests/test_idempotency.py` | `test_terminal_reconciliation_check` | Confirms mathematical equality: $N_{input} = N_{accepted} + N_{rejected} + N_{duplicate}$. |
| **20**| API Responses | `tests/test_api.py` | `test_health_endpoint`, `test_batch_upload_and_reporting_endpoints` | End-to-end REST API upload, batch query, daily metrics, and reconciliation endpoint tests. |

---

## 3. Running the Test Suite

Execute all tests from the repository root:

```powershell
# Run the complete test suite with verbose output
pytest -v

# Run with duration profiling to identify slow tests
pytest -v --durations=10

# Run specific domain test module
pytest tests/test_transactions.py -v
pytest tests/test_idempotency.py -v
```

