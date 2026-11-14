# Data Dictionary

This document details all database entities, tables, fields, constraints, and relationships implemented in the YottaFlex Data Engineering Solution.

---

## 1. `data_sources`
Tracks upstream ingestion source systems.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER (PK) | No | Auto-incrementing primary key |
| `name` | VARCHAR(64) | No | Unique identifier of source system (e.g., `PAYMENT_GATEWAY_V1`) |
| `system_type` | VARCHAR(64) | No | Classification category (`PAYMENT_PROCESSOR`, `WEB_STORE`, `POINT_OF_SALE`) |
| `created_at` | DATETIME | No | System registration timestamp (UTC) |

---

## 2. `processing_runs`
Tracks batch execution lifecycle, file fingerprints, timing, and accounting metrics.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `run_id` | VARCHAR(64) (PK) | No | Unique execution run identifier (`run_YYYYMMDD_HHMMSS_UUID`) |
| `source_file` | VARCHAR(255) | No | Original input file name or API upload label |
| `file_hash` | VARCHAR(64) | No | SHA-256 hash of raw input file contents (Index) |
| `status` | VARCHAR(32) | No | Execution state: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `RETRIED` |
| `input_count` | INTEGER | No | Total raw records presented in batch |
| `accepted_count` | INTEGER | No | Count of structurally valid, non-duplicate records |
| `rejected_count` | INTEGER | No | Count of quarantined invalid or malformed records |
| `duplicate_count` | INTEGER | No | Count of duplicate event IDs detected |
| `processed_count` | INTEGER | No | Count of state changes applied to transactions |
| `start_time` | DATETIME | No | Pipeline execution start timestamp (UTC) |
| `end_time` | DATETIME | Yes | Pipeline execution completion or failure timestamp (UTC) |
| `execution_duration_sec` | FLOAT | Yes | Elapsed runtime in seconds |
| `failure_reason` | TEXT | Yes | Root-cause error message if status is `FAILED` |
| `created_at` | DATETIME | No | Run creation timestamp (UTC) |

---

## 3. `raw_events`
Immutable record of all accepted and duplicate events ingested.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER (PK) | No | Auto-incrementing primary key |
| `event_id` | VARCHAR(64) | No | Unique event identifier (Unique, Index) |
| `run_id` | VARCHAR(64) (FK) | No | Reference to `processing_runs.run_id` |
| `transaction_id` | VARCHAR(64) | No | Business transaction identifier (Index) |
| `customer_id` | VARCHAR(64) | Yes | Customer reference key (Index) |
| `product_id` | VARCHAR(64) | Yes | Product reference key (Index) |
| `event_type` | VARCHAR(32) | No | Event type: `NEW`, `UPDATE`, `REVERSAL` |
| `amount` | NUMERIC(14, 2) | Yes | Transaction monetary amount |
| `currency` | VARCHAR(3) | Yes | 3-letter currency code (e.g., `USD`) |
| `event_timestamp` | DATETIME | No | Business timestamp when event occurred (UTC, Index) |
| `ingestion_timestamp`| DATETIME | No | System timestamp when event was ingested (UTC) |
| `source_system` | VARCHAR(64) | Yes | Originating system name |
| `source_file` | VARCHAR(255) | Yes | Source file path or name |
| `raw_payload` | TEXT | Yes | Original raw line string or JSON payload |
| `status` | VARCHAR(32) | No | Processing status: `ACCEPTED`, `DUPLICATE` |
| `created_at` | DATETIME | No | Record creation timestamp (UTC) |

---

