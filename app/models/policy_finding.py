from app.extensions import db


class PolicyFinding(db.Model):
    """The result of comparing the organisation's policy with one topic of the Act during an audit (FR-08)."""
    __tablename__ = "policy_findings"
    finding_id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey("audit_runs.audit_id"), nullable=False)
    policy_id = db.Column(db.Integer, db.ForeignKey("policy_documents.document_id"), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    rule_id = db.Column(db.Integer, db.ForeignKey("compliance_rules.rule_id"))
    verdict = db.Column(db.String(20), nullable=False)     # Addressed | Partly addressed | Not found
    similarity = db.Column(db.Numeric(6, 4))
    best_statement = db.Column(db.Text)
    audit_run = db.relationship("AuditRun", backref="policy_findings")
    policy = db.relationship("PolicyDocument")
    rule = db.relationship("ComplianceRule")
