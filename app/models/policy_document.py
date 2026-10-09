from datetime import datetime

from app.extensions import db


class PolicyDocument(db.Model):
    __tablename__ = "policy_documents"

    document_id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    content_text = db.Column(db.Text)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)

    uploader = db.relationship("User", backref="policy_documents")