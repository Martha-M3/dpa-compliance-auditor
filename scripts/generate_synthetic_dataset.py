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

Shape the data with options (all optional; run with --help to see them):
    --rows 300               how many records
    --no-consent 30          percent of people who did NOT give consent
    --active-if-expired 60   percent of expired records that are still Active (retention violations)
    --active-if-valid 90     percent of in-date records that are Active
    --years 3                collection dates fall within this many years before today
    --id-prefix Patient      IDs look like Patient12345
    --random                 different data every run (otherwise the same --seed gives the same data)
    --out data/simulated/my_dataset.csv

Examples:
    A perfectly clean dataset (no violations at all):
        python scripts/generate_synthetic_dataset.py --no-consent 0 --active-if-expired 0 --out data/simulated/clean.csv
    A very bad dataset:
        python scripts/generate_synthetic_dataset.py --no-consent 50 --active-if-expired 90 --out data/simulated/messy.csv
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
DEFAULT_NO_CONSENT = 12  # percent of people who did not give consent

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
DEFAULT_ACTIVE_IF_EXPIRED = 25
# ... and percent chance that a record is Active while still inside its period.
DEFAULT_ACTIVE_IF_VALID = 95

DEFAULT_HISTORY_YEARS = 5  # collection dates fall within this many years before today
DEFAULT_ID_PREFIX = "Customer"

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


def make_record(fake, today, settings):
    """Build one record. `settings` carries the options chosen on the command line."""
    subject_id = fake.unique.numerify(settings["id_prefix"] + "#####")

    consent = fake.random_element(settings["consent_weights"])

    collected = fake.date_between_dates(
        date_start=add_months(today, -settings["years"] * 12), date_end=today
    )
    amount, unit = fake.random_element(RETENTION_WEIGHTS)
    expires = expiry_date(collected, amount, unit)
    expired = expires < today

    chance_active = settings["active_if_expired"] if expired else settings["active_if_valid"]
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


def percent(text):
    """Argument type: a number from 0 to 100."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a number")
    if not 0 <= value <= 100:
        raise argparse.ArgumentTypeError("must be between 0 and 100")
    return value


def main():
    parser = argparse.ArgumentParser(
        description="Generate a synthetic compliance dataset (and its answer key)."
    )
    parser.add_argument("--rows", type=int, default=200, help="number of records (default 200)")
    parser.add_argument(
        "--out", default="data/simulated/synthetic_dataset.csv", help="output CSV path"
    )
    parser.add_argument(
        "--no-consent", type=percent, default=DEFAULT_NO_CONSENT, metavar="PERCENT",
        help=f"percent of people who did not give consent (default {DEFAULT_NO_CONSENT})",
    )
    parser.add_argument(
        "--active-if-expired", type=percent, default=DEFAULT_ACTIVE_IF_EXPIRED, metavar="PERCENT",
        help="percent of records past their retention period that are still Active; "
             f"each one is a retention violation (default {DEFAULT_ACTIVE_IF_EXPIRED})",
    )
    parser.add_argument(
        "--active-if-valid", type=percent, default=DEFAULT_ACTIVE_IF_VALID, metavar="PERCENT",
        help=f"percent of in-date records that are Active (default {DEFAULT_ACTIVE_IF_VALID})",
    )
    parser.add_argument(
        "--years", type=int, default=DEFAULT_HISTORY_YEARS,
        help=f"collection dates fall within this many years before today (default {DEFAULT_HISTORY_YEARS})",
    )
    parser.add_argument(
        "--id-prefix", default=DEFAULT_ID_PREFIX,
        help=f"letters at the start of each ID (default {DEFAULT_ID_PREFIX})",
    )
    parser.add_argument("--seed", type=int, default=42, help="same seed gives the same data")
    parser.add_argument(
        "--random", action="store_true", help="ignore --seed: different data every run"
    )
    args = parser.parse_args()

    if not 1 <= args.rows <= 50000:
        parser.error("--rows must be between 1 and 50000")
    if not 1 <= args.years <= 30:
        parser.error("--years must be between 1 and 30")
    if not args.id_prefix.isalnum() or len(args.id_prefix) > 20:
        parser.error("--id-prefix must be letters and numbers only (20 at most)")

    no_consent = args.no_consent / 100
    settings = {
        "id_prefix": args.id_prefix,
        "years": args.years,
        "consent_weights": OrderedDict([("Yes", round(1 - no_consent, 6)), ("No", round(no_consent, 6))]),
        "active_if_expired": args.active_if_expired,
        "active_if_valid": args.active_if_valid,
    }

    fake = Faker()
    if not args.random:
        Faker.seed(args.seed)
    today = date.today()

    records, keys = [], []
    for _ in range(args.rows):
        record, key = make_record(fake, today, settings)
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
