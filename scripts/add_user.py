"""
Add a new user to the system.

Run from the project folder:   python scripts/add_user.py
It asks for a username, email, role and password, then saves the user.
"""
import sys
from getpass import getpass
from pathlib import Path

# Lets this script find the "app" folder, which sits one level above "scripts".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import User

ROLES = {"1": "ComplianceOfficer", "2": "Administrator"}


def main():
    username = input("Username: ").strip()
    email = input("Email (the Google account they will sign in with): ").strip().lower()
    print("Role:  1 = Compliance Officer   2 = Administrator")
    role = ROLES.get(input("Choose 1 or 2: ").strip())
    password = getpass("Password (at least 8 characters; hidden as you type): ")

    if not username or not email or role is None or len(password) < 8:
        print("Not saved: fill in every field, choose 1 or 2, and use a password of 8+ characters.")
        return

    app = create_app()
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"Not saved: the username '{username}' is already taken.")
            return
        if User.query.filter(db.func.lower(User.email) == email).first():
            print(f"Not saved: {email} already belongs to another user.")
            return

        user = User(username=username, email=email, role=role)
        user.set_password(password)  # stores a scrambled version, never the real password
        db.session.add(user)
        db.session.commit()
        print(f"Done. '{username}' ({role}) was added with email {email}.")


if __name__ == "__main__":
    main()