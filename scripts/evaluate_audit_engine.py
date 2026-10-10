"""
Compare the audit engine's findings with the generator's answer key.

The answer key (<dataset>_answer_key.csv) lists which records were deliberately
made non-compliant. This script runs the engine on the dataset and reports, for
each rule, how many violations were expected, how many were found, and the
precision / recall / F1 of the engine. Use the output as testing evidence.

Usage (from the project root, venv active):
    python scripts/generate_synthetic_dataset.py --rows 5000 --out data/simulated/perf_5000.csv
    python scripts/evaluate_audit_engine.py data/simulated/perf_5000.csv
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

# Let this script import the app package when run from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auditing.engine import audit_file, load_rules  # noqa: E402

# Which answer-key column belongs to which rule.
KEY_COLUMN = {"CONSENT-01": "consent_violation", "RETENTION-01": "retention_violation"}


def main():
    parser = argparse.ArgumentParser(description="Evaluate the audit engine against an answer key.")
    parser.add_argument("dataset", help="path to the dataset CSV")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    key_path = dataset_path.with_name(dataset_path.stem + "_answer_key.csv")
    key = pd.read_csv(key_path, dtype=str)

    started = time.perf_counter()
    outcome = audit_file(dataset_path, load_rules())
    seconds = time.perf_counter() - started

    print(f"Dataset: {dataset_path}  ({outcome.records_checked} records)")
    print(f"Audit finished in {seconds:.2f} s; compliance score {outcome.score}%")
    print()
    print(f"{'Rule':<14}{'Expected':>9}{'Found':>7}{'TP':>6}{'FP':>5}{'FN':>5}{'Prec':>8}{'Recall':>8}{'F1':>7}")

    for rule_code, column in KEY_COLUMN.items():
        expected = set(key.loc[key[column] == "Yes", "data_subject_id"])
        found = {f.record_id for f in outcome.findings if f.rule_code == rule_code}
        tp, fp, fn = len(expected & found), len(found - expected), len(expected - found)
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        print(f"{rule_code:<14}{len(expected):>9}{len(found):>7}{tp:>6}{fp:>5}{fn:>5}"
              f"{precision:>8.1%}{recall:>8.1%}{f1:>7.2f}")


if __name__ == "__main__":
    main()