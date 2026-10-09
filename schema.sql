-- ============================================================
-- Automated DPA Compliance Auditing System
-- Database Schema 
-- ============================================================

CREATE TABLE users (
    user_id       SERIAL PRIMARY KEY,
    username      VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20) NOT NULL CHECK (role IN ('Administrator', 'ComplianceOfficer')),
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE policy_documents (
    document_id  SERIAL PRIMARY KEY,
    file_name    VARCHAR(255) NOT NULL,
    upload_date  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_text TEXT,
    uploaded_by  INTEGER NOT NULL REFERENCES users(user_id)
);

CREATE TABLE datasets (
    dataset_id       SERIAL PRIMARY KEY,
    file_name        VARCHAR(255) NOT NULL,
    upload_date      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    schema_validated BOOLEAN NOT NULL DEFAULT FALSE,
    uploaded_by      INTEGER NOT NULL REFERENCES users(user_id)
);

CREATE TABLE audit_runs (
    audit_id         SERIAL PRIMARY KEY,
    start_time       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time         TIMESTAMP,
    compliance_score NUMERIC(5, 2),
    dataset_id       INTEGER NOT NULL REFERENCES datasets(dataset_id),
    run_by           INTEGER NOT NULL REFERENCES users(user_id)
);

CREATE TABLE compliance_rules (
    rule_id         SERIAL PRIMARY KEY,
    obligation_text TEXT NOT NULL,
    category        VARCHAR(50) NOT NULL CHECK (category IN ('consent', 'retention')),
    source_section  VARCHAR(100)
);

CREATE TABLE audit_results (
    result_id      SERIAL PRIMARY KEY,
    record_id      VARCHAR(100) NOT NULL,
    violation_type VARCHAR(100) NOT NULL,
    severity       VARCHAR(20) NOT NULL,
    description    TEXT,
    audit_id       INTEGER NOT NULL REFERENCES audit_runs(audit_id),
    rule_id        INTEGER NOT NULL REFERENCES compliance_rules(rule_id)
);

CREATE TABLE compliance_reports (
    report_id      SERIAL PRIMARY KEY,
    generated_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    file_path      VARCHAR(255),
    audit_id       INTEGER NOT NULL UNIQUE REFERENCES audit_runs(audit_id)
);

SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;