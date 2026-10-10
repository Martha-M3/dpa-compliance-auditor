"""
Rule-based compliance auditing engine (FR-10, FR-11, FR-12).

The engine reads the compliance rules from the JSON knowledge base (NFR-05) and
checks every ACTIVE record in a validated dataset against them. It returns a
list of findings and a compliance score. It does not touch the database, so it
is easy to test on its own; saving the results is done elsewhere.
"""
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
from dateutil.relativedelta import relativedelta

from app.auditing.dataset_schema import RETENTION_PATTERN

# <project root>/data/knowledge_base/dpa_rules.json
RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "dpa_rules.json"

REQUIRED_RULE_KEYS = [
    "rule_code", "category", "severity", "violation_type",
    "source_section", "obligation_text", "recommendation", "check",
]
KNOWN_CHECKS = {"field_equals", "retention_expired"}


class RuleError(Exception):
    """Raised when the rules file is missing something or has an unknown check."""


@dataclass
class Finding:
    """One violation: one record that broke one rule."""
    record_id: str
    rule_code: str
    violation_type: str
    severity: str
    description: str


@dataclass
class AuditOutcome:
    """Everything an audit produces, ready to be saved or displayed."""
    audit_date: date
    records_checked: int
    violating_records: int
    score: float
    findings: list = field(default_factory=list)


def load_rules(path=RULES_PATH):
    """Read the JSON knowledge base and make sure every rule is complete."""
    with open(path, encoding="utf-8") as f:
        rules = json.load(f)["rules"]

    for rule in rules:
        missing = [key for key in REQUIRED_RULE_KEYS if key not in rule]
        if missing:
            raise RuleError(f"Rule {rule.get('rule_code', '?')} is missing: {', '.join(missing)}")
        if rule["check"].get("type") not in KNOWN_CHECKS:
            raise RuleError(f"Rule {rule['rule_code']} uses an unknown check type.")
    return rules


def retention_end(collected, period_text):
    """
    The derived field retention_expiry_date (Table 4.3):
    collection_date plus retention_period, e.g. 2023-01-31 + '1 month'.
    """
    match = RETENTION_PATTERN.match(period_text)
    amount = int(match.group(1))
    unit = match.group(2).lower().rstrip("s")   # 'years' -> 'year'
    if unit == "year":
        return collected + relativedelta(years=amount)
    if unit == "month":
        return collected + relativedelta(months=amount)
    return collected + relativedelta(days=amount)


def _check_record(rule, record, today):
    """Apply one rule to one record. Returns a description if violated, else None."""
    check = rule["check"]

    if check["type"] == "field_equals":
        actual = record[check["field"]].strip()
        if actual.lower() == check["value"].lower():
            return f"{check['field']} is '{actual}' but the record is still Active."

    elif check["type"] == "retention_expired":
        collected = date.fromisoformat(record["collection_date"].strip())
        ends = retention_end(collected, record["retention_period"])
        if ends < today:
            period = record["retention_period"].strip()
            return (
                f"Retention period of {period} from {collected} ended on {ends}, "
                "but the record is still Active."
            )
    return None


def audit_dataframe(df, rules, today=None):
    """
    Audit a dataset that has already passed schema validation.
    Only Active records are checked: an Inactive record is no longer being
    processed, so it cannot breach consent or retention rules.
    """
    today = today or date.today()
    findings = []
    violating_rows = set()

    for row_number, record in enumerate(df.to_dict("records")):
        if record["record_status"].strip().lower() != "active":
            continue
        for rule in rules:
            description = _check_record(rule, record, today)
            if description:
                findings.append(
                    Finding(
                        record_id=record["data_subject_id"].strip(),
                        rule_code=rule["rule_code"],
                        violation_type=rule["violation_type"],
                        severity=rule["severity"],
                        description=description,
                    )
                )
                violating_rows.add(row_number)

    total = len(df)
    # Score = share of records with no violation (a record with two violations counts once).
    score = round(100 * (total - len(violating_rows)) / total, 2) if total else 0.0
    return AuditOutcome(
        audit_date=today,
        records_checked=total,
        violating_records=len(violating_rows),
        score=score,
        findings=findings,
    )


def audit_file(path, rules=None, today=None):
    """Read a stored CSV and audit it."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [str(c).strip().lower() for c in df.columns]   # same tidy-up as validation
    return audit_dataframe(df, rules or load_rules(), today)