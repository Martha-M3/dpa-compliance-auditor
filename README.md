# KenyaDPA Audit

**An Automated Data Protection Act Compliance Auditing System Using NLP for Kenyan Organizations**

A web application that checks an organization's personal-data records against the
Kenya Data Protection Act, 2019. A Compliance Officer uploads a dataset, the system
validates it, audits every record against rules held in a knowledge base, and produces
a compliance score, a list of violations and a report with recommendations.

This is an undergraduate final-year project (Computer Science, Strathmore University)
by Martha Muinde. It is a proof of concept built on simulated data. It is **not legal
advice**, and its findings should be reviewed by a qualified person.

---

## What it does

1. **Upload and validate a dataset.** The CSV is checked against a standard
   five-column schema. A file that fails cannot be audited, and the page says exactly
   which rows are wrong.
2. **Run an automated audit.** Each active record is checked against the compliance
   rules and every breach is saved with its severity and a plain-English explanation.
3. **Read the results.**
   - **Dashboard:** overall compliance health, violations by severity and category,
     recent audits and alerts.
   - **Audit screen:** score, issues by severity, a tab for each area of the Act,
     the result of each rule, and the list of affected records.
   - **Reports:** a filterable list of all audits with a summary preview and a
     printable one-page summary that can be saved as a PDF.
4. **Upload an organization policy document** (PDF, Word or text). The text is
   extracted and stored for the policy comparison planned next.
5. **Sign in** with a username and password, with a "Forgot password?" email link,
   or with a Google account that is already registered. Two roles are supported:
   Compliance Officer and Administrator.

### What is checked today

| Area | Rule | A record breaks it when |
|---|---|---|
| Consent | Processing without consent | `consent_status` is `No` but the record is still `Active` |
| Data retention | Retained beyond retention period | `collection_date` + `retention_period` has passed but the record is still `Active` |

Only `Active` records are audited, because an inactive record is no longer being
processed. The **compliance score** is the percentage of records with no violation.

The rules live in `data/knowledge_base/dpa_rules.json`, not in the code, so a new
rule can be added without changing any Python.

### Dataset format

A CSV (UTF-8) with a heading row and these five columns:

| Column | Example |
|---|---|
| `data_subject_id` | `Customer10432` |
| `consent_status` | `Yes` or `No` |
| `collection_date` | `2024-03-31` |
| `retention_period` | `5 years`, `6 months` or `90 days` |
| `record_status` | `Active` or `Inactive` |



## Technology

- **Language and framework:** Python 3.11, Flask
- **Database:** PostgreSQL, accessed through Flask-SQLAlchemy
- **Authentication:** Flask-Login
- **Data handling:** pandas
- **Policy documents:** pypdf (PDF), built-in `zipfile` (Word)
- **Test data:** Faker
- **Interface:** server-rendered HTML templates, plain CSS and a little JavaScript
- **Planned:** spaCy and scikit-learn for the NLP stage

## Project structure

```
dpa-compliance-auditor/
├── app/
│   ├── __init__.py            App factory: creates and configures the Flask app
│   ├── auditing/
│   │   ├── dataset_schema.py  Validates an uploaded CSV
│   │   ├── engine.py          Applies the rules to each record and scores the audit
│   │   ├── runner.py          Connects the engine to the database
│   │   └── policy_reader.py   Extracts text from PDF, Word and text policies
│   ├── models/                Database tables (users, datasets, audits, rules, ...)
│   ├── routes/                Pages: auth, dashboard, upload, reports
│   ├── templates/             HTML pages
│   ├── static/                CSS and JavaScript
│   ├── google_auth.py         Sign in with Google
│   └── mailer.py              Sends password-reset emails
├── data/
│   ├── knowledge_base/        dpa_rules.json: the compliance rules
│   └── simulated/             Generated test datasets and answer keys
├── scripts/
│   ├── generate_synthetic_dataset.py
│   └── evaluate_audit_engine.py
├── config.py                  Settings, read from the .env file
├── run.py                     Starts the app
├── schema.sql                 Creates the database tables
└── requirements.txt           Python packages
```

