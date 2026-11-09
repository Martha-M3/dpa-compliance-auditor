"""
NFR-01: under a workload of up to 5,000 records, at least 95% of audit runs must finish within 30 seconds.

Run with  pytest tests/test_performance.py -s  to see the timings. The numbers depend on the computer,
so re-run this on the machine you want to report.
"""
import statistics
import subprocess
import sys
import time
from pathlib import Path

from app.auditing.dataset_schema import validate_dataset
from app.auditing.engine import audit_file, load_rules
from helpers import run_audit_via_web

ROOT = Path(__file__).resolve().parent.parent
LIMIT_SECONDS = 30


def make_dataset(tmp_path, rows):
    out = tmp_path / f"perf_{rows}.csv"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_synthetic_dataset.py"),
                    "--rows", str(rows), "--out", str(out)], check=True, capture_output=True)
    return out


def percentile(values, p):
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))
    return ordered[index]


def summarise(label, times):
    return (f"{label}: runs={len(times)}, min={min(times):.3f}s, mean={statistics.mean(times):.3f}s, "
            f"p95={percentile(times, 95):.3f}s, max={max(times):.3f}s")


def test_engine_with_5000_records(tmp_path, record):
    path = make_dataset(tmp_path, 5000)
    rules = load_rules()
    times = []
    for _ in range(30):
        start = time.perf_counter()
        assert validate_dataset(path).passed
        outcome = audit_file(path, rules)
        times.append(time.perf_counter() - start)
    assert outcome.records_checked == 5000
    within = sum(t <= LIMIT_SECONDS for t in times) / len(times)
    assert within >= 0.95
    record("TC-F01", summarise("Validation + audit of 5,000 records", times) + f"; {within:.0%} of runs within {LIMIT_SECONDS} s.")


def test_whole_web_workflow_with_5000_records(officer, tmp_path, record):
    path = make_dataset(tmp_path, 5000)
    content = path.read_bytes()
    times = []
    for _ in range(10):
        start = time.perf_counter()
        run_audit_via_web(officer, content, "perf.csv")  # upload + validate + audit + save results
        times.append(time.perf_counter() - start)
    within = sum(t <= LIMIT_SECONDS for t in times) / len(times)
    assert within >= 0.95
    record("TC-F02", summarise("Upload, validation, audit and saving of results for 5,000 records (test database)", times) + f"; {within:.0%} of runs within {LIMIT_SECONDS} s.")


def test_stress_with_50000_records(tmp_path, record):
    path = make_dataset(tmp_path, 50000)
    start = time.perf_counter()
    assert validate_dataset(path).passed
    outcome = audit_file(path, load_rules())
    elapsed = time.perf_counter() - start
    assert outcome.records_checked == 50000 and elapsed < LIMIT_SECONDS
    record("TC-F03", f"Stress run, 10 times the required workload: validation + audit of 50,000 records took {elapsed:.2f} s ({len(outcome.findings)} violations found).")
