-- ==============================================================================
-- YottaFlex Automated Data Quality Profiling & Drift Monitoring Platform
-- Relational Database DDL Schema (SQLite / PostgreSQL ANSI Compatible)
-- ==============================================================================

-- 1. Baseline Profiles (Versioned historical reference baselines)
CREATE TABLE IF NOT EXISTS baseline_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version VARCHAR(32) NOT NULL UNIQUE,
    baseline_name VARCHAR(64) NOT NULL,
    record_volume INTEGER NOT NULL,
    null_rate FLOAT NOT NULL,
    mean_amount FLOAT NOT NULL,
    std_amount FLOAT NOT NULL,
    min_amount FLOAT NOT NULL,
    max_amount FLOAT NOT NULL,
    median_amount FLOAT NOT NULL,
    p95_amount FLOAT NOT NULL,
    event_freshness_sec FLOAT NOT NULL,
    column_baselines TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Upstream Data Sources
CREATE TABLE IF NOT EXISTS data_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(64) NOT NULL UNIQUE,
    system_type VARCHAR(64) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Ingestion Processing Runs (Audit ledger & idempotency control)
CREATE TABLE IF NOT EXISTS processing_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    source_file VARCHAR(255) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    processed_count INTEGER NOT NULL DEFAULT 0,
    start_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time DATETIME,
    execution_duration_sec FLOAT,
    failure_reason TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_processing_runs_file_hash ON processing_runs (file_hash);

-- 4. Transactions (Current dimensional state)
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    product_id VARCHAR(64) NOT NULL,
    current_amount NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    is_reversed BOOLEAN NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    first_event_timestamp DATETIME NOT NULL,
    latest_event_timestamp DATETIME NOT NULL,
    latest_event_id VARCHAR(64) NOT NULL,
    last_run_id VARCHAR(64) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_transactions_customer_id ON transactions (customer_id);
CREATE INDEX IF NOT EXISTS ix_transactions_product_id ON transactions (product_id);
CREATE INDEX IF NOT EXISTS idx_tx_customer_product ON transactions (customer_id, product_id);
CREATE INDEX IF NOT EXISTS idx_tx_status_updated ON transactions (status, updated_at);

-- 5. Transaction History (Append-only state transition audit log)
CREATE TABLE IF NOT EXISTS transaction_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    previous_amount NUMERIC(14, 2),
    new_amount NUMERIC(14, 2) NOT NULL,
    event_timestamp DATETIME NOT NULL,
    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_id VARCHAR(64) NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES transactions (transaction_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_transaction_history_transaction_id ON transaction_history (transaction_id);
CREATE INDEX IF NOT EXISTS ix_transaction_history_event_id ON transaction_history (event_id);
CREATE INDEX IF NOT EXISTS idx_tx_hist_tx_id ON transaction_history (transaction_id, event_timestamp);

-- 6. Daily Business Metrics (Aggregated financial metrics by date & dimension)
CREATE TABLE IF NOT EXISTS daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_date DATE NOT NULL,
    dimension_type VARCHAR(32) NOT NULL,
    dimension_value VARCHAR(64) NOT NULL,
    total_transactions INTEGER NOT NULL,
    total_amount NUMERIC(16, 2) NOT NULL,
    active_customers INTEGER NOT NULL,
    active_products INTEGER NOT NULL,
    avg_amount NUMERIC(14, 2) NOT NULL,
    min_amount NUMERIC(14, 2) NOT NULL,
    max_amount NUMERIC(14, 2) NOT NULL,
    null_rate FLOAT NOT NULL,
    record_volume INTEGER NOT NULL,
    event_freshness_sec FLOAT NOT NULL,
    ingestion_freshness_sec FLOAT NOT NULL,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_id VARCHAR(64),
    CONSTRAINT uq_daily_metric_date_dim UNIQUE (metric_date, dimension_type, dimension_value)
);
CREATE INDEX IF NOT EXISTS ix_daily_metrics_metric_date ON daily_metrics (metric_date);
CREATE INDEX IF NOT EXISTS idx_daily_metric_date ON daily_metrics (metric_date);

