from datetime import datetime

from app.extensions import db


class CandidateReview(db.Model):
    """An administrator's decision on a rule candidate extracted from the Act (approved or rejected)."""
    __tablename__ = "candidate_reviews"
    candidate_code = db.Column(db.String(30), primary_key=True)
    decision = db.Column(db.String(10), nullable=False)     # approved | rejected
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    reviewed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