## 4. `transactions`
Current state dimensional representation of business transactions.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `transaction_id` | VARCHAR(64) (PK) | No | Business transaction primary key |
| `customer_id` | VARCHAR(64) | No | Customer reference key (Index) |
| `product_id` | VARCHAR(64) | No | Product reference key (Index) |
| `current_amount` | NUMERIC(14, 2) | No | Current contributing amount ($0.00 if reversed) |
| `currency` | VARCHAR(3) | No | 3-letter currency code |
| `status` | VARCHAR(32) | No | Transaction state: `ACTIVE`, `REVERSED` |
| `is_reversed` | BOOLEAN | No | Boolean flag indicating whether transaction is reversed |
| `version` | INTEGER | No | Incremental state version number |
| `first_event_timestamp`| DATETIME | No | Business timestamp of the initial event (determines business date) |
| `latest_event_timestamp`| DATETIME| No | Business timestamp of latest applied event |
| `latest_event_id` | VARCHAR(64) | No | Event ID of latest applied event |
| `last_run_id` | VARCHAR(64) | No | Run ID that last modified this transaction |
| `created_at` | DATETIME | No | Row creation timestamp (UTC) |
| `updated_at` | DATETIME | No | Row modification timestamp (UTC) |

---

## 5. `transaction_history`
Append-only audit trail capturing every state change and superseded event.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER (PK) | No | Auto-incrementing primary key |
| `transaction_id` | VARCHAR(64) | No | Reference to `transactions.transaction_id` (Index) |
| `event_id` | VARCHAR(64) | No | Associated event identifier (Index) |
| `event_type` | VARCHAR(32) | No | Action type: `NEW`, `UPDATE`, `REVERSAL`, `UPDATE_SUPERSEDED`, `REVERSAL_DUPLICATE_IGNORED` |
| `previous_amount` | NUMERIC(14, 2) | Yes | Amount prior to event application |
| `new_amount` | NUMERIC(14, 2) | No | Resulting amount after event application |
| `event_timestamp` | DATETIME | No | Business timestamp of the event |
| `applied_at` | DATETIME | No | Timestamp when event was processed (UTC) |
| `run_id` | VARCHAR(64) | No | Execution run ID |

---

## 6. `daily_metrics`
Aggregated business and operational metrics rolled up by business event date.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER (PK) | No | Auto-incrementing primary key |
| `metric_date` | DATE | No | Business event date (Index) |
| `dimension_type` | VARCHAR(32) | No | Dimension slice: `TOTAL`, `PRODUCT`, `CUSTOMER` |
| `dimension_value` | VARCHAR(64) | No | Dimension value (`ALL` or specific ID) |
| `total_transactions` | INTEGER | No | Count of active, contributing transactions on this date |
| `total_amount` | NUMERIC(16, 2) | No | Sum of contributing amounts for active transactions |
| `active_customers` | INTEGER | No | Distinct count of active customers |
| `active_products` | INTEGER | No | Distinct count of active products |
| `avg_amount` | NUMERIC(14, 2) | No | Average amount across active transactions |
| `min_amount` | NUMERIC(14, 2) | No | Minimum transaction amount |
| `max_amount` | NUMERIC(14, 2) | No | Maximum transaction amount |
| `null_rate` | FLOAT | No | Ratio of quarantined records to total activity |
| `record_volume` | INTEGER | No | Total raw event volume observed on this date |
| `event_freshness_sec` | FLOAT | No | Age of latest business event relative to computation |
| `ingestion_freshness_sec`| FLOAT | No | Age of latest ingestion event relative to computation |
| `rejected_count` | INTEGER | No | Number of quarantined records on this date |
| `duplicate_count` | INTEGER | No | Number of duplicate events observed on this date |
| `computed_at` | DATETIME | No | Timestamp of latest recomputation (UTC) |
| `run_id` | VARCHAR(64) | Yes | Run ID that triggered the recomputation |

---

## 7. `baseline_profiles`
Versioned historical operational and statistical profiles.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER (PK) | No | Auto-incrementing primary key |
| `version` | VARCHAR(32) | No | Version code (e.g. `v1.0`, Unique) |
| `baseline_name` | VARCHAR(64) | No | Human-readable name |
| `record_volume` | INTEGER | No | Expected baseline batch record volume |
| `null_rate` | FLOAT | No | Expected baseline null/quarantine proportion |
| `mean_amount` | FLOAT | No | Expected average transaction amount |
| `std_amount` | FLOAT | No | Standard deviation of transaction amounts |
| `min_amount` | FLOAT | No | Expected minimum amount |
| `max_amount` | FLOAT | No | Expected maximum amount |
| `median_amount` | FLOAT | No | Expected median (p50) amount |
| `p95_amount` | FLOAT | No | Expected 95th percentile amount |
| `event_freshness_sec`| FLOAT | No | Expected event freshness in seconds |
| `is_active` | BOOLEAN | No | Active baseline indicator |
| `created_at` | DATETIME | No | Baseline creation timestamp |

