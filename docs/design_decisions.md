# Architectural Design Decisions and Trade-offs

This document outlines the key technical design decisions made in building the YottaFlex Data Engineering Solution.

---

## 1. Local-First Engine: SQLite Default with PostgreSQL Compatibility

### Decision
Use SQLite as the zero-dependency local default database while providing drop-in PostgreSQL support through SQLAlchemy URL configuration (`DATABASE_URL`).

### Rationale & Trade-offs
- **Zero Friction**: Evaluators and developers can clone and execute tests immediately without provisioning Docker, local database services, or cloud infrastructure.
- **Production Portability**: By using standard SQLAlchemy ORM abstractions, switching to enterprise PostgreSQL in staging/production requires only setting `DATABASE_URL=postgresql+psycopg2://user:password@host:5432/db`.
- **Constraint Enforcement**: SQLite foreign keys (`PRAGMA foreign_keys = ON`) are enabled explicitly to match PostgreSQL relational guarantees.

---

## 2. Separation of Event History from Current State

### Decision
Store raw incoming events in `raw_events`, audit state changes in `transaction_history`, and maintain current dimensional values in `transactions`.

### Rationale & Trade-offs
- **Current State Query Efficiency**: Analytical queries and daily metric recomputations need the latest state (`current_amount`, `is_reversed`) without executing an expensive `GROUP BY` or window function over millions of historical events.
- **Auditability & Traceability**: Preserving every raw payload in `raw_events` and every applied transition in `transaction_history` ensures complete auditability for forensic compliance.
- **Space vs. Compute Trade-off**: Storing both history and current state uses slightly more storage, but reduces query time from $O(E)$ (total events) to $O(T)$ (distinct transactions).

---

## 3. SHA-256 Payload Hashing for Batch Idempotency

### Decision
Use SHA-256 content hashing of incoming batch files rather than relying on file names.

### Rationale & Trade-offs
- **File Name Fragility**: Upstream ETL tools frequently rename files (e.g. `data.csv` -> `data_processed.csv` or `batch_20261110_copy.csv`). File name checks produce false positives or false negatives.
- **Content Integrity**: A cryptographic content hash uniquely identifies the dataset payload. Submitting the exact same data twice is detected with certainty regardless of file naming.
- **Transactional Atomicity**: Processing runs are staged in `processing_runs`. If a run fails midway, the transaction rolls back cleanly, allowing safe retries.

---

## 4. Targeted Selective Historical Recomputation

### Decision
Identify distinct business event dates affected by the batch and recompute daily metrics only for those specific dates.

### Rationale & Trade-offs
- **Late Arrivals**: When an event from 10 days ago arrives in today's batch, recalculating the entire historical table across years of data is computationally wasteful.
- **Selective Upsert**: By collecting `affected_dates = {event.event_timestamp.date()}`, the engine queries and upserts only the dates that actually changed.
- **Performance**: Keeps recomputation time constant relative to the number of affected days, rather than scaling with total historical volume.

---

## 5. Explainable Drift Detection vs. Black-Box ML

### Decision
Implement explainable statistical threshold comparisons (percentage change, percentage point shift, quantile comparisons) for anomaly alerts rather than unsupervised ML clustering or neural anomaly detectors.

### Rationale & Trade-offs
- **Explainability**: Data engineers on-call need immediate, unambiguous diagnostic messages (e.g., *"Batch volume dropped by 70.0% compared to baseline"*) and concrete action steps.
- **Reproducibility**: Statistical rules behave deterministically and do not suffer from cold-start problems, concept drift, or model training instability.
- **Configurability**: Thresholds can be fine-tuned via environment variables without retraining models.

