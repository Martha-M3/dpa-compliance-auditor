from datetime import datetime

from app.extensions import db


class ActivityLog(db.Model):
    """A line in the system log: who did what and when (FR-03). Passwords and file contents are never logged."""
    __tablename__ = "activity_log"
    log_id = db.Column(db.Integer, primary_key=True)
    logged_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    username = db.Column(db.String(100))          # kept even if the user is later changed
    action = db.Column(db.String(40), nullable=False)
    detail = db.Column(db.String(300))
    user = db.relationship("User")
