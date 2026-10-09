from datetime import datetime

from app.extensions import db


class AuditRun(db.Model):
    __tablename__ = "audit_runs"

    audit_id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    end_time = db.Column(db.DateTime)
    compliance_score = db.Column(db.Numeric(5, 2))
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.dataset_id"), nullable=False)
    run_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)

    dataset = db.relationship("Dataset", backref="audit_runs")
    runner = db.relationship("User", backref="audit_runs")