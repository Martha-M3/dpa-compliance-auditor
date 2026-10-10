"""
Connects the audit engine to the database (FR-09, FR-12).

The engine itself knows nothing about the database. This module:
  1. makes sure the rules from the JSON knowledge base exist in compliance_rules,
  2. creates an AuditRun, runs the engine on the stored dataset file,
  3. saves every violation as an AuditResult, plus the score and a report record.
"""
from datetime import datetime

from app.auditing.engine import audit_file, load_rules
from app.extensions import db
from app.models import AuditResult, AuditRun, ComplianceReport, ComplianceRule


def sync_rules(rules):
    """
    Copy the rules from the JSON file into the compliance_rules table.
    New rules are added; existing ones (matched by rule_code) are updated.
    Returns a dictionary {rule_code: ComplianceRule row}.
    """
    rows = {row.rule_code: row for row in ComplianceRule.query.all()}

    for rule in rules:
        row = rows.get(rule["rule_code"])
        if row is None:
            row = ComplianceRule(rule_code=rule["rule_code"])
            db.session.add(row)
            rows[rule["rule_code"]] = row
        row.category = rule["category"]
        row.obligation_text = rule["obligation_text"]
        row.source_section = rule["source_section"]

    db.session.flush()   # gives any new rows their rule_id
    return rows


def run_audit(dataset, user, path):
    """
    Audit one validated dataset and save everything to the database.
    Returns (audit_run, outcome). The caller must roll back if this raises.
    """
    rules = load_rules()
    rule_rows = sync_rules(rules)

    audit = AuditRun(
        dataset_id=dataset.dataset_id,
        run_by=user.user_id,
        start_time=datetime.utcnow(),
    )
    db.session.add(audit)
    db.session.flush()   # gives the audit its audit_id

    outcome = audit_file(path, rules)

    db.session.add_all(
        AuditResult(
            record_id=finding.record_id,
            violation_type=finding.violation_type,
            severity=finding.severity,
            description=finding.description,
            audit_id=audit.audit_id,
            rule_id=rule_rows[finding.rule_code].rule_id,
        )
        for finding in outcome.findings
    )

    audit.compliance_score = outcome.score
    audit.end_time = datetime.utcnow()
    db.session.add(ComplianceReport(audit_id=audit.audit_id))
    db.session.commit()
    return audit, outcome