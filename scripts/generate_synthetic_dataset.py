"""
Generate a synthetic organizational dataset for testing the auditing engine.

The columns follow the standardized compliance schema (Table 4.3) and the
sample dataset in Table 3.1. The derived field retention_expiry_date is NOT
written to the CSV, because the system computes it (collection_date plus
retention_period) during preprocessing.

Alongside the dataset, an "answer key" CSV is written. It lists which records
were deliberately made non-compliant, so the auditing engine's results can be
checked against the truth.

Usage (from the project root, with the venv active):
    python scripts/generate_synthetic_dataset.py
    python scripts/generate_synthetic_dataset.py --rows 5000 --out data/simulated/perf_5000.csv
"""
import argparse
import calendar
import csv
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

# ---------------------------------------------------------------------------
# Settings you can tune. Probabilities in each group must add up to 1.
# ---------------------------------------------------------------------------
CONSENT_WEIGHTS = OrderedDict([("Yes", 0.88), ("No", 0.12)])

# (amount, unit) -> how likely. Units are "years", "months" or "days".
RETENTION_WEIGHTS = OrderedDict([
    ((1, "years"), 0.10),
    ((2, "years"), 0.15),
    ((3, "years"), 0.20),
    ((5, "years"), 0.30),
    ((7, "years"), 0.15),
    ((6, "months"), 0.05),
    ((90, "days"), 0.05),
])

# Percent chance that a record is still Active once its retention period has
# ended (an Active expired record is a retention violation) ...
ACTIVE_IF_EXPIRED = 25
# ... and percent chance that a record is Active while still inside its period.
ACTIVE_IF_VALID = 95

HISTORY_YEARS = 5  # collection dates fall within this many years before today

COLUMNS = [
    "data_subject_id",
    "consent_status",
    "collection_date",
    "retention_period",
    "record_status",
]
KEY_COLUMNS = ["data_subject_id", "consent_violation", "retention_violation"]


def add_months(start, months):
    """Move a date forward by whole months, clamping to the end of short months."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def expiry_date(collection_date, amount, unit):
    """collection_date plus retention_period (the derived field in Table 4.3)."""
    if unit == "years":
        return add_months(collection_date, amount * 12)
    if unit == "months":
        return add_months(collection_date, amount)
    return collection_date + timedelta(days=amount)


def format_period(amount, unit):
    """'1 year', '5 years', '6 months', '90 days'."""
    if amount == 1:
        unit = unit[:-1]
    return f"{amount} {unit}"


def make_record(fake, today):
    subject_id = fake.unique.numerify("Customer#####")

    consent = fake.random_element(CONSENT_WEIGHTS)

    collected = fake.date_between_dates(
        date_start=add_months(today, -HISTORY_YEARS * 12), date_end=today
    )
    amount, unit = fake.random_element(RETENTION_WEIGHTS)
    expires = expiry_date(collected, amount, unit)
    expired = expires < today

    chance_active = ACTIVE_IF_EXPIRED if expired else ACTIVE_IF_VALID
    status = "Active" if fake.boolean(chance_of_getting_true=chance_active) else "Inactive"

    record = {
        "data_subject_id": subject_id,
        "consent_status": consent,
        "collection_date": collected.isoformat(),
        "retention_period": format_period(amount, unit),
        "record_status": status,
    }
    # Ground truth: only Active records are still being processed.
    key = {
        "data_subject_id": subject_id,
        "consent_violation": "Yes" if consent == "No" and status == "Active" else "No",
        "retention_violation": "Yes" if expired and status == "Active" else "No",
    }
    return record, key


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Generate a synthetic compliance dataset.")
    parser.add_argument("--rows", type=int, default=200, help="number of records (default 200)")
    parser.add_argument(
        "--out", default="data/simulated/synthetic_dataset.csv", help="output CSV path"
    )
    parser.add_argument("--seed", type=int, default=42, help="same seed gives the same data")
    args = parser.parse_args()

    if not 1 <= args.rows <= 50000:
        parser.error("--rows must be between 1 and 50000")

    fake = Faker()
    Faker.seed(args.seed)
    today = date.today()

    records, keys = [], []
    for _ in range(args.rows):
        record, key = make_record(fake, today)
        records.append(record)
        keys.append(key)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    key_path = out_path.with_name(out_path.stem + "_answer_key.csv")

    write_csv(out_path, COLUMNS, records)
    write_csv(key_path, KEY_COLUMNS, keys)

    consent_bad = sum(k["consent_violation"] == "Yes" for k in keys)
    retention_bad = sum(k["retention_violation"] == "Yes" for k in keys)
    clean = sum(
        k["consent_violation"] == "No" and k["retention_violation"] == "No" for k in keys
    )
    print(f"Wrote {args.rows} records to {out_path}")
    print(f"Wrote the answer key to {key_path}")
    print(f"  Compliant records:        {clean}")
    print(f"  Consent violations:       {consent_bad}")
    print(f"  Retention violations:     {retention_bad}")
    print(f"  (A record can have both, so these can add up to more than {args.rows}.)")


if __name__ == "__main__":
    main()