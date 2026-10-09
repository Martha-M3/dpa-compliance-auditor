from app.extensions import db


class AuditResult(db.Model):
    __tablename__ = "audit_results"

    result_id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.String(100), nullable=False)
    violation_type = db.Column(db.String(100), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text)
    audit_id = db.Column(db.Integer, db.ForeignKey("audit_runs.audit_id"), nullable=False)
    rule_id = db.Column(db.Integer, db.ForeignKey("compliance_rules.rule_id"), nullable=False)

    audit_run = db.relationship("AuditRun", backref="audit_results")
    rule = db.relationship("ComplianceRule", backref="audit_results")