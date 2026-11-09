"""
Print the versions of everything the system runs on, ready to copy into Table 5.1 / 5.2
of the report (configuration evidence).

Run from the project root with the virtual environment active:
    python scripts/print_environment.py

It never prints passwords: the database address is shown without the password.
"""
import platform
import sys
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PACKAGES = [
    "Flask", "Flask-SQLAlchemy", "Flask-Login", "SQLAlchemy", "psycopg2-binary", "pandas",
    "python-dateutil", "pypdf", "Faker", "python-dotenv", "itsdangerous", "Werkzeug", "gunicorn", "pytest",
]


def version_of(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def main():
    print("Operating system :", platform.platform())
    print("Processor        :", platform.processor() or "(not reported)")
    print("Python           :", sys.version.split()[0])
    print()
    print("Packages")
    for name in PACKAGES:
        print(f"  {name:<18} {version_of(name)}")
    print()
    try:
        from sqlalchemy import text
        from app import create_app
        from app.extensions import db

        app = create_app()
        with app.app_context():
            url = db.engine.url
            print("Database         :", url.render_as_string(hide_password=True))
            print("Database version :", db.session.execute(text("select version()")).scalar())
    except Exception as error:  # the report is still useful without a database
        print("Database         : could not connect (" + type(error).__name__ + ")")


if __name__ == "__main__":
    main()
