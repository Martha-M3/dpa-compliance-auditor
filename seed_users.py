"""
Create a first Administrator and a Compliance Officer for local use.

    python seed_users.py

Each account gets a random password that is printed ONCE here. Write it down, sign in, and change it
from the profile page. To choose your own, set SEED_ADMIN_PASSWORD or SEED_OFFICER_PASSWORD first.
"""
import os
import secrets

from app import create_app
from app.extensions import db
from app.models import User

app = create_app()

with app.app_context():
    for username, role, label, env in (("admin", "Administrator", "Administrator", "SEED_ADMIN_PASSWORD"),
                                       ("officer", "ComplianceOfficer", "Compliance Officer", "SEED_OFFICER_PASSWORD")):
        if User.query.filter_by(username=username).first() is not None:
            print(f"'{username}' already exists, skipping.")
            continue
        password = os.environ.get(env) or secrets.token_urlsafe(9)
        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        print(f"Created {label}: {username}   password: {password}")
    db.session.commit()
    print("Done. Change these passwords from the profile page.")
