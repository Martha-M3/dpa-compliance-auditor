-- ============================================================
-- Automated DPA Compliance Auditing System
-- Database Schema 
-- ============================================================

CREATE TABLE users (
    user_id       SERIAL PRIMARY KEY,
    username      VARCHAR(100) UNIQUE NOT NULL,
    email         VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20) NOT NULL CHECK (role IN ('Administrator', 'ComplianceOfficer')),
    full_name      VARCHAR(150),
    phone          VARCHAR(30),
    job_title      VARCHAR(100),
    department     VARCHAR(100),
    photo_filename VARCHAR(255),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
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
    rule_code VARCHAR(30) NOT NULL UNIQUE,
    category        VARCHAR(50) NOT NULL CHECK (category IN ('consent', 'retention')),
    source_section  VARCHAR(100),
    violation_type  VARCHAR(100),
    severity        VARCHAR(20),
    recommendation  TEXT,
    check_config    TEXT,                       -- NULL = a policy obligation that is only compared with policies
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    origin          VARCHAR(20) NOT NULL DEFAULT 'knowledge_base',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

CREATE TABLE policy_findings (
    finding_id     SERIAL PRIMARY KEY,
    audit_id       INTEGER NOT NULL REFERENCES audit_runs(audit_id),
    policy_id      INTEGER NOT NULL REFERENCES policy_documents(document_id),
    category       VARCHAR(50) NOT NULL,
    rule_id        INTEGER REFERENCES compliance_rules(rule_id),
    verdict        VARCHAR(20) NOT NULL,
    similarity     NUMERIC(6, 4),
    best_statement TEXT
);

CREATE TABLE activity_log (
    log_id    SERIAL PRIMARY KEY,
    logged_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id   INTEGER REFERENCES users(user_id),
    username  VARCHAR(100),
    action    VARCHAR(40) NOT NULL,
    detail    VARCHAR(300)
);

CREATE TABLE candidate_reviews (
    candidate_code VARCHAR(30) PRIMARY KEY,
    decision       VARCHAR(10) NOT NULL,
    reviewed_by    INTEGER REFERENCES users(user_id),
    reviewed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;