## Getting started

These steps are for Windows with PowerShell. You need Python 3.11 and PostgreSQL.

### 1. Get the code and install the packages

```powershell
git clone https://github.com/Martha-M3/dpa-compliance-auditor.git
cd dpa-compliance-auditor
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Create the database

```powershell
psql -U postgres -c "CREATE DATABASE dpa_compliance_db;"
psql -U postgres -d dpa_compliance_db -f schema.sql
```

### 3. Create the `.env` file

Create a file named `.env` in the project folder (it is ignored by Git, so your
secrets are never uploaded):

```
SECRET_KEY=a-long-random-string
DB_NAME=dpa_compliance_db
DB_USER=postgres
DB_PASSWORD=your-postgres-password
DB_HOST=localhost
DB_PORT=5432
```

Generate a secret key with:
`python -c "import secrets; print(secrets.token_hex(32))"`

### 4. Create the first user

There is no sign-up page yet, so create accounts from a Python prompt. Run `python`,
then paste:

```python
from app import create_app
from app.extensions import db
from app.models import User

app = create_app()
with app.app_context():
    user = User(username="officer", email="officer@example.com", role="ComplianceOfficer")
    user.set_password("ChangeMe123")
    db.session.add(user)
    db.session.commit()
```

Use `role="Administrator"` for an administrator account.

### 5. Run it

```powershell
python run.py
```

Open <http://127.0.0.1:5000>, choose the role, and sign in.

## Optional settings

Add these to `.env` only if you want them. The app works without them.

**Password-reset emails.** Without these, the reset link is printed in the terminal
instead of being emailed, which is enough for development.

```
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your.address@gmail.com
MAIL_PASSWORD=your-app-password
```

**Sign in with Google.** Create an OAuth client in Google Cloud and add the redirect
addresses `http://127.0.0.1:5000/auth/google/callback` and
`http://localhost:5000/auth/google/callback`. Then:

```
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
```

The "Continue with Google" button appears once both are set. Google sign-in only
admits people whose verified Google email matches an existing account.

## Try it with sample data

Generate a test dataset in which some records are deliberately non-compliant, then
upload it on the **Upload Data** page:

```powershell
python scripts/generate_synthetic_dataset.py
```

This writes `data/simulated/synthetic_dataset.csv` and an answer key that lists the
records that were made non-compliant.

## Testing

Check the audit engine against the answer key. The script reports, for each rule, how
many violations were expected and found, with precision, recall and F1:

```powershell
python scripts/generate_synthetic_dataset.py --rows 5000 --out data/simulated/perf_5000.csv
python scripts/evaluate_audit_engine.py data/simulated/perf_5000.csv
```

The engine and the generator share the same definition of a violation, so a perfect
score here shows the engine is **functionally correct**. It does not measure how well
the planned NLP stage will read real legal text. That needs a separate, hand-annotated
reference set.

## Known limitations

- The audit covers two obligations, consent and retention, as set out in the project
  scope. It does not cover the whole Act.
- Policy documents are uploaded and read, but not yet compared with the Act.
- Scanned (picture-only) documents cannot be read. Only English text is supported.
- Score bands and severity levels are provisional and should be confirmed with the
  supervisor.
- The "Download PDF" button opens the browser's print dialog. Choose *Save as PDF*.
- Requests for password-reset emails are not rate-limited.

## Troubleshooting

- **"Application Control policy has blocked this file" when starting the app.**
  Windows has blocked a newly installed package. Recreate the virtual environment with
  Python 3.11 and reinstall from `requirements.txt`, which pins versions known to work.
- **Google shows `redirect_uri_mismatch`.** The address in your browser must match a
  redirect address registered in Google Cloud. Use `127.0.0.1` or `localhost`
  consistently.

## Author

Martha Muinde, Strathmore University. Final-year project, 2026.