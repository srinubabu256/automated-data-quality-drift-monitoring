# Platform Limitations & Future Architectural Roadmap

**Project:** Automated Data Quality Profiling & Drift Monitoring Platform  
**Target Audience:** Forward Deployed Engineers, Data Engineers, Platform Evaluators  

---

## 1. Architectural Scope & Current Boundaries

The platform is designed to provide production-grade transaction ingestion, data quality quarantine, historical metric recomputation, and multi-dimensional statistical drift detection within a lightweight, local-first Python architecture.

To balance zero-dependency local operability with enterprise design patterns, the current implementation operates under specific known trade-offs detailed below.

---

## 2. Identified Platform Limitations

### 2.1 Database & Concurrency (SQLite In-Process Engine)
- **Single-Writer Constraint**: SQLite utilizes database-level locking during write operations (`BEGIN IMMEDIATE`). While readers execute concurrently using WAL mode (`PRAGMA journal_mode=WAL`), high-throughput concurrent batch writes will encounter lock contention or timeout.
- **Production Path**: The platform includes native support for PostgreSQL via `DATABASE_URL=postgresql://...`. For high-concurrency production deployments, switching to PostgreSQL enables connection pooling (`pgbouncer`), row-level locking, and distributed multi-worker ingestion.

### 2.2 In-Memory Batch Scale Boundaries
- **Batch Processing Volume**: The current in-memory processing pipeline (`TransactionProcessor`) comfortably handles batches up to **100,000 records** in under 5 minutes with ~760 MB RAM. For batches exceeding 500,000+ records in a single payload, memory utilization scales linearly without generator-based chunking.
- **Production Path**: Implement streaming generators (`pd.read_csv(chunksize=10000)`) and database copy operations (`COPY FROM` in PostgreSQL) for multi-million row batch files.

### 2.3 Statistical Assumptions & Sample Sizes
- **Chi-Square Goodness-of-Fit**: Chi-Square calculations enforce the **Cochran condition** ($E_i \ge 5$ across at least 80% of categories). For small batch sizes ($N < 30$) or highly sparse categorical columns with high cardinality (e.g., UUIDs or free-text descriptions), the test is appropriately skipped to prevent false positive alerts.
- **Kolmogorov-Smirnov (KS) Sensitivity**: The 2-sample KS test has high statistical power with large sample sizes ($N > 50,000$). At large scale, trivial differences in distribution shape may yield $p < 0.05$. The platform mitigates this by coupling the KS test with the Population Stability Index (PSI) to separate statistical significance from operational impact ($PSI \ge 0.20$).

### 2.4 Freshness Monitoring Scope
- **Latency Tracking**: Event freshness is measured as the elapsed latency between the latest event timestamp ($t_{\text{event}}$) and current system time ($t_{\text{current}}$).
- **Scheduled SLA Monitoring**: Arrival-schedule freshness alerts require explicit configuration of expected cron schedules (`cron` expressions or hourly SLA thresholds). Without an arrival schedule, freshness alerts evaluate whether incoming events arrive older than `ALERT_FRESHNESS_MAX_SEC` (default: 24 hours).

### 2.5 Single-Node Local Execution
- **Distributed Processing**: The current deployment runs on a single node (FastAPI, Uvicorn, Streamlit). It does not use distributed orchestrators like Apache Spark, Apache Flink, or Ray. This is an intentional hackathon design decision to preserve local reproducibility without heavyweight container infrastructure.

---

## 3. Future Enhancements Roadmap

1. **Distributed Queue Ingestion**: Introduce Apache Kafka or AWS SQS consumer workers to stream events directly into the `IngestionPipeline`.
2. **PostgreSQL Distributed Sharding**: Implement time-based table partitioning on `daily_metrics` and `raw_events` using `pg_partman`.
3. **Automated Baseline Promotion**: Add approval workflows with webhooks allowing data stewards to promote approved batch profiles to production baselines with one click.
4. **Interactive Schema Evolution**: Provide automated migration generators for backward-compatible schema changes (e.g., adding nullable columns).
5. **OpenTelemetry & Prometheus Exporter**: Expose a Prometheus `/metrics` scrape endpoint for pipeline duration, PSI drift values, and quarantine counts.

