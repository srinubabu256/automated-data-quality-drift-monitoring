# Business Rules and Conflict Resolution Policies

This document formalizes the domain rules, deterministic ordering strategies, conflict-resolution policies, and data quality thresholds implemented in the YottaFlex Data Engineering Solution.

---

## 1. Event Identification and Uniqueness

1. **`event_id`**: Universally unique identifier for an event transmission.
   - An `event_id` must be processed at most once into active transaction state.
   - Duplicate occurrences of an `event_id` within the same batch or across batches are classified as `DUPLICATE` and quarantined into the duplicate ledger. They never affect financial metrics twice.
2. **`transaction_id`**: Identifies the business transaction entity across its complete lifecycle (`NEW`, `UPDATE`, `REVERSAL`).
   - Multiple events may share the same `transaction_id`, representing sequential state updates or cancellations.

---

## 2. Event Ordering and Conflict Resolution

Because distributed message queues and external files can deliver events out-of-order, the engine applies a **deterministic sorting and conflict-resolution policy**:

### 2.1 Deterministic Batch Ordering
Before applying state mutations, all accepted events within a batch are sorted by:
1. `event_timestamp` ascending.
2. `event_type` priority: `NEW (0) -> UPDATE (1) -> REVERSAL (2)`.
3. `event_id` ascending as a deterministic tie-breaker.

### 2.2 Conflict Resolution Matrix

| Existing State | Incoming Event | Resolution Action | Ledger History Status |
| :--- | :--- | :--- | :--- |
| **None** | `NEW` | Create `Transaction` with `status="ACTIVE"`, `version=1`, `current_amount=amount`. | `NEW` |
| **None** | `UPDATE` | Out-of-order arrival: create `Transaction` with `status="ACTIVE"`, `version=1`. | `UPDATE` |
| **None** | `REVERSAL` | Out-of-order arrival: create `Transaction` with `status="REVERSED"`, `current_amount=0.00`. | `REVERSAL` |
| **ACTIVE** | `NEW` | Duplicate creation attempt: preserve current state without creating a second transaction. | `NEW_DUPLICATE_IGNORED` |
| **ACTIVE** | `UPDATE` ($t_{event} \ge t_{latest}$) | Normal update: update `current_amount`, update `latest_event_timestamp`, increment `version`. | `UPDATE` |
| **ACTIVE** | `UPDATE` ($t_{event} < t_{latest}$) | **Superseded event**: An older event MUST NOT overwrite a newer valid state. Current state is preserved. | `UPDATE_SUPERSEDED` |
| **ACTIVE** | `REVERSAL` | Mark `status="REVERSED"`, `is_reversed=True`, set contributing `current_amount=0.00`. | `REVERSAL` |
| **REVERSED**| `NEW` | Ignore new creation on reversed transaction; preserve reversal. | `NEW_IGNORED_REVERSED` |
| **REVERSED**| `UPDATE` | Ignore update on reversed transaction; preserve reversal. | `UPDATE_IGNORED_REVERSED` |
| **REVERSED**| `REVERSAL` | **Double-reversal prevention**: Ignore duplicate reversal to prevent double-deduction. | `REVERSAL_DUPLICATE_IGNORED` |

---

## 3. Reversal Accounting

- When a transaction is reversed:
  - Its dimensional status becomes `REVERSED`.
  - Its net contributing amount in daily metrics becomes `$0.00`.
  - It is excluded from the count of active transactions and contributing amounts for that business date.
  - Its full history is preserved in `transaction_history` with the exact previous amount and timestamp.

---

## 4. Late-Arriving Events and Historical Recomputation

- **Business Date vs. Ingestion Date**:
  - Daily business metrics are strictly partitioned by the **business event date** (`func.date(first_event_timestamp)`), not the ingestion date.
- **Selective Historical Recomputation**:
  - When an event arrives with an event timestamp from a past business date (e.g. 5 days ago), the engine collects all unique dates affected by the batch.
  - The `RecomputationEngine` aggregates and upserts the `daily_metrics` table specifically for the affected historical dates.
  - Historical recomputations are idempotent: re-evaluating metrics for past dates reproduces the exact consolidated state without double-counting.

---

## 5. Terminal Accounting and Conservation Equation

To guarantee zero data loss and absolute observability, every single record entering the ingestion pipeline must receive exactly one terminal classification:

$$\text{Input Rows} = \text{Accepted Rows} + \text{Rejected Rows} + \text{Duplicate Rows}$$

- **`Accepted Rows`**: Structurally valid, verified reference keys, unique event IDs applied to transactions.
- **`Rejected Rows`**: Quarantined records with syntax errors, missing mandatory fields, non-numeric amounts, or malformed timestamps.
- **`Duplicate Rows`**: Events with already-seen `event_id` in the batch or historical ledger.

The reconciliation audit fails if $\text{Discrepancy} \neq 0$.

---

## 6. Anomaly Detection and Alerting Thresholds

The alert engine compares incoming batch profiles against an active versioned `BaselineProfile`:

| Metric Name | Threshold | Severity | Trigger Condition |
| :--- | :--- | :--- | :--- |
| `record_volume` | $\le -30\%$ drop | `WARNING` | Current volume is 30% to 50% below baseline. |
| `record_volume` | $\le -50\%$ drop | `CRITICAL`| Current volume is $> 50\%$ below baseline. |
| `null_rate` | $\ge +10.0$ percentage points | `WARNING` | Rejection proportion increases by 10 to 20 percentage points. |
| `null_rate` | $\ge +20.0$ percentage points | `CRITICAL`| Rejection proportion increases by $> 20$ percentage points. |
| `mean_amount` | $\ge \pm 50\%$ drift | `WARNING` | Average transaction amount drifts by $> 50\%$ from baseline. |
| `mean_amount` | $\ge \pm 100\%$ drift | `CRITICAL`| Average transaction amount drifts by $> 100\%$ from baseline. |

Alerts are explainable: every alert specifies the baseline value, current value, difference, percentage change, and actionable operational guidance. Duplicate alerts for the same `(run_id, metric_name)` are prevented.

