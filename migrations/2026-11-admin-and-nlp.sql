-- Run ONCE against your existing database (dpa_compliance_db) to add what the administrator pages,
-- the policy comparison and the activity log need. Safe to run twice: every statement checks first.
--   psql -U postgres -d dpa_compliance_db -f migrations/2026-11-admin-and-nlp.sql

-- Users: profile columns (if you did not add them earlier) and the "deactivated" switch
ALTER TABLE users ADD COLUMN IF NOT EXISTS email          VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name      VARCHAR(150);
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone          VARCHAR(30);
ALTER TABLE users ADD COLUMN IF NOT EXISTS job_title      VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS department     VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_filename VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS active         BOOLEAN NOT NULL DEFAULT TRUE;

-- Rules: the working copy of the rules now lives in the database
ALTER TABLE compliance_rules ADD COLUMN IF NOT EXISTS violation_type VARCHAR(100);
ALTER TABLE compliance_rules ADD COLUMN IF NOT EXISTS severity       VARCHAR(20);
ALTER TABLE compliance_rules ADD COLUMN IF NOT EXISTS recommendation TEXT;
ALTER TABLE compliance_rules ADD COLUMN IF NOT EXISTS check_config   TEXT;
ALTER TABLE compliance_rules ADD COLUMN IF NOT EXISTS enabled        BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE compliance_rules ADD COLUMN IF NOT EXISTS origin         VARCHAR(20) NOT NULL DEFAULT 'knowledge_base';
ALTER TABLE compliance_rules ADD COLUMN IF NOT EXISTS created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- New tables
CREATE TABLE IF NOT EXISTS policy_findings (
    finding_id     SERIAL PRIMARY KEY,
    audit_id       INTEGER NOT NULL REFERENCES audit_runs(audit_id),
    policy_id      INTEGER NOT NULL REFERENCES policy_documents(document_id),
    category       VARCHAR(50) NOT NULL,
    rule_id        INTEGER REFERENCES compliance_rules(rule_id),
    verdict        VARCHAR(20) NOT NULL,
    similarity     NUMERIC(6, 4),
    best_statement TEXT
);

CREATE TABLE IF NOT EXISTS activity_log (
    log_id    SERIAL PRIMARY KEY,
    logged_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id   INTEGER REFERENCES users(user_id),
    username  VARCHAR(100),
    action    VARCHAR(40) NOT NULL,
    detail    VARCHAR(300)
);

CREATE TABLE IF NOT EXISTS candidate_reviews (
    candidate_code VARCHAR(30) PRIMARY KEY,
    decision       VARCHAR(10) NOT NULL,
    reviewed_by    INTEGER REFERENCES users(user_id),
    reviewed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;
