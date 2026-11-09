import json
from datetime import datetime

from app.extensions import db


class ComplianceRule(db.Model):
    """
    One compliance rule. Rules come from three places (`origin`): the JSON knowledge base that ships with
    the system, candidates extracted from the Act and approved by an administrator, and rules an
    administrator typed in. A rule with a `check_config` can be applied to dataset records by the audit
    engine. A rule without one is a policy obligation: it is only compared with policy documents.
    """
    __tablename__ = "compliance_rules"
    rule_id = db.Column(db.Integer, primary_key=True)
    rule_code = db.Column(db.String(30), unique=True, nullable=False)
    obligation_text = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    source_section = db.Column(db.String(100))
    violation_type = db.Column(db.String(100))
    severity = db.Column(db.String(20))
    recommendation = db.Column(db.Text)
    check_config = db.Column(db.Text)                      # JSON, for example {"type": "field_equals", ...}
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    origin = db.Column(db.String(20), nullable=False, default="knowledge_base")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def check(self):
        return json.loads(self.check_config) if self.check_config else None

    @property
    def is_dataset_rule(self):
        return bool(self.check_config)

    def as_engine_rule(self):
        """The dictionary form the audit engine expects."""
        return {
            "rule_code": self.rule_code,
            "category": self.category,
            "severity": self.severity or "Medium",
            "violation_type": self.violation_type or self.rule_code,
            "source_section": self.source_section or "",
            "obligation_text": self.obligation_text,
            "recommendation": self.recommendation or "",
            "check": self.check,
        }
