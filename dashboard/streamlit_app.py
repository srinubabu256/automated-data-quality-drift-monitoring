"""Streamlit Interactive Observability & Drift Monitoring Dashboard.

Provides interactive visualization, real-time batch monitoring, multi-dimensional
drift detection radar with Plotly charts, baseline management, explainable alert feeds,
and terminal reconciliation auditing.

Usage:
    streamlit run dashboard/streamlit_app.py
"""
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.config import settings
from app.database import SessionLocal, init_db
from app.database.models import (
    BaselineProfile,
    DailyMetric,
    DataQualityAlert,
    DriftAnalysisResult,
    ProcessingRun,
    RejectedRecord,
)
from app.services.baseline_service import BaselineService
from app.services.batch_service import BatchService
from app.services.drift_service import DriftService
from app.services.report_service import ReportService

# Streamlit Page Configuration
st.set_page_config(
    page_title="YottaFlex | Data Quality & Drift Platform",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown("""
<style>
    .main-title { font-size: 2.2rem; font-weight: 700; color: #1E3A8A; margin-bottom: 0.2rem; }
    .sub-title { font-size: 1.05rem; color: #4B5563; margin-bottom: 1.5rem; }
    .metric-card { background: #FFFFFF; border-radius: 8px; padding: 1.2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)


def get_db_session():
    """Provides a thread-safe database session."""
    init_db()
    return SessionLocal()


# ==============================================================================
# SIDEBAR NAVIGATION
# ==============================================================================
st.sidebar.image("https://img.shields.io/badge/YottaFlex-Data%20Quality%20Platform-blue?style=for-the-badge", use_container_width=True)
st.sidebar.markdown("### Navigation")
page = st.sidebar.radio(
    "Select View",
    [
        "📈 Overview",
        "📤 Data Upload",
        "🔍 Data Profiling",
        "🎯 Baseline Management",
        "⚡ Drift Monitoring",
        "🚨 Alert Center",
        "📋 Batch Monitoring",
        "⚖️ Reconciliation",
    ],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.info(
    f"**Engine:** SQLite (Local)\n\n"
    f"**Baseline Version:** `{settings.BASELINE_VERSION}`\n\n"
    f"**Environment:** `{settings.ENVIRONMENT}`"
)


# ==============================================================================
# 1. OVERVIEW PAGE
# ==============================================================================
if page == "📈 Overview":
    st.markdown('<div class="main-title">🛡️ Data Quality & Observability Platform</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Real-time telemetry, transaction volumes, drift detection, and health status</div>', unsafe_allow_html=True)

    db = get_db_session()
    try:
        runs = db.query(ProcessingRun).order_by(ProcessingRun.start_time.desc()).all()
        alerts = db.query(DataQualityAlert).all()
        drifts = db.query(DriftAnalysisResult).all()
        metrics = db.query(DailyMetric).order_by(DailyMetric.metric_date.asc()).all()

        total_runs = len(runs)
        completed_runs = sum(1 for r in runs if r.status == "COMPLETED")
        failed_runs = sum(1 for r in runs if r.status in ["FAILED", "ERROR"])
        total_tx = sum(r.input_count for r in runs)
        total_acc = sum(r.accepted_count for r in runs)
        total_rej = sum(r.rejected_count for r in runs)
        active_alerts = len(alerts)
        crit_alerts = sum(1 for a in alerts if str(a.severity).upper() == "CRITICAL")
        drift_count = sum(1 for d in drifts if d.drift_detected)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Ingestion Runs", f"{total_runs:,}", f"{completed_runs} Completed")
        col2.metric("Total Records Ingested", f"{total_tx:,}", f"{total_acc:,} Accepted")
        col3.metric("Quarantined Records", f"{total_rej:,}", f"{(total_rej/max(1, total_tx))*100:.2f}% Error Rate", delta_color="inverse")
        col4.metric("Active Quality Alerts", f"{active_alerts}", f"{crit_alerts} Critical", delta_color="inverse")

        st.markdown("---")

        # Trends
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("Daily Processed Amount Trend ($)")
            if metrics:
                df_metrics = pd.DataFrame([
                    {
                        "Date": str(m.metric_date),
                        "Total Amount ($)": float(m.total_amount),
                        "Transactions": m.total_transactions,
                        "Dimension": m.dimension_type,
                    }
                    for m in metrics if m.dimension_type in ["GLOBAL", "TOTAL"]
                ])
                if not df_metrics.empty:
                    fig_trend = px.line(
                        df_metrics,
                        x="Date",
                        y="Total Amount ($)",
                        markers=True,
                        title="Aggregated Financial Transaction Volume",
                        template="plotly_white",
                    )
                    fig_trend.update_layout(height=350)
                    st.plotly_chart(fig_trend, use_container_width=True)
                else:
                    st.info("No global daily metrics recorded yet.")
            else:
                st.info("No daily metrics computed yet. Run a batch to populate trends.")

        with c2:
            st.subheader("Alert Severity Distribution")
            if alerts:
                sev_counts = {}
                for a in alerts:
                    s = str(a.severity).upper()
                    sev_counts[s] = sev_counts.get(s, 0) + 1
                df_sev = pd.DataFrame(list(sev_counts.items()), columns=["Severity", "Count"])
                fig_pie = px.pie(
                    df_sev,
                    names="Severity",
                    values="Count",
                    color="Severity",
                    color_discrete_map={"CRITICAL": "#DC2626", "HIGH": "#EA580C", "WARNING": "#F59E0B", "LOW": "#10B981"},
                    hole=0.45,
                )
                fig_pie.update_layout(height=350, showlegend=True)
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.success("No data quality alerts detected. System fully healthy!")

    finally:
        db.close()


# ==============================================================================
# 2. DATA UPLOAD PAGE
# ==============================================================================
elif page == "📤 Data Upload":
    st.markdown('<div class="main-title">📤 Batch Data Upload & Ingestion</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Upload CSV or JSON transaction batches for automated validation, deduplication, and metric updates</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([3, 2])
    with c1:
        uploaded_file = st.file_uploader(
            "Choose a Transaction Feed File",
            type=["csv", "json"],
            help="Upload a standard transaction CSV or JSON/NDJSON file.",
        )
        allow_rerun = st.checkbox("Allow Rerun (Override duplicate SHA-256 fingerprint check)", value=False)

        if uploaded_file is not None:
            st.write(f"**Filename:** `{uploaded_file.name}` ({uploaded_file.size:,} bytes)")
            if st.button("🚀 Ingest & Process Batch", type="primary"):
                # Save file to input directory
                os.makedirs(settings.DATA_INPUT_DIR, exist_ok=True)
                save_path = Path(settings.DATA_INPUT_DIR) / uploaded_file.name
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                with st.spinner("Processing batch through validation and recomputation pipeline..."):
                    db = get_db_session()
                    try:
                        res = BatchService.process_batch_file(
                            file_path=save_path,
                            db=db,
                            allow_rerun=allow_rerun,
                        )
                        st.success(f"Batch processed successfully! Run ID: `{res.run_id}`")

                        col_a, col_b, col_c, col_d = st.columns(4)
                        col_a.metric("Input Rows", f"{res.input_count:,}")
                        col_b.metric("Accepted", f"{res.accepted_count:,}")
                        col_c.metric("Quarantined", f"{res.rejected_count:,}", delta_color="inverse")
                        col_d.metric("Duplicates", f"{res.duplicate_count:,}", delta_color="inverse")

                        st.info(f"**Reconciliation:** {'PASSED (100% Conserved)' if res.reconciliation_passed else 'FAILED'}")
                    except Exception as err:
                        st.error(f"Ingestion Failed: {err}")
                    finally:
                        db.close()

    with c2:
        st.subheader("Expected Ingestion Schema")
        st.markdown("""
        Every record must contain the following required fields:
        - `event_id` (String UUID)
        - `transaction_id` (String, e.g. `TXN_000001`)
        - `customer_id` (String, format `CUST_XXXXX`)
        - `product_id` (String, format `PROD_XXXX`)
        - `event_type` (`NEW`, `UPDATE`, `REVERSAL`)
        - `amount` (Positive decimal number)
        - `currency` (ISO-4217, e.g. `USD`)
        - `event_timestamp` (ISO-8601 UTC timestamp)
        """)


# ==============================================================================
# 3. DATA PROFILING PAGE
# ==============================================================================
elif page == "🔍 Data Profiling":
    st.markdown('<div class="main-title">🔍 Column-Level Data Quality Profiling</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Statistical distributions, null-rates, distinct cardinality, and freshness latencies</div>', unsafe_allow_html=True)

    db = get_db_session()
    try:
        from app.database.models import RawEvent
        sample_evts = db.query(RawEvent).order_by(RawEvent.id.desc()).limit(2000).all()

        if not sample_evts:
            st.warning("No transaction events found in database to profile. Please upload or ingest a batch first.")
        else:
            df = pd.DataFrame([
                {
                    "amount": float(e.amount) if e.amount is not None else np.nan,
                    "currency": e.currency,
                    "event_type": e.event_type,
                    "customer_id": e.customer_id,
                    "product_id": e.product_id,
                    "event_timestamp": e.event_timestamp,
                }
                for e in sample_evts
            ])

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Numeric Amount Distribution")
                fig_hist = px.histogram(
                    df,
                    x="amount",
                    nbins=30,
                    title="Transaction Amount Histogram (Recent Sample)",
                    template="plotly_white",
                    color_discrete_sequence=["#2563EB"],
                )
                st.plotly_chart(fig_hist, use_container_width=True)

            with col2:
                st.subheader("Event Type Frequency")
                type_counts = df["event_type"].value_counts().reset_index()
                type_counts.columns = ["Event Type", "Count"]
                fig_bar = px.bar(
                    type_counts,
                    x="Event Type",
                    y="Count",
                    color="Event Type",
                    title="Transaction Event Classifications",
                    template="plotly_white",
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            st.subheader("Column Quality Metrics Summary")
            col_stats = []
            for col in df.columns:
                null_cnt = int(df[col].isna().sum())
                null_pct = round((null_cnt / len(df)) * 100.0, 2)
                distinct_cnt = int(df[col].nunique(dropna=True))
                col_stats.append({
                    "Column Name": col,
                    "Total Records": len(df),
                    "Null Count": null_cnt,
                    "Null Rate (%)": f"{null_pct}%",
                    "Distinct Values": distinct_cnt,
                    "Data Type": str(df[col].dtype),
                })
            st.dataframe(pd.DataFrame(col_stats), use_container_width=True)

    finally:
        db.close()


# ==============================================================================
# 4. BASELINE MANAGEMENT PAGE
# ==============================================================================
elif page == "🎯 Baseline Management":
    st.markdown('<div class="main-title">🎯 Baseline Profile Management</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Version-controlled production reference profiles for statistical drift comparison</div>', unsafe_allow_html=True)

    db = get_db_session()
    try:
        baselines = BaselineService.list_baselines(db)

        c1, c2 = st.columns([3, 2])
        with c1:
            st.subheader("Available Reference Baselines")
            if baselines:
                b_data = [
                    {
                        "Version": b.version,
                        "Baseline Name": b.baseline_name,
                        "Volume": f"{b.record_volume:,}",
                        "Null Rate": f"{(b.null_rate or 0)*100:.2f}%",
                        "Mean Amount": f"${b.mean_amount:.2f}",
                        "Std Dev": f"${b.std_amount:.2f}",
                        "Freshness (s)": f"{b.event_freshness_sec:,.0f}s",
                        "Active": "✅ YES" if b.is_active else "NO",
                    }
                    for b in baselines
                ]
                st.dataframe(pd.DataFrame(b_data), use_container_width=True)
            else:
                st.info("No baseline profiles found in database.")

        with c2:
            st.subheader("Create / Update Baseline Version")
            with st.form("create_baseline_form"):
                new_ver = st.text_input("Baseline Version", value=f"v{len(baselines)+1}.0")
                new_name = st.text_input("Baseline Description", value="Production Gold Baseline")
                vol = st.number_input("Target Volume", value=10000, step=1000)
                n_rate = st.number_input("Target Null Rate", value=0.015, step=0.005, format="%.3f")
                m_amt = st.number_input("Mean Amount ($)", value=150.0, step=5.0)
                std_amt = st.number_input("Std Amount ($)", value=45.0, step=5.0)
                is_act = st.checkbox("Set as Active Reference Baseline", value=True)

                if st.form_submit_button("💾 Save Baseline Version"):
                    BaselineService.create_or_update(
                        db=db,
                        version=new_ver,
                        baseline_name=new_name,
                        metrics={
                            "record_volume": vol,
                            "null_rate": n_rate,
                            "mean_amount": m_amt,
                            "std_amount": std_amt,
                            "min_amount": 5.0,
                            "max_amount": 1000.0,
                            "median_amount": m_amt - 5.0,
                            "p95_amount": m_amt + (std_amt * 2.0),
                            "event_freshness_sec": 3600.0,
                        },
                        is_active=is_act,
                    )
                    st.success(f"Baseline version `{new_ver}` saved successfully!")
                    st.rerun()

    finally:
        db.close()


# ==============================================================================
# 5. DRIFT MONITORING PAGE
# ==============================================================================
elif page == "⚡ Drift Monitoring":
    st.markdown('<div class="main-title">⚡ Multi-Dimensional Drift Radar</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Statistical drift detection across Volume, Null-Rate, Numeric PSI, Categorical Chi-Square, and KS Tests</div>', unsafe_allow_html=True)

    db = get_db_session()
    try:
        drift_results = DriftService.query_drift_results(db, limit=200)

        if not drift_results:
            st.info("No drift analysis records found yet. Ingest a batch to trigger statistical drift testing.")
        else:
            df_drift = pd.DataFrame([
                {
                    "Run ID": d.run_id[:16],
                    "Drift Type": d.drift_type,
                    "Column": d.column_name or "BATCH_TABLE",
                    "Method": d.detection_method,
                    "Baseline": f"{d.baseline_value:.2f}" if d.baseline_value is not None else "-",
                    "Current": f"{d.current_value:.2f}" if d.current_value is not None else "-",
                    "Diff (%)": f"{d.percentage_difference:+.2f}%" if d.percentage_difference is not None else "-",
                    "Stat Value": f"{d.statistical_statistic:.3f}" if d.statistical_statistic is not None else "-",
                    "p-value": f"{d.p_value:.4f}" if d.p_value is not None else "-",
                    "Status": "🚨 DRIFT" if d.drift_detected else "✅ STABLE",
                    "Severity": d.severity,
                }
                for d in drift_results
            ])

            # Chart of detected drifts
            st.subheader("Statistical Test Findings")
            fig_drift_bar = px.bar(
                df_drift,
                x="Column",
                y="Drift Type",
                color="Status",
                color_discrete_map={"🚨 DRIFT": "#DC2626", "✅ STABLE": "#10B981"},
                barmode="group",
                title="Drift Findings by Column and Dimension",
                template="plotly_white",
            )
            st.plotly_chart(fig_drift_bar, use_container_width=True)

            st.dataframe(df_drift, use_container_width=True)

    finally:
        db.close()


# ==============================================================================
# 6. ALERT CENTER PAGE
# ==============================================================================
elif page == "🚨 Alert Center":
    st.markdown('<div class="main-title">🚨 Explainable Quality Alert Center</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Actionable anomaly notifications with root-cause explanations and operator recommendations</div>', unsafe_allow_html=True)

    db = get_db_session()
    try:
        alerts = ReportService.get_alerts(db, limit=100)

        if not alerts:
            st.success("🎉 No active data quality alerts! All pipeline metrics match approved baseline profiles.")
        else:
            for a in alerts:
                sev_color = "#DC2626" if a.severity == "CRITICAL" else "#EA580C" if a.severity == "HIGH" else "#F59E0B"
                with st.expander(f"⚠️ [{a.severity}] {a.metric_name} — Run {a.run_id[:16]}", expanded=(a.severity == "CRITICAL")):
                    st.markdown(f"**Alert ID:** `{a.alert_id}` | **Severity:** <span style='color:{sev_color}; font-weight:bold;'>{a.severity}</span>", unsafe_allow_html=True)
                    st.markdown(f"**Baseline Value:** `{a.baseline_value:.2f}` | **Current Value:** `{a.current_value:.2f}` | **Drift:** `{a.pct_change:+.2f}%`")
                    st.markdown(f"**Root Cause Explanation:**\n> {a.explanation}")
                    st.markdown(f"**Recommended Action:**\n> 🛠️ {a.suggested_action}")

    finally:
        db.close()


# ==============================================================================
# 7. BATCH MONITORING PAGE
# ==============================================================================
elif page == "📋 Batch Monitoring":
    st.markdown('<div class="main-title">📋 Ingestion Batch Telemetry & Runs</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Audit trail of execution statuses, SHA-256 idempotency hashes, and processing durations</div>', unsafe_allow_html=True)

    db = get_db_session()
    try:
        runs = BatchService.list_runs(db, limit=100)
        if not runs:
            st.info("No ingestion runs recorded yet.")
        else:
            run_data = [
                {
                    "Run ID": r.run_id,
                    "Source File": r.source_file,
                    "Status": r.status,
                    "Input Rows": f"{r.input_count:,}",
                    "Accepted": f"{r.accepted_count:,}",
                    "Quarantined": f"{r.rejected_count:,}",
                    "Duplicates": f"{r.duplicate_count:,}",
                    "Duration (s)": f"{r.execution_duration_sec:.2f}s",
                    "Started At": r.start_time.strftime("%Y-%m-%d %H:%M:%S") if r.start_time else "-",
                }
                for r in runs
            ]
            st.dataframe(pd.DataFrame(run_data), use_container_width=True)

    finally:
        db.close()


# ==============================================================================
# 8. RECONCILIATION PAGE
# ==============================================================================
elif page == "⚖️ Reconciliation":
    st.markdown('<div class="main-title">⚖️ Mathematical Conservation & Reconciliation</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Guaranteed zero data loss accounting: Input = Accepted + Quarantined + Duplicates</div>', unsafe_allow_html=True)

    db = get_db_session()
    try:
        runs = BatchService.list_runs(db, limit=20)
        if not runs:
            st.info("No runs available to reconcile.")
        else:
            run_options = {f"{r.run_id} ({r.source_file})": r.run_id for r in runs}
            selected_label = st.selectbox("Select Ingestion Run to Audit", list(run_options.keys()))
            selected_run_id = run_options[selected_label]

            recon = ReportService.get_reconciliation_report(db, selected_run_id)

            st.markdown("### Conservation Equation Verification")
            st.latex(r"\text{Input Records} = \text{Accepted Records} + \text{Quarantined Records} + \text{Duplicate Records}")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Input Records", f"{recon.get('input_count', 0):,}")
            c2.metric("Accepted Records", f"{recon.get('accepted_count', 0):,}")
            c3.metric("Quarantined Records", f"{recon.get('rejected_count', 0):,}")
            c4.metric("Duplicate Records", f"{recon.get('duplicate_count', 0):,}")

            passed = recon.get("reconciliation_passed", False)
            if passed:
                st.success(f"✅ RECONCILIATION PASSED: 100% mathematical conservation verified for Run `{selected_run_id}`.")
            else:
                st.error(f"❌ RECONCILIATION FAILED: Discrepancy of {recon.get('difference', 0)} records detected.")

            st.json(recon)

    finally:
        db.close()

