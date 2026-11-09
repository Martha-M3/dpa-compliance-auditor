"""Audit engine: FR-10, FR-11, FR-12, NFR-05 (tests TC-E01 to TC-E15)."""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.auditing.engine import RuleError, audit_dataframe, audit_file, load_rules, retention_end

ROOT = Path(__file__).resolve().parent.parent
RULES = load_rules()
COLUMNS = ["data_subject_id", "consent_status", "collection_date", "retention_period", "record_status"]


def audit(rows, today):
    return audit_dataframe(pd.DataFrame(rows, columns=COLUMNS), RULES, today)


def codes(outcome):
    return sorted(f.rule_code for f in outcome.findings)


def test_consent_missing_and_active_is_critical(record):
    out = audit([["C1", "No", "2026-01-01", "5 years", "Active"]], date(2026, 6, 1))
    assert codes(out) == ["CONSENT-01"] and out.findings[0].severity == "Critical"
    record("TC-E01", f"1 finding: {out.findings[0].rule_code}, severity {out.findings[0].severity}.")


def test_inactive_records_are_not_audited(record):
    out = audit([
        ["C1", "No", "2026-01-01", "5 years", "Inactive"],
        ["C2", "Yes", "2015-01-01", "1 year", "Inactive"],
    ], date(2026, 6, 1))
    assert out.findings == [] and out.score == 100.0
    record("TC-E02", "0 findings and score 100.00 for an Inactive record without consent and an expired Inactive record.")


def test_retention_boundaries_around_today(record):
    today = date(2026, 6, 15)
    ends_yesterday = audit([["C1", "Yes", "2025-06-14", "1 year", "Active"]], today)
    ends_today = audit([["C2", "Yes", "2025-06-15", "1 year", "Active"]], today)
    ends_tomorrow = audit([["C3", "Yes", "2025-06-16", "1 year", "Active"]], today)
    assert codes(ends_yesterday) == ["RETENTION-01"]
    assert ends_today.findings == [] and ends_tomorrow.findings == []
    record("TC-E03", "Expiry yesterday: 1 violation. Expiry today: none. Expiry tomorrow: none.")


def test_expired_period_but_inactive_is_compliant(record):
    out = audit([["C1", "Yes", "2015-01-01", "2 years", "Inactive"]], date(2026, 6, 1))
    assert out.findings == []
    record("TC-E04", "0 findings.")


def test_leap_day_collection_date(record):
    assert retention_end(date(2024, 2, 29), "1 year") == date(2025, 2, 28)
    row = [["C1", "Yes", "2024-02-29", "1 year", "Active"]]
    assert audit(row, date(2025, 2, 28)).findings == []
    assert codes(audit(row, date(2025, 3, 1))) == ["RETENTION-01"]
    record("TC-E05", "2024-02-29 + 1 year = 2025-02-28. Not a violation on 2025-02-28; a violation on 2025-03-01.")


def test_month_end_arithmetic(record):
    assert retention_end(date(2023, 8, 31), "6 months") == date(2024, 2, 29)
    assert retention_end(date(2023, 1, 31), "1 month") == date(2023, 2, 28)
    record("TC-E06", "2023-08-31 + 6 months = 2024-02-29; 2023-01-31 + 1 month = 2023-02-28 (end of month, not an invalid date).")


def test_period_units(record):
    assert retention_end(date(2025, 1, 1), "90 days") == date(2025, 4, 1)
    assert retention_end(date(2025, 1, 1), "1 year") == date(2026, 1, 1)
    assert retention_end(date(2025, 1, 1), "2 YEARS") == date(2027, 1, 1)
    assert retention_end(date(2025, 1, 1), "6 month") == date(2025, 7, 1)
    record("TC-E07", "90 days, 1 year, 2 YEARS and 6 month were all read correctly (singular, plural and capitals).")


def test_two_violations_on_one_record(record):
    out = audit([
        ["C1", "No", "2015-01-01", "1 year", "Active"],
        ["C2", "Yes", "2026-01-01", "5 years", "Active"],
    ], date(2026, 6, 1))
    assert codes(out) == ["CONSENT-01", "RETENTION-01"]
    assert out.violating_records == 1 and out.score == 50.0
    record("TC-E08", "2 findings, 1 violating record; score 50.00 (the record counted once).")


def test_score_arithmetic(record):
    today = date(2026, 6, 1)
    ten = [[f"C{i}", "Yes", "2026-01-01", "5 years", "Active"] for i in range(10)]
    assert audit(ten, today).score == 100.0
    for i in range(3):
        ten[i][1] = "No"
    assert audit(ten, today).score == 70.0
    for row in ten:
        row[1] = "No"
    assert audit(ten, today).score == 0.0
    third = audit([[f"C{i}", "No" if i == 0 else "Yes", "2026-01-01", "5 years", "Active"] for i in range(3)], today)
    assert third.score == 66.67
    record("TC-E09", "10 clean records: 100.00. 3 of 10 violating: 70.00. 10 of 10: 0.00. 1 of 3: 66.67 (rounded to two places).")


