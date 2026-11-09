"""
Where the compliance rules live at run time (FR-04, NFR-05).

The JSON knowledge base (data/knowledge_base/dpa_rules.json) is the starting set. The first time the
system needs rules it copies them into the database, and from then on the database is the working copy
that an administrator can edit, switch on and off, and extend. Copying never overwrites an edit: an
existing rule is only completed if its new fields are still empty (for example a database created before
those fields existed).
"""
import json

from app.auditing.engine import load_rules
from app.extensions import db
from app.models import ComplianceRule


def seed_rules():
    """Make sure every rule of the knowledge base exists in the database. Returns {rule_code: row}."""
    rows = {row.rule_code: row for row in ComplianceRule.query.all()}
    for rule in load_rules():
        row = rows.get(rule["rule_code"])
        if row is None:
            row = ComplianceRule(rule_code=rule["rule_code"], origin="knowledge_base", enabled=True)
            db.session.add(row)
            rows[rule["rule_code"]] = row
            row.category = rule["category"]
            row.obligation_text = rule["obligation_text"]
            row.source_section = rule["source_section"]
        # Fill fields that are still empty. Never replace something an administrator has written.
        if not row.severity:
            row.severity = rule["severity"]
        if not row.violation_type:
            row.violation_type = rule["violation_type"]
        if not row.recommendation:
            row.recommendation = rule["recommendation"]
        if not row.check_config:
            row.check_config = json.dumps(rule["check"])
        if row.enabled is None:
            row.enabled = True
        if not row.origin:
            row.origin = "knowledge_base"
    db.session.flush()
    return rows


def dataset_rules(enabled_only=True):
    """Rules the audit engine can apply to dataset records, as engine dictionaries, oldest first."""
    query = ComplianceRule.query.filter(ComplianceRule.check_config.isnot(None))
    if enabled_only:
        query = query.filter(ComplianceRule.enabled.is_(True))
    return [row.as_engine_rule() for row in query.order_by(ComplianceRule.rule_id).all()]


def policy_rules():
    """Enabled rules whose obligation text is compared with the organisation's policy."""
    return ComplianceRule.query.filter(ComplianceRule.enabled.is_(True)).order_by(ComplianceRule.rule_id).all()
