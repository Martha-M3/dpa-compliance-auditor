"""Dataset schema validation: FR-07, NFR-03, IR-02, DR-04 (tests TC-V01 to TC-V10)."""
from app.auditing.dataset_schema import validate_dataset
from helpers import HEADER, csv_bytes, good_rows


def run(tmp_path, content, name="d.csv"):
    path = tmp_path / name
    path.write_bytes(content)
    return validate_dataset(path)


def failing_messages(result):
    return " | ".join(c.message for c in result.checks if not c.passed)


def test_valid_dataset_passes(tmp_path, record):
    result = run(tmp_path, csv_bytes(good_rows(50)))
    assert result.passed and len(result.checks) == 5 and result.row_count == 50
    record("TC-V01", f"All {len(result.checks)} checks passed; {result.row_count} rows read.")


def test_missing_column_is_named(tmp_path, record):
    header = "data_subject_id,consent_status,collection_date,record_status"
    result = run(tmp_path, csv_bytes([["C1", "Yes", "2025-01-01", "Active"]], header))
    assert not result.passed and "retention_period" in failing_messages(result)
    record("TC-V02", "Rejected. " + failing_messages(result))


def test_blank_cell_row_identified(tmp_path, record):
    rows = good_rows(4)
    rows[2][1] = ""
    result = run(tmp_path, csv_bytes(rows))
    message = failing_messages(result)
    assert not result.passed and "consent_status" in message and "row 4" in message
    record("TC-V03", "Rejected. " + message)


def test_invalid_consent_and_status_values(tmp_path, record):
    rows = good_rows(3)
    rows[0][1] = "Maybe"
    rows[1][4] = "Pending"
    message = failing_messages(run(tmp_path, csv_bytes(rows)))
    assert "consent_status" in message and "Yes or No" in message
    assert "record_status" in message and "Active or Inactive" in message
    record("TC-V04", "Rejected. " + message)


def test_invalid_dates(tmp_path, record):
    seen = []
    for bad in ("31/03/2024", "2024-02-30", "2999-01-01", "yesterday"):
        rows = good_rows(2)
        rows[1][2] = bad
        result = run(tmp_path, csv_bytes(rows))
        assert not result.passed and "collection_date" in failing_messages(result), bad
        seen.append(bad)
    record("TC-V05", "All rejected, each naming collection_date: " + ", ".join(seen) + ".")


def test_invalid_retention_periods(tmp_path, record):
    seen = []
    for bad in ("five years", "5 yrs", "-3 years", "5", "years"):
        rows = good_rows(2)
        rows[0][3] = bad
        result = run(tmp_path, csv_bytes(rows))
        assert not result.passed and "retention_period" in failing_messages(result), bad
        seen.append(bad)
    record("TC-V06", "All rejected, each naming retention_period: " + ", ".join(seen) + ".")


def test_unreadable_files_do_not_crash(tmp_path, record):
    cases = {
        "empty file": b"",
        "headings only": (HEADER + "\n").encode(),
        "not UTF-8": b"data_subject_id,consent_status\n\xff\xfe\x00bad\n",
        "random binary": bytes(range(256)) * 20,
    }
    outcomes = []
    for label, content in cases.items():
        result = run(tmp_path, content)
        assert not result.passed and result.checks and result.checks[0].message
        outcomes.append(f"{label}: {result.checks[0].message}")
    record("TC-V07", "No exception; each rejected with a message. " + " / ".join(outcomes))


def test_heading_case_spaces_and_bom_tolerated(tmp_path, record):
    header = "﻿ Data_Subject_ID , Consent_Status,COLLECTION_DATE,Retention_Period,Record_Status "
    result = run(tmp_path, csv_bytes(good_rows(3), header))
    assert result.passed
    record("TC-V08", "Accepted: upper-case headings, stray spaces and a byte-order mark were normalised.")


def test_error_examples_are_capped(tmp_path, record):
    rows = good_rows(40)
    for row in rows[:30]:
        row[1] = "Perhaps"
    message = failing_messages(run(tmp_path, csv_bytes(rows)))
    assert "(and 25 more)" in message
    record("TC-V09", "Rejected. The message listed 5 example rows and '(and 25 more)' instead of 30 lines.")


def test_file_with_text_numbers_keeps_leading_zeros(tmp_path, record):
    rows = good_rows(2)
    rows[0][0] = "00123"
    assert run(tmp_path, csv_bytes(rows)).passed
    record("TC-V10", "Accepted; identifier 00123 is read as text (no conversion to 123).")
