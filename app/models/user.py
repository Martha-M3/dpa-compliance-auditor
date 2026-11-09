from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "users"
    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True)  # used for Google sign-in and password reset
    full_name = db.Column(db.String(150))
    phone = db.Column(db.String(30))
    job_title = db.Column(db.String(100))
    department = db.Column(db.String(100))
    photo_filename = db.Column(db.String(255))  # file inside uploads/profile_photos, or None
    active = db.Column(db.Boolean, nullable=False, default=True)  # False = deactivated by an administrator
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        """Flask-Login refuses to sign in (or keep signed in) a user for whom this is False."""
        return bool(self.active)

    def get_id(self):
        return str(self.user_id)

    @property
    def display_name(self):
        """The name to show people: the full name if they gave one, else the username."""
        return self.full_name or self.username

    @property
    def first_name(self):
        return (self.full_name or self.username).split()[0]

    @property
    def role_label(self):
        return "Compliance Officer" if self.role == "ComplianceOfficer" else "Administrator"