---

## 8. `data_quality_profiles`
Per-batch data quality and statistical distribution metrics.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER (PK) | No | Auto-incrementing primary key |
| `run_id` | VARCHAR(64) (FK) | No | Reference to `processing_runs.run_id` (Unique, Index) |
| `batch_volume` | INTEGER | No | Total rows in the incoming batch |
| `null_rate` | FLOAT | No | Proportion of quarantined/invalid records in the batch |
| `mean_amount` | FLOAT | No | Mean amount of accepted batch transactions |
| `std_amount` | FLOAT | No | Standard deviation of accepted batch amounts |
| `min_amount` | FLOAT | No | Minimum amount in the batch |
| `max_amount` | FLOAT | No | Maximum amount in the batch |
| `median_amount` | FLOAT | No | Median amount in the batch |
| `p95_amount` | FLOAT | No | 95th percentile amount in the batch |
| `event_freshness_sec`| FLOAT | No | Freshness in seconds of the latest batch event |
| `created_at` | DATETIME | No | Profile calculation timestamp |

---

## 9. `data_quality_alerts`
Actionable alerts generated when batch profiles exceed baseline thresholds.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `alert_id` | VARCHAR(64) (PK) | No | Unique alert identifier (`alt_UUID`) |
| `run_id` | VARCHAR(64) (FK) | No | Associated execution run ID (Index) |
| `metric_name` | VARCHAR(64) | No | Evaluated metric (`record_volume`, `null_rate`, `mean_amount`) |
| `baseline_value` | FLOAT | No | Expected historical baseline value |
| `current_value` | FLOAT | No | Observed batch value |
| `difference` | FLOAT | No | Absolute difference (`current - baseline`) |
| `pct_change` | FLOAT | No | Percentage change or percentage point shift |
| `severity` | VARCHAR(32) | No | Alert severity level: `INFO`, `WARNING`, `CRITICAL` |
| `explanation` | TEXT | No | Human-readable explanation of the anomaly |
| `suggested_action`| TEXT | No | Actionable investigation instructions for operators |
| `is_resolved` | BOOLEAN | No | Resolution flag (default `False`) |
| `created_at` | DATETIME | No | Alert creation timestamp |

---

## 10. `rejected_records`
Quarantine storage for malformed and invalid records.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER (PK) | No | Auto-incrementing primary key |
| `run_id` | VARCHAR(64) (FK) | No | Associated execution run ID (Index) |
| `source_file` | VARCHAR(255) | No | Source file name |
| `line_number` | INTEGER | Yes | 1-based line number in input file |
| `raw_data` | TEXT | No | Exact raw record data / payload |
| `rejection_reason` | TEXT | No | Human-readable validation failure description |
| `rejection_code` | VARCHAR(64) | No | Standard rejection code (`MISSING_REQUIRED_FIELD`, `INVALID_AMOUNT_VALUE`, etc.) |
| `rejected_at` | DATETIME | No | Quarantine timestamp |

---

## 11. `processing_errors`
Diagnostic log for unexpected pipeline exceptions.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER (PK) | No | Auto-incrementing primary key |
| `run_id` | VARCHAR(64) (FK) | No | Associated execution run ID (Index) |
| `stage` | VARCHAR(64) | No | Processing stage where failure occurred (`LOAD`, `VALIDATE`, `EXECUTION`) |
| `error_type` | VARCHAR(64) | No | Exception class name |
| `error_message` | TEXT | No | Detailed error message |
| `stack_trace` | TEXT | Yes | Full Python traceback |
| `created_at` | DATETIME | No | Error timestamp |

