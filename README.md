# KenyaDPA Audit

**An Automated Data Protection Act Compliance Auditing System Using NLP for Kenyan Organizations**

A web application that checks an organization's personal-data records against the Kenya Data Protection Act, 2019. A Compliance Officer uploads a dataset and a policy document. The system validates the data, audits every active record against the consent and retention rules, compares the policy with the Act, and produces a compliance score, a list of violations and a report. An Administrator manages the rules and the users.

This is an undergraduate final-year project (Computer Science, Strathmore University) by Martha Muinde. It is a proof of concept built on simulated data. It is **not legal advice**, and its findings should be reviewed by a qualified person.

---

## What it does

**For a Compliance Officer**
1. **Upload and validate a dataset.** A CSV is checked against a five-column schema. A file that fails cannot be audited, and the page says exactly which rows are wrong.
2. **Upload a policy document** (PDF, Word or text). Its text is extracted and stored.
3. **Run an audit.** Each active record is checked against the rules that are switched on. The policy is compared with the obligations of the Act using TF-IDF and cosine similarity, and each topic is marked *Addressed*, *Partly addressed* or *Not found*.
4. **Read the results:** dashboard, audit page (score, issues by severity, results by topic, policy alignment, affected records), reports list with filters, and a **PDF report** download.

**For an Administrator**
- **Compliance Rules:** switch rules on or off, edit them, add new ones, and review **rule candidates extracted from the Act** by the language-processing step.
- **User Management:** create accounts, change usernames and roles, reset passwords, deactivate and reactivate accounts.
- **System Logs:** who did what and when. Four monitoring figures on the rules page.

**For everyone:** sign in with a password or a registered Google account, sign up (as a Compliance Officer), reset a forgotten password by e-mail, and edit a profile with a picture.

### How the audit decides

| Area | Rule | A record breaks it when |
|---|---|---|
| Consent (Sections 30 and 32) | Processing without consent | `consent_status` is `No` but the record is still `Active` |
| Data retention (Section 39) | Retained beyond retention period | `collection_date` + `retention_period` is before the audit date but the record is still `Active` |

Only `Active` records are audited. The **compliance score** is the percentage of records with no violation. 80 or more is *Compliant*, 50 to 79 *Action Required*, below 50 *Critical Violations*; a compliant dataset whose policy leaves a topic *Not found* is marked *Review*. These bands are working values chosen for the prototype; the Act prescribes no scores.

### The language-processing part

1. `app/nlp/act_reader.py` reads the Act's PDF (scanned text with page headers and margin notes) into numbered provisions.
2. `app/nlp/extractor.py` uses **spaCy** to find duties ("shall", "must"), who must do what, and whether a provision concerns consent or retention. Duties on those topics become candidate rules.
3. An administrator approves or rejects each candidate. Approved rules join the policy comparison.
4. `app/nlp/similarity.py` compares policy statements with the rules (TF-IDF, cosine similarity, word stems, domain concept words and a topic gate). It is plain Python so the website needs no spaCy.

Measured results are produced by `scripts/evaluate_nlp_extraction.py` and `scripts/evaluate_policy_comparison.py`; see Chapter 5 of the report.

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

Python, Flask, PostgreSQL (Flask-SQLAlchemy, psycopg2), Flask-Login, pandas, pypdf, ReportLab (PDF), spaCy (language processing, development only), pytest, Faker. HTML templates, plain CSS and a little JavaScript.

## Project structure

```
app/
  auditing/    dataset validation, audit engine, policy reader, runner (no web code)
  nlp/         Act reader, rule extractor (spaCy), similarity and policy check
  models/      database tables
  routes/      pages: auth, account, upload, dashboard, reports, admin
  templates/   HTML pages          static/   CSS and JavaScript
  rules_store.py  status.py  activity.py  pdf_report.py  google_auth.py  mailer.py
data/
  knowledge_base/   dpa_rules.json (starting rules), act_candidates.json (extracted candidates)
  reference/        hand-labelled provisions and policy statements used to measure the NLP
  raw/legal/        the Data Protection Act and the ODPC handbook (PDF)
scripts/    data generator, evaluation scripts, rule extraction, environment report, database set-up
tests/      80 automated tests
migrations/ SQL to upgrade an existing database
schema.sql  render.yaml  wsgi.py  requirements.txt  requirements-dev.txt
```

## Getting started (Windows, PowerShell)

You need Python 3.11 and PostgreSQL.

```powershell
git clone https://github.com/Martha-M3/dpa-compliance-auditor.git
cd dpa-compliance-auditor
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m spacy download en_core_web_sm
psql -U postgres -c "CREATE DATABASE dpa_compliance_db;"
psql -U postgres -d dpa_compliance_db -f schema.sql
```

Create a `.env` file (it is ignored by Git):

```
SECRET_KEY=a-long-random-string
DB_NAME=dpa_compliance_db
DB_USER=postgres
DB_PASSWORD=your-postgres-password
DB_HOST=localhost
DB_PORT=5432
```

Create the first accounts and start the system:

```powershell
python seed_users.py      # prints a random password for 'admin' and 'officer' ONCE
python run.py
```

Open <http://127.0.0.1:5000>. **Upgrading an older database?** Run `psql -U postgres -d dpa_compliance_db -f migrations/2026-11-admin-and-nlp.sql` once.

Optional `.env` settings: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD` (password-reset e-mails; without them the link is printed in the terminal) and `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (the Google button; add `http://127.0.0.1:5000/auth/google/callback` as a redirect address in Google Cloud).

## Try it with sample data

```powershell
python scripts/generate_synthetic_dataset.py --rows 300 --no-consent 30 --out data/simulated/my_dataset.csv
```

Upload the file on **Upload Data**. Options: `--rows`, `--no-consent`, `--active-if-expired`, `--active-if-valid`, `--years`, `--id-prefix`, `--random` (run with `--help`). Each run also writes an answer key beside the dataset.

## Testing and evaluation

```powershell
pytest                                                    # 80 tests; results in tests/results/test_record.json
python scripts/evaluate_audit_engine.py data/simulated/synthetic_dataset.csv
python scripts/evaluate_nlp_extraction.py data/reference/act_reference_heldout.csv
python scripts/evaluate_policy_comparison.py
python scripts/extract_rules_from_act.py                  # rebuilds data/knowledge_base/act_candidates.json
python scripts/print_environment.py                       # versions of everything, for the report
```

The audit engine and its test data share one definition of a violation, so agreement shows the engine is *functionally correct*. The language-processing measurements use provisions and statements labelled by hand; the statement set was written by the researcher, so it is not an independent test.

## Deployment

`render.yaml` describes a free Render web service and database. Set `ADMIN_PASSWORD` (and `ADMIN_EMAIL`) on Render's Environment page to create the first Administrator. On Render's free plan uploaded files do not survive a restart.

## Known limitations

- Two obligations are audited: consent and retention (the scope of the project).
- Policy comparison is approximate. It shows where a policy appears to address a topic; a person must read the statement.
- Scanned (picture-only) documents cannot be read. Only English text is supported.
- Score bands, severities and the interpretation of Sections 30, 32 and 39 are the researcher's, not legal advice.
- Rule extraction reads the Act's duties but misses restrictive "may only" provisions and is tuned on a small hand-labelled set.
- The Settings page of the original wireframe was not built.

## Author

Martha Muinde, Strathmore University. Final-year project, 2026.
