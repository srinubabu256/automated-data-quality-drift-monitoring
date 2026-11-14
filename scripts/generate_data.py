"""Synthetic Transaction Data Generator for YottaFlex Data Engineering Challenge.
Generates reproducible transaction datasets with realistic business patterns and edge cases.
"""
import argparse
import csv
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple


class DataGenerator:
    """Generates synthetic transaction records with configurable anomalies and edge cases."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
        self.currencies = ["USD"]
        self.source_systems = ["PAYMENT_GATEWAY_V1", "ECOMMERCE_CHECKOUT", "MOBILE_POS"]

    def generate_dataset(
        self,
        num_records: int,
        base_date: datetime = None
    ) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
        """Generate a list of transaction records along with ground truth metadata."""
        if base_date is None:
            base_date = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)

        if num_records == 0:
            return [], {
                "total_records": 0,
                "normal_new": 0,
                "updates": 0,
                "reversals": 0,
                "duplicates": 0,
                "missing_fields": 0,
                "malformed_timestamps": 0,
                "invalid_amounts": 0,
                "invalid_references": 0,
                "late_arriving": 0,
                "out_of_order": 0,
            }

        records: List[Dict[str, str]] = []
        metadata = {
            "total_records": num_records,
            "normal_new": 0,
            "updates": 0,
            "reversals": 0,
            "duplicates": 0,
            "missing_fields": 0,
            "malformed_timestamps": 0,
            "invalid_amounts": 0,
            "invalid_references": 0,
            "late_arriving": 0,
            "out_of_order": 0,
        }

        # Customer and product pools
        num_customers = max(10, num_records // 20)
        num_products = max(5, num_records // 50)
        customers = [f"CUST_{i:05d}" for i in range(1, num_customers + 1)]
        products = [f"PROD_{i:04d}" for i in range(1, num_products + 1)]

        # Track valid transactions for updates and reversals
        created_transactions: List[Dict[str, any]] = []

        # Target proportions:
        # ~74% Normal NEW
        # ~10% UPDATE
        # ~5% REVERSAL
        # ~3% Duplicates
        # ~2% Missing fields
        # ~1% Malformed timestamps
        # ~2% Invalid amounts
        # ~1% Invalid references
        # ~2% Late arriving

        for idx in range(num_records):
            roll = random.random()
            event_id = f"evt_{uuid.uuid4().hex[:12]}"
            source_system = random.choice(self.source_systems)
            currency = "USD"

            # Case 1: Duplicate of an existing record (if we have records)
            if roll < 0.03 and len(records) > 0:
                dup_target = random.choice(records)
                dup_record = dict(dup_target)
                records.append(dup_record)
                metadata["duplicates"] += 1
                continue

            # Case 2: Missing required field (~2%)
            elif roll < 0.05:
                txn_id = f"TXN_{idx:07d}"
                cust = random.choice(customers)
                prod = random.choice(products)
                amt = f"{round(random.uniform(10.0, 500.0), 2):.2f}"
                ts = (base_date + timedelta(minutes=idx % 1440)).strftime("%Y-%m-%dT%H:%M:%SZ")

                missing_field = random.choice(["event_id", "transaction_id", "customer_id", "product_id"])
                rec = {
                    "event_id": "" if missing_field == "event_id" else event_id,
                    "transaction_id": "" if missing_field == "transaction_id" else txn_id,
                    "customer_id": "" if missing_field == "customer_id" else cust,
                    "product_id": "" if missing_field == "product_id" else prod,
                    "event_type": "NEW",
                    "amount": amt,
                    "currency": currency,
                    "event_timestamp": ts,
                    "source_system": source_system,
                }
                records.append(rec)
                metadata["missing_fields"] += 1
                continue

            # Case 3: Malformed timestamp (~1%)
            elif roll < 0.06:
                txn_id = f"TXN_{idx:07d}"
                cust = random.choice(customers)
                prod = random.choice(products)
                amt = f"{round(random.uniform(10.0, 500.0), 2):.2f}"
                bad_ts = random.choice(["2026-99-99 25:99:99", "INVALID_DATE", "2026/13/45 10:00:00", "not-a-timestamp"])
                rec = {
                    "event_id": event_id,
                    "transaction_id": txn_id,
                    "customer_id": cust,
                    "product_id": prod,
                    "event_type": "NEW",
                    "amount": amt,
                    "currency": currency,
                    "event_timestamp": bad_ts,
                    "source_system": source_system,
                }
                records.append(rec)
                metadata["malformed_timestamps"] += 1
                continue

            # Case 4: Invalid amount (~2%)
            elif roll < 0.08:
                txn_id = f"TXN_{idx:07d}"
                cust = random.choice(customers)
                prod = random.choice(products)
                bad_amt = random.choice(["-50.00", "0.00", "N/A", "INVALID", "-999.99"])
                ts = (base_date + timedelta(minutes=idx % 1440)).strftime("%Y-%m-%dT%H:%M:%SZ")
                rec = {
                    "event_id": event_id,
                    "transaction_id": txn_id,
                    "customer_id": cust,
                    "product_id": prod,
                    "event_type": "NEW",
                    "amount": bad_amt,
                    "currency": currency,
                    "event_timestamp": ts,
                    "source_system": source_system,
                }
                records.append(rec)
                metadata["invalid_amounts"] += 1
                continue

            # Case 5: Invalid reference keys (~1%)
            elif roll < 0.09:
                txn_id = f"TXN_{idx:07d}"
                bad_cust = random.choice(["INV_CUST_@@@", "UNKNOWN_CUST", "!@#$%^"])
                bad_prod = random.choice(["BAD_PROD_***", "NULL", "???"])
                amt = f"{round(random.uniform(10.0, 500.0), 2):.2f}"
                ts = (base_date + timedelta(minutes=idx % 1440)).strftime("%Y-%m-%dT%H:%M:%SZ")
                rec = {
                    "event_id": event_id,
                    "transaction_id": txn_id,
                    "customer_id": bad_cust,
                    "product_id": bad_prod,
                    "event_type": "NEW",
                    "amount": amt,
                    "currency": currency,
                    "event_timestamp": ts,
                    "source_system": source_system,
                }
                records.append(rec)
                metadata["invalid_references"] += 1
                continue

            # Case 6: Late-arriving event (~2%)
            elif roll < 0.11:
                txn_id = f"TXN_{idx:07d}"
                cust = random.choice(customers)
                prod = random.choice(products)
                amt = f"{round(random.uniform(10.0, 500.0), 2):.2f}"
                # 5 to 10 days older than base_date
                days_ago = random.randint(5, 10)
                late_ts = (base_date - timedelta(days=days_ago, minutes=idx % 1440)).strftime("%Y-%m-%dT%H:%M:%SZ")
                rec = {
                    "event_id": event_id,
                    "transaction_id": txn_id,
                    "customer_id": cust,
                    "product_id": prod,
                    "event_type": "NEW",
                    "amount": amt,
                    "currency": currency,
                    "event_timestamp": late_ts,
                    "source_system": source_system,
                }
                records.append(rec)
                metadata["late_arriving"] += 1
                created_transactions.append({"transaction_id": txn_id, "customer_id": cust, "product_id": prod, "timestamp": late_ts})
                continue

            # Case 7: UPDATE to an existing transaction (~10%)
            elif roll < 0.21 and len(created_transactions) > 0:
                target_txn = random.choice(created_transactions)
                # Update amount
                new_amt = f"{round(random.uniform(15.0, 600.0), 2):.2f}"
                # Timestamp after initial
                upd_ts = (base_date + timedelta(minutes=(idx % 1440) + 60)).strftime("%Y-%m-%dT%H:%M:%SZ")
                rec = {
                    "event_id": event_id,
                    "transaction_id": target_txn["transaction_id"],
                    "customer_id": target_txn["customer_id"],
                    "product_id": target_txn["product_id"],
                    "event_type": "UPDATE",
                    "amount": new_amt,
                    "currency": currency,
                    "event_timestamp": upd_ts,
                    "source_system": source_system,
                }
                records.append(rec)
                metadata["updates"] += 1
                continue

            # Case 8: REVERSAL to an existing transaction (~5%)
            elif roll < 0.26 and len(created_transactions) > 0:
                target_txn = random.choice(created_transactions)
                rev_amt = f"{round(random.uniform(10.0, 500.0), 2):.2f}"
                rev_ts = (base_date + timedelta(minutes=(idx % 1440) + 120)).strftime("%Y-%m-%dT%H:%M:%SZ")
                rec = {
                    "event_id": event_id,
                    "transaction_id": target_txn["transaction_id"],
                    "customer_id": target_txn["customer_id"],
                    "product_id": target_txn["product_id"],
                    "event_type": "REVERSAL",
                    "amount": rev_amt,
                    "currency": currency,
                    "event_timestamp": rev_ts,
                    "source_system": source_system,
                }
                records.append(rec)
                metadata["reversals"] += 1
                continue

            # Case 9: Normal NEW transaction (~74%)
            else:
                txn_id = f"TXN_{idx:07d}"
                cust = random.choice(customers)
                prod = random.choice(products)
                amt = f"{round(random.uniform(10.0, 500.0), 2):.2f}"
                ts = (base_date + timedelta(minutes=idx % 1440)).strftime("%Y-%m-%dT%H:%M:%SZ")
                rec = {
                    "event_id": event_id,
                    "transaction_id": txn_id,
                    "customer_id": cust,
                    "product_id": prod,
                    "event_type": "NEW",
                    "amount": amt,
                    "currency": currency,
                    "event_timestamp": ts,
                    "source_system": source_system,
                }
                records.append(rec)
                metadata["normal_new"] += 1
                created_transactions.append({"transaction_id": txn_id, "customer_id": cust, "product_id": prod, "timestamp": ts})

        return records, metadata

    def write_csv(self, records: List[Dict[str, str]], output_path: Path):
        """Write records to CSV file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "event_id",
            "transaction_id",
            "customer_id",
            "product_id",
            "event_type",
            "amount",
            "currency",
            "event_timestamp",
            "source_system"
        ]
        with open(output_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            if records:
                writer.writerows(records)

    def write_metadata(self, metadata: Dict[str, int], metadata_path: Path):
        """Write ground-truth metadata to JSON file."""
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_path, mode="w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic transaction datasets.")
    parser.add_argument("--records", type=int, default=1000, help="Number of records to generate")
    parser.add_argument("--output", type=str, default="data/sample/transactions_1k.csv", help="Output CSV path")
    parser.add_argument("--metadata", type=str, default=None, help="Output metadata JSON path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--generate-all-samples", action="store_true", help="Generate 1k, 10k, 100k and empty sample datasets")
    args = parser.parse_args()

    generator = DataGenerator(seed=args.seed)

    if args.generate_all_samples:
        configs = [
            (0, Path("data/sample/empty_batch.csv"), Path("data/sample/empty_batch_metadata.json")),
            (1000, Path("data/sample/transactions_1k.csv"), Path("data/sample/transactions_1k_metadata.json")),
            (10000, Path("data/sample/transactions_10k.csv"), Path("data/sample/transactions_10k_metadata.json")),
            (100000, Path("data/sample/transactions_100k.csv"), Path("data/sample/transactions_100k_metadata.json")),
        ]
        for count, csv_path, meta_path in configs:
            print(f"Generating {count} records -> {csv_path}...")
            records, meta = generator.generate_dataset(count)
            generator.write_csv(records, csv_path)
            generator.write_metadata(meta, meta_path)
            print(f"  Finished: {meta}")
    else:
        csv_path = Path(args.output)
        meta_path = Path(args.metadata) if args.metadata else csv_path.with_suffix(".json")
        print(f"Generating {args.records} records -> {csv_path} (seed={args.seed})...")
        records, meta = generator.generate_dataset(args.records)
        generator.write_csv(records, csv_path)
        generator.write_metadata(meta, meta_path)
        print(f"Done! Metadata: {meta}")


if __name__ == "__main__":
    main()

