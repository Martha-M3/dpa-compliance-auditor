from app.extensions import db


class ComplianceRule(db.Model):
    __tablename__ = "compliance_rules"

    rule_id = db.Column(db.Integer, primary_key=True)
    obligation_text = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    source_section = db.Column(db.String(100))