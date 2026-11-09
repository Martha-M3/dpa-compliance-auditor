"""
Create the database tables (safe to run again: it only creates tables that are missing) and, if asked,
the first Administrator.

On Render this runs every time the site starts (see render.yaml). You can also run it yourself:
    python scripts/init_db.py

To create the first Administrator, set these settings (in .env, or in Render's Environment page):
    ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD
The account is created only if no Administrator exists yet, so restarting never changes a password.
"""
import os
import sys
from pathlib import Path

# Lets this script find the "app" folder, which sits one level above "scripts".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import User


def main():
    app = create_app()
    with app.app_context():
        db.create_all()
        print("Database tables are ready.")

        username = os.environ.get("ADMIN_USERNAME", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        email = os.environ.get("ADMIN_EMAIL", "").strip().lower() or None
        if username and password:
            if User.query.filter_by(role="Administrator").first() is None:
                admin = User(username=username, email=email, role="Administrator", full_name="System Administrator")
                admin.set_password(password)
                db.session.add(admin)
                db.session.commit()
                print(f"Created the Administrator '{username}'.")
            else:
                print("An Administrator already exists, so no account was created.")


if __name__ == "__main__":
    main()
