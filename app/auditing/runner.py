"""
Connects the audit engine to the database (FR-09, FR-12).

The engine itself knows nothing about the database. This module:
  1. makes sure the rules from the JSON knowledge base exist in compliance_rules,
  2. creates an AuditRun and runs the engine on the stored dataset file with the rules that are switched on,
  3. saves every violation as an AuditResult,
  4. compares the latest policy document with the obligations and saves the findings (FR-08),
  5. saves the score and a report record.
"""
from datetime import datetime

from app import rules_store
from app.activity import log_event
from app.auditing.engine import audit_file
from app.extensions import db
from app.models import AuditResult, AuditRun, ComplianceReport, PolicyDocument, PolicyFinding
from app.nlp.policy_check import assess_policy


class NoRulesError(Exception):
    """Raised when no dataset rule is switched on, so there is nothing to audit against."""


def run_audit(dataset, user, path):
    """
    Audit one validated dataset and save everything to the database.
    Returns (audit_run, outcome). The caller must roll back if this raises.
    """
    rule_rows = rules_store.seed_rules()
    rules = rules_store.dataset_rules(enabled_only=True)
    if not rules:
        raise NoRulesError("No audit rules are switched on.")

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

    # Compare the most recently uploaded policy with the obligations (FR-08). No policy: nothing to compare.
    policy = PolicyDocument.query.order_by(PolicyDocument.upload_date.desc(), PolicyDocument.document_id.desc()).first()
    if policy is not None and policy.content_text:
        for found in assess_policy(policy.content_text, rules_store.policy_rules()):
            db.session.add(PolicyFinding(
                audit_id=audit.audit_id,
                policy_id=policy.document_id,
                category=found["category"],
                rule_id=found["rule"].rule_id,
                verdict=found["verdict"],
                similarity=found["similarity"],
                best_statement=found["best_statement"][:2000],
            ))

    audit.compliance_score = outcome.score
    audit.end_time = datetime.utcnow()
    db.session.add(ComplianceReport(audit_id=audit.audit_id))
    log_event("audit_run", f"{dataset.file_name}: score {outcome.score}, {len(outcome.findings)} violations", user=user)
    db.session.commit()
    return audit, outcome
