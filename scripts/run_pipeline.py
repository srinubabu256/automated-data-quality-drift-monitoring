"""Command-Line Pipeline Runner for YottaFlex Data Engineering Challenge.

Executes end-to-end ingestion, schema validation, transaction lifecycle,
historical metric recomputation, data quality profiling, drift detection,
and terminal reconciliation on a given CSV or JSON transaction file.

Usage:
    python scripts/run_pipeline.py --file data/sample/transactions_1k.csv
    python scripts/run_pipeline.py --file data/sample/transactions_10k.csv --allow-rerun
"""
import argparse
import sys
import time
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.database import SessionLocal, init_db
from app.services.batch_service import BatchService


def main():
    parser = argparse.ArgumentParser(description="Run YottaFlex transaction ingestion pipeline.")
    parser.add_argument(
        "--file",
        type=str,
        default="data/sample/transactions_1k.csv",
        help="Path to CSV or JSON transaction file (default: data/sample/transactions_1k.csv)"
    )
    parser.add_argument(
        "--allow-rerun",
        action="store_true",
        default=False,
        help="Allow re-execution of previously processed file hash"
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[ERROR] Target file not found: {file_path}")
        sys.exit(1)

    print("=================================================================")
    print("        YottaFlex Data Quality & Ingestion Pipeline Runner       ")
    print("=================================================================")
    print(f"  Target File:  {file_path.resolve()}")
    print(f"  File Size:    {file_path.stat().st_size:,} bytes")
    print(f"  Allow Rerun:  {args.allow_rerun}")
    print("-----------------------------------------------------------------")

    init_db()
    db = SessionLocal()

    try:
        t0 = time.perf_counter()
        result = BatchService.process_batch_file(
            file_path=file_path,
            db=db,
            allow_rerun=args.allow_rerun,
        )
        elapsed = time.perf_counter() - t0

        print("\nPipeline Execution Succeeded!")
        print(f"  Run ID:              {result.run_id}")
        print(f"  Status:              {result.status}")
        print(f"  Input Rows:          {result.input_count:,}")
        print(f"  Accepted Records:    {result.accepted_count:,}")
        print(f"  Quarantined/Rejected:{result.rejected_count:,}")
        print(f"  Duplicate Events:    {result.duplicate_count:,}")
        print(f"  Transactions Applied:{result.processed_count:,}")
        print(f"  Affected Dates:      {len(result.affected_dates)}")
        print(f"  Duration:            {elapsed:.3f} seconds")
        print(f"  Reconciliation:      {'PASSED (100% Conserved)' if result.reconciliation_passed else 'FAILED'}")
        print("=================================================================")

    except Exception as exc:
        print(f"\n[ERROR] Pipeline run failed: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