-- 7. Raw Events (Immutable audit ledger of all ingested event payloads)
CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id VARCHAR(64) NOT NULL,
    run_id VARCHAR(64) NOT NULL,
    transaction_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64),
    product_id VARCHAR(64),
    event_type VARCHAR(32) NOT NULL,
    amount NUMERIC(14, 2),
    currency VARCHAR(3),
    event_timestamp DATETIME NOT NULL,
    ingestion_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system VARCHAR(64),
    source_file VARCHAR(255),
    raw_payload TEXT,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES processing_runs (run_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_raw_events_event_id ON raw_events (event_id);
CREATE INDEX IF NOT EXISTS ix_raw_events_run_id ON raw_events (run_id);
CREATE INDEX IF NOT EXISTS ix_raw_events_transaction_id ON raw_events (transaction_id);
CREATE INDEX IF NOT EXISTS ix_raw_events_customer_id ON raw_events (customer_id);
CREATE INDEX IF NOT EXISTS ix_raw_events_product_id ON raw_events (product_id);
CREATE INDEX IF NOT EXISTS ix_raw_events_event_timestamp ON raw_events (event_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_event_tx_type ON raw_events (transaction_id, event_type);

-- 8. Quarantined Rejected Records (Failed records with line numbers & error codes)
CREATE TABLE IF NOT EXISTS rejected_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(64) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    line_number INTEGER,
    raw_data TEXT NOT NULL,
    rejection_reason TEXT NOT NULL,
    rejection_code VARCHAR(64) NOT NULL,
    rejected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES processing_runs (run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_rejected_records_run_id ON rejected_records (run_id);

-- 9. Batch Data Quality Profiles (Descriptive statistical profiles per run)
CREATE TABLE IF NOT EXISTS data_quality_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(64) NOT NULL UNIQUE,
    batch_volume INTEGER NOT NULL,
    null_rate FLOAT NOT NULL,
    mean_amount FLOAT NOT NULL,
    std_amount FLOAT NOT NULL,
    min_amount FLOAT NOT NULL,
    max_amount FLOAT NOT NULL,
    median_amount FLOAT NOT NULL,
    p95_amount FLOAT NOT NULL,
    event_freshness_sec FLOAT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES processing_runs (run_id) ON DELETE CASCADE
);

-- 10. Multi-Dimensional Drift Analysis Results (Statistical tests & p-values)
CREATE TABLE IF NOT EXISTS drift_analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(64) NOT NULL,
    baseline_version VARCHAR(32) NOT NULL,
    drift_type VARCHAR(64) NOT NULL,
    column_name VARCHAR(64),
    detection_method VARCHAR(64) NOT NULL,
    baseline_value FLOAT,
    current_value FLOAT,
    absolute_difference FLOAT,
    percentage_difference FLOAT,
    statistical_statistic FLOAT,
    p_value FLOAT,
    degrees_of_freedom INTEGER,
    drift_detected BOOLEAN NOT NULL DEFAULT 0,
    severity VARCHAR(32) NOT NULL DEFAULT 'NONE',
    threshold FLOAT,
    details TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES processing_runs (run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_drift_analysis_results_run_id ON drift_analysis_results (run_id);
CREATE INDEX IF NOT EXISTS ix_drift_analysis_results_column_name ON drift_analysis_results (column_name);
CREATE INDEX IF NOT EXISTS ix_drift_analysis_results_drift_type ON drift_analysis_results (drift_type);

-- 11. Explainable Data Quality Alerts (Actionable operational notifications)
CREATE TABLE IF NOT EXISTS data_quality_alerts (
    alert_id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    dataset_name VARCHAR(128) DEFAULT 'transactions',
    column_name VARCHAR(64),
    drift_type VARCHAR(64),
    metric_name VARCHAR(64) NOT NULL,
    detection_method VARCHAR(64),
    baseline_value FLOAT NOT NULL,
    current_value FLOAT NOT NULL,
    difference FLOAT NOT NULL,
    pct_change FLOAT NOT NULL,
    statistical_statistic FLOAT,
    p_value FLOAT,
    configured_threshold FLOAT,
    severity VARCHAR(32) NOT NULL,
    explanation TEXT NOT NULL,
    suggested_action TEXT NOT NULL,
    is_resolved BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_run_metric_alert UNIQUE (run_id, metric_name),
    FOREIGN KEY (run_id) REFERENCES processing_runs (run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_data_quality_alerts_run_id ON data_quality_alerts (run_id);
CREATE INDEX IF NOT EXISTS ix_data_quality_alerts_column_name ON data_quality_alerts (column_name);
CREATE INDEX IF NOT EXISTS ix_data_quality_alerts_drift_type ON data_quality_alerts (drift_type);

-- 12. Processing Errors (Detailed execution failure diagnostics)
CREATE TABLE IF NOT EXISTS processing_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(64) NOT NULL,
    stage VARCHAR(64) NOT NULL,
    error_type VARCHAR(64) NOT NULL,
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES processing_runs (run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_processing_errors_run_id ON processing_errors (run_id);