def test_text_variations_tolerated(record):
    out = audit([["C1", " NO ", "2026-01-01", " 5 years ", " active "]], date(2026, 6, 1))
    assert codes(out) == ["CONSENT-01"]
    record("TC-E10", "' NO ' and ' active ' were treated as No and Active; 1 finding.")


def test_new_rule_added_through_json_only(tmp_path, record):
    data = json.loads((ROOT / "data" / "knowledge_base" / "dpa_rules.json").read_text(encoding="utf-8"))
    data["rules"].append({
        "rule_code": "TEST-99", "category": "consent", "severity": "Low",
        "violation_type": "Test rule", "source_section": "n/a", "obligation_text": "Test.",
        "recommendation": "Test.", "check": {"type": "field_equals", "field": "record_status", "value": "Active"},
    })
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    rules = load_rules(path)
    out = audit_dataframe(pd.DataFrame([["C1", "Yes", "2026-01-01", "5 years", "Active"]], columns=COLUMNS), rules, date(2026, 6, 1))
    assert codes(out) == ["TEST-99"] and len(rules) == len(RULES) + 1
    record("TC-E11", "A third rule added to the JSON file alone was loaded and applied: 1 finding (TEST-99). No Python was changed.")


def test_incomplete_rules_are_refused(tmp_path, record):
    base = json.loads((ROOT / "data" / "knowledge_base" / "dpa_rules.json").read_text(encoding="utf-8"))
    missing = json.loads(json.dumps(base))
    del missing["rules"][0]["severity"]
    unknown = json.loads(json.dumps(base))
    unknown["rules"][0]["check"] = {"type": "made_up"}
    messages = []
    for label, content in (("missing key", missing), ("unknown check", unknown)):
        path = tmp_path / f"{label.replace(' ', '_')}.json"
        path.write_text(json.dumps(content), encoding="utf-8")
        with pytest.raises(RuleError) as error:
            load_rules(path)
        messages.append(f"{label}: {error.value}")
    record("TC-E12", "Both refused with RuleError. " + " / ".join(messages))


def test_two_rules_loaded_from_knowledge_base(record):
    assert [r["rule_code"] for r in RULES] == ["CONSENT-01", "RETENTION-01"]
    assert {r["category"] for r in RULES} == {"consent", "retention"}
    record("TC-E13", "The knowledge base provided 2 rules: CONSENT-01 (consent, Critical) and RETENTION-01 (retention, High).")


def generate(tmp_path, name, *extra):
    out = tmp_path / f"{name}.csv"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_synthetic_dataset.py"), "--out", str(out), *extra],
        check=True, capture_output=True,
    )
    return out


def compare_with_answer_key(csv_path):
    key = pd.read_csv(csv_path.with_name(csv_path.stem + "_answer_key.csv"), dtype=str)
    outcome = audit_file(csv_path, RULES)
    found = {rule: {f.record_id for f in outcome.findings if f.rule_code == rule} for rule in ("CONSENT-01", "RETENTION-01")}
    expected = {
        "CONSENT-01": set(key.loc[key.consent_violation == "Yes", "data_subject_id"]),
        "RETENTION-01": set(key.loc[key.retention_violation == "Yes", "data_subject_id"]),
    }
    return {r: (len(expected[r]), len(found[r]), len(expected[r] & found[r])) for r in expected}, outcome


def test_engine_matches_answer_key(tmp_path, record):
    parts = []
    for label, extra in (
        ("default 5,000 records", ("--rows", "5000")),
        ("heavily non-compliant 2,000 records", ("--rows", "2000", "--no-consent", "50", "--active-if-expired", "90", "--seed", "7")),
        ("fully compliant 1,000 records", ("--rows", "1000", "--no-consent", "0", "--active-if-expired", "0", "--seed", "3")),
    ):
        stats, outcome = compare_with_answer_key(generate(tmp_path, label.split()[0], *extra))
        for rule, (expected, found, true_pos) in stats.items():
            assert expected == found == true_pos, (label, rule, stats)
        parts.append(f"{label}: " + ", ".join(f"{r} expected {e}, found {f}, matched {t}" for r, (e, f, t) in stats.items()) + f"; score {outcome.score}")
    record("TC-E14", "Precision and recall were 100% for both rules in every dataset. " + " | ".join(parts))
