"""
Dataset schema validation (Table 4.3, NFR-03, IR-02).

Before a dataset can be audited we must be sure it has the columns and the
kinds of values the audit engine expects. This module reads an uploaded CSV
and runs five checks on it. It never crashes on bad input: every problem is
turned into a plain-English message the user can act on.
"""
import re
from dataclasses import dataclass, field

import pandas as pd

# The standardized schema (Table 4.3). The audit engine relies on these.
REQUIRED_COLUMNS = [
    "data_subject_id",
    "consent_status",
    "collection_date",
    "retention_period",
    "record_status",
]

ALLOWED_CONSENT = {"yes", "no"}
ALLOWED_STATUS = {"active", "inactive"}

# "5 years", "1 year", "6 months", "90 days" (a number, a space, a unit)
RETENTION_PATTERN = re.compile(r"^\s*(\d+)\s*(year|years|month|months|day|days)\s*$", re.IGNORECASE)

# How many example problems to show per check, so a bad file of 50,000 rows
# does not produce a 50,000-line message.
MAX_EXAMPLES = 5


@dataclass
class CheckResult:
    """The outcome of one check: its name, whether it passed, and a message."""
    name: str
    passed: bool
    message: str


@dataclass
class ValidationResult:
    """Everything the upload page needs to know about a file."""
    checks: list = field(default_factory=list)
    row_count: int = 0

    checks: list = field(default_factory=list)
    row_count: int = 0
    columns: list = field(default_factory=list)  # column headings found in the file

    @property
    def passed(self):
        # The file is valid only if EVERY check passed.
        return all(c.passed for c in self.checks)


def _describe_rows(row_numbers):
    """Turn [5, 9, 12, ...] into 'rows 5, 9, 12 (and 20 more)'."""
    shown = ", ".join(str(n) for n in row_numbers[:MAX_EXAMPLES])
    extra = len(row_numbers) - MAX_EXAMPLES
    label = "row" if len(row_numbers) == 1 else "rows"
    if extra > 0:
        return f"{label} {shown} (and {extra} more)"
    return f"{label} {shown}"


def _file_readable_check(path):
    """Check 1: can we open it as a non-empty CSV? Returns (check, DataFrame or None)."""
    name = "File can be read as a CSV"
    try:
        # dtype=str keeps everything as text, so "00123" does not become 123.
        # keep_default_na=False stops pandas turning the text "NA" into a missing value.
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return CheckResult(name, False, "The file is empty."), None
    except UnicodeDecodeError:
        return CheckResult(name, False, "The file is not a valid UTF-8 text file. Save it as CSV (UTF-8) and try again."), None
    except (pd.errors.ParserError, ValueError) as error:
        return CheckResult(name, False, f"The file could not be parsed as a CSV ({error})."), None

    if len(df) == 0:
        return CheckResult(name, False, "The file has column headings but no data rows."), None
    return CheckResult(name, True, f"Read {len(df)} data rows."), df


def _required_columns_check(df):
    """Check 2: are all five required columns present?"""
    name = "All required columns are present"
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return CheckResult(name, False, "Missing column(s): " + ", ".join(missing) + ".")
    return CheckResult(name, True, "All 5 required columns found.")


def _no_blanks_check(df):
    """Check 3: no required column may contain empty cells."""
    name = "No missing values"
    problems = []
    for column in REQUIRED_COLUMNS:
        blank = df[column].str.strip() == ""
        if blank.any():
            # +2 because row 1 of the file is the heading and Python counts from 0.
            rows = [int(i) + 2 for i in df.index[blank]]
            problems.append(f"'{column}' is empty in {_describe_rows(rows)}")
    if problems:
        return CheckResult(name, False, "; ".join(problems) + ".")
    return CheckResult(name, True, "Every required cell is filled in.")


def _allowed_values_check(df):
    """Check 4: consent_status must be Yes/No, record_status must be Active/Inactive."""
    name = "Consent and record status values are valid"
    problems = []
    rules = [
        ("consent_status", ALLOWED_CONSENT, "Yes or No"),
        ("record_status", ALLOWED_STATUS, "Active or Inactive"),
    ]
    for column, allowed, wording in rules:
        values = df[column].str.strip().str.lower()
        # Blank cells are already reported by check 3, so skip them here.
        bad = (~values.isin(allowed)) & (values != "")
        if bad.any():
            rows = [int(i) + 2 for i in df.index[bad]]
            problems.append(f"'{column}' must be {wording} (check {_describe_rows(rows)})")
    if problems:
        return CheckResult(name, False, "; ".join(problems) + ".")
    return CheckResult(name, True, "All consent_status and record_status values are valid.")


def _dates_and_periods_check(df):
    """Check 5: collection_date is a real past date; retention_period looks like '5 years'."""
    name = "Dates and retention periods are valid"
    problems = []

    # --- collection_date: must be YYYY-MM-DD and not in the future ---
    dates = pd.to_datetime(df["collection_date"].str.strip(), format="%Y-%m-%d", errors="coerce")
    not_blank = df["collection_date"].str.strip() != ""
    unreadable = dates.isna() & not_blank
    if unreadable.any():
        rows = [int(i) + 2 for i in df.index[unreadable]]
        problems.append(f"'collection_date' must look like 2024-03-31 (check {_describe_rows(rows)})")
    future = dates > pd.Timestamp.today().normalize()
    if future.any():
        rows = [int(i) + 2 for i in df.index[future]]
        problems.append(f"'collection_date' is in the future in {_describe_rows(rows)}")

    # --- retention_period: a whole number plus years/months/days ---
    periods = df["retention_period"].str.strip()
    matches = periods.apply(lambda text: bool(RETENTION_PATTERN.match(text)))
    bad_period = (~matches) & (periods != "")
    if bad_period.any():
        rows = [int(i) + 2 for i in df.index[bad_period]]
        problems.append(
            f"'retention_period' must look like '5 years', '6 months' or '90 days' (check {_describe_rows(rows)})"
        )

    if problems:
        return CheckResult(name, False, "; ".join(problems) + ".")
    return CheckResult(name, True, "All dates and retention periods are valid.")


def validate_dataset(path):
    """
    Run all five checks on the CSV at `path` and return a ValidationResult.
    If the file cannot even be read, the later checks are skipped.
    """
    result = ValidationResult()

    readable, df = _file_readable_check(path)
    result.checks.append(readable)
    if df is None:
        return result

    # Tolerate stray spaces and capital letters in the headings ("Consent_Status ").
    df.columns = [str(c).strip().lower() for c in df.columns]
    result.row_count = len(df)
    result.columns = list(df.columns)

    columns_check = _required_columns_check(df)
    result.checks.append(columns_check)
    if not columns_check.passed:
        # Without the columns, the remaining checks cannot run.
        return result

    result.checks.append(_no_blanks_check(df))
    result.checks.append(_allowed_values_check(df))
    result.checks.append(_dates_and_periods_check(df))
    return result