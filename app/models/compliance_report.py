from datetime import datetime

from app.extensions import db


class ComplianceReport(db.Model):
    __tablename__ = "compliance_reports"

    report_id = db.Column(db.Integer, primary_key=True)
    generated_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    file_path = db.Column(db.String(255))
    audit_id = db.Column(
        db.Integer, db.ForeignKey("audit_runs.audit_id"), unique=True, nullable=False
    )

    audit_run = db.relationship(
        "AuditRun", backref=db.backref("compliance_report", uselist=False)
    )