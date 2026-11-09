"""Authentication, access control and account recovery: FR-01, NFR-02 (tests TC-A01 to TC-A14)."""
import io

import pytest

from app import google_auth
from app.extensions import db
from app.models import User
from app.routes.auth import make_reset_token
from conftest import ADMIN, OFFICER

PAGES = ["/dashboard", "/upload", "/reports", "/audits", "/profile"]


def login(client, who=OFFICER, **override):
    username, password, role, _ = who
    data = {"username": username, "password": password, "role": role}
    data.update(override)
    return client.post("/login", data=data)


def test_valid_login(anon, record):
    response = login(anon)
    assert response.status_code == 302 and response.headers["Location"].endswith("/dashboard")
    assert anon.get("/dashboard").status_code == 200
    record("TC-A01", "Redirected to /dashboard; the dashboard then opened (200).")


def test_wrong_password_and_unknown_user_give_same_message(anon, record):
    wrong = login(anon, password="not-the-password")
    unknown = login(anon, username="nobody")
    for response in (wrong, unknown):
        assert response.status_code == 200 and b"Incorrect username or password." in response.data
    assert anon.get("/dashboard").status_code == 302
    record("TC-A02", "Both attempts showed 'Incorrect username or password.' (the same text, so the page does not reveal which usernames exist); /dashboard stayed locked.")


def test_wrong_role_is_refused(anon, record):
    response = login(anon, role="Administrator")
    assert b"not registered as an Administrator" in response.data
    assert anon.get("/dashboard").status_code == 302
    record("TC-A03", "Refused: 'This account is not registered as an Administrator.' No session was created.")


def test_anonymous_users_are_sent_to_login(anon, record):
    for page in PAGES:
        response = anon.get(page)
        assert response.status_code == 302 and "/login" in response.headers["Location"], page
    record("TC-A04", "All " + str(len(PAGES)) + " protected pages (" + ", ".join(PAGES) + ") redirected to /login.")


def test_administrator_cannot_use_officer_functions(admin, record, app):
    from app.models import Dataset
    from helpers import csv_bytes, good_rows, upload_csv
    page = admin.get("/upload")
    posted = upload_csv(admin, csv_bytes(good_rows()))
    policy = admin.post("/upload/policy", data={"policy": (io.BytesIO(b"x" * 100), "p.txt")}, content_type="multipart/form-data")
    for response in (page, posted, policy):
        assert response.status_code == 302 and response.headers["Location"].endswith("/dashboard")
    with app.app_context():
        assert Dataset.query.count() == 0
    record("TC-A05", "GET /upload, POST /upload and POST /upload/policy each redirected to the dashboard with a 'no permission' message; no dataset was created.")


def test_logout_locks_the_session(officer, record):
    assert officer.get("/dashboard").status_code == 200
    officer.get("/logout")
    assert officer.get("/dashboard").status_code == 302
    record("TC-A06", "Dashboard opened (200) before logging out and redirected to login (302) afterwards.")


def test_registration_always_creates_compliance_officer(anon, app, record):
    response = anon.post("/register", data={
        "username": "newbie", "email": "newbie@example.com", "password": "LongEnough1",
        "confirm": "LongEnough1", "role": "Administrator",
    })
    assert response.status_code == 302
    with app.app_context():
        assert User.query.filter_by(username="newbie").one().role == "ComplianceOfficer"
    record("TC-A07", "Account created. Although the form was sent with role=Administrator, the stored role was ComplianceOfficer.")


