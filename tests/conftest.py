"""
Shared set-up for the automated tests.

Every test runs against a throw-away SQLite database and throw-away upload folders
inside a temporary directory, so running the tests never touches your real
PostgreSQL database or your real uploads.

Each test also calls record("TC-xxx", "what was observed"). At the end of the run
these observations and the pass/fail outcome of every test are written to
tests/results/test_record.json, which is the raw evidence for the testing chapter.
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")

from config import Config  # noqa: E402
from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402

OFFICER = ("officer", "OfficerPass1", "ComplianceOfficer", "officer@example.com")
ADMIN = ("admin", "AdminPass123", "Administrator", "admin@example.com")

_observations = {}
_outcomes = {}


@pytest.fixture()
def app(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
    Config.UPLOAD_FOLDER = tmp_path / "uploads" / "datasets"
    Config.POLICY_FOLDER = tmp_path / "uploads" / "policies"
    Config.PHOTO_FOLDER = tmp_path / "uploads" / "profile_photos"
    Config.GOOGLE_CLIENT_ID = "test-client-id"
    Config.GOOGLE_CLIENT_SECRET = "test-client-secret"
    Config.MAIL_SERVER = ""  # reset links are logged, never sent
    application = create_app()
    application.config.update(TESTING=True)
    with application.app_context():
        db.drop_all()
        db.create_all()
        for username, password, role, email in (OFFICER, ADMIN):
            user = User(username=username, role=role, email=email)
            user.set_password(password)
            db.session.add(user)
        db.session.commit()
    yield application


def _login(app, who):
    client = app.test_client()
    username, password, role, _ = who
    client.post("/login", data={"username": username, "password": password, "role": role})
    return client


@pytest.fixture()
def anon(app):
    return app.test_client()


@pytest.fixture()
def officer(app):
    return _login(app, OFFICER)


@pytest.fixture()
def admin(app):
    return _login(app, ADMIN)


@pytest.fixture()
def record(request):
    def _record(tc_id, observed):
        _observations[request.node.nodeid] = {"id": tc_id, "observed": observed}
    return _record


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _outcomes[item.nodeid] = report.outcome


def pytest_sessionfinish(session, exitstatus):
    results = {}
    for nodeid, info in _observations.items():
        results[info["id"]] = {
            "observed": info["observed"],
            "outcome": _outcomes.get(nodeid, "not run"),
            "test": nodeid.split("::")[-1],
        }
    out = Path(__file__).resolve().parent / "results"
    out.mkdir(exist_ok=True)
    (out / "test_record.json").write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