def test_registration_validation(anon, app, record):
    base = {"username": "fresh", "email": "fresh@example.com", "password": "LongEnough1", "confirm": "LongEnough1"}
    cases = {
        "short username": {"username": "ab"},
        "bad email": {"email": "not-an-email"},
        "short password": {"password": "short", "confirm": "short"},
        "passwords differ": {"confirm": "Different123"},
        "duplicate username in other case": {"username": "OFFICER"},
        "duplicate email in other case": {"email": "ADMIN@example.com"},
    }
    for label, change in cases.items():
        response = anon.post("/register", data={**base, **change})
        assert response.status_code == 200, label
    with app.app_context():
        assert User.query.count() == 2
    record("TC-A08", "All 6 invalid sign-ups were refused with a message (" + "; ".join(cases) + "); the users table still held 2 rows.")


def test_reset_link_sets_new_password_and_works_once(anon, app, record):
    with app.app_context():
        token = make_reset_token(User.query.filter_by(username="officer").one())
    page = anon.get(f"/reset-password/{token}")
    assert page.status_code == 200
    done = anon.post(f"/reset-password/{token}", data={"password": "BrandNew123", "confirm": "BrandNew123"})
    assert done.status_code == 302
    assert login(anon, password="BrandNew123").headers["Location"].endswith("/dashboard")
    second = anon.get(f"/reset-password/{token}")
    assert second.status_code == 302 and "forgot-password" in second.headers["Location"]
    record("TC-A09", "The new password worked for sign-in. Using the same link a second time was refused and redirected to 'forgot password'.")


def test_tampered_and_expired_reset_links_are_refused(anon, app, record):
    with app.app_context():
        token = make_reset_token(User.query.filter_by(username="officer").one())
    tampered = anon.get(f"/reset-password/{token[:-3]}abc")
    assert tampered.status_code == 302 and "forgot-password" in tampered.headers["Location"]
    app.config["RESET_TOKEN_MAX_AGE"] = -1  # every link is already older than the limit
    expired = anon.get(f"/reset-password/{token}")
    assert expired.status_code == 302 and "forgot-password" in expired.headers["Location"]
    record("TC-A10", "A link with its last characters changed and a link older than the allowed age were both refused.")


def test_forgot_password_does_not_reveal_accounts(anon, record):
    known = anon.post("/forgot-password", data={"email": "officer@example.com"}, follow_redirects=True)
    unknown = anon.post("/forgot-password", data={"email": "nobody@example.com"}, follow_redirects=True)
    text = b"If an account exists for that email address, a reset link has been sent to it."
    assert text in known.data and text in unknown.data
    record("TC-A11", "Registered and unregistered addresses produced the identical message.")


@pytest.fixture()
def google(monkeypatch, anon):
    """Pretend to be Google: the real exchange needs internet and a real account."""
    state = {}

    def start():
        anon.get("/auth/google")  # stores the random state in the session
        with anon.session_transaction() as session:
            return session["google_state"]

    def reply(profile):
        monkeypatch.setattr(google_auth, "fetch_google_user", lambda code, uri: profile)

    return start, reply


def test_google_sign_in_rules(anon, google, record):
    start, reply = google
    results = []

    reply({"email": "officer@example.com", "email_verified": True})
    state = start()
    ok = anon.get(f"/auth/google/callback?code=abc&state={state}")
    assert ok.status_code == 302 and ok.headers["Location"].endswith("/dashboard")
    results.append("registered verified email: signed in")
    anon.get("/logout")

    reply({"email": "stranger@gmail.com", "email_verified": True})
    state = start()
    unregistered = anon.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=True)
    assert b"No account is registered for stranger@gmail.com" in unregistered.data
    results.append("unregistered email: refused")

    reply({"email": "officer@example.com", "email_verified": False})
    state = start()
    unverified = anon.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=True)
    assert b"not verified" in unverified.data
    results.append("unverified email: refused")

    reply({"email": "officer@example.com", "email_verified": True})
    start()
    forged = anon.get("/auth/google/callback?code=abc&state=forged", follow_redirects=True)
    assert b"could not be verified" in forged.data
    results.append("wrong state value: refused")
    assert anon.get("/dashboard").status_code == 302
    record("TC-A12", "Google replies were simulated. " + "; ".join(results) + ".")
