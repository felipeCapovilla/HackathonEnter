"""SQLite persistence for the API repository services."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    case_number TEXT NOT NULL UNIQUE,
    uf TEXT NOT NULL,
    value_of_claim REAL,
    sub_subject TEXT,
    dossie_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    original_filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    declared_type TEXT NOT NULL,
    detected_type TEXT,
    type_status TEXT NOT NULL,
    source_party TEXT NOT NULL,
    status TEXT NOT NULL,
    page_count INTEGER NOT NULL DEFAULT 0,
    pages_extracted INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL,
    quality_flags TEXT NOT NULL DEFAULT '[]',
    request_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(case_id, sha256)
);

CREATE TABLE IF NOT EXISTS document_pages (
    document_id TEXT NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    text_content TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    quality_flags TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY(document_id, page_number)
);

CREATE TABLE IF NOT EXISTS dossie_analyses (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    sha256 TEXT NOT NULL,
    model TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('COMPLETED', 'FAILED')),
    result TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dossie_analysis_claims (
    document_id TEXT NOT NULL REFERENCES documents(id),
    sha256 TEXT NOT NULL,
    model TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    token TEXT NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY(document_id, sha256, model, analyzer_version)
);

CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    recommendation TEXT NOT NULL,
    decision_code TEXT NOT NULL,
    policy_source TEXT NOT NULL,
    agreement_probability REAL,
    documentary_status TEXT NOT NULL,
    reasons TEXT NOT NULL,
    feature_vector TEXT NOT NULL,
    feature_provenance TEXT NOT NULL,
    pricing TEXT,
    limitations TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_requests (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    document_type TEXT NOT NULL,
    hypothesis_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    due_date TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    responded_at TEXT,
    response_reason TEXT
);

CREATE TABLE IF NOT EXISTS lawyer_decisions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    analysis_id TEXT NOT NULL REFERENCES analyses(id),
    action TEXT NOT NULL,
    reason TEXT,
    proposed_value REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS documents_case_idx ON documents(case_id);
CREATE INDEX IF NOT EXISTS document_pages_document_idx ON document_pages(document_id);
CREATE INDEX IF NOT EXISTS dossie_analyses_document_idx ON dossie_analyses(document_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS dossie_analysis_success_idx
ON dossie_analyses(document_id, sha256, model, analyzer_version) WHERE status = 'COMPLETED';
CREATE INDEX IF NOT EXISTS analyses_case_idx ON analyses(case_id, created_at);
CREATE INDEX IF NOT EXISTS requests_case_idx ON document_requests(case_id, status);
CREATE INDEX IF NOT EXISTS decisions_analysis_idx ON lawyer_decisions(analysis_id);
"""


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.executescript(SCHEMA)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(analyses)")}
        if "pricing" not in columns:
            connection.execute("ALTER TABLE analyses ADD COLUMN pricing TEXT")
        connection.execute(
            "UPDATE document_requests SET status = 'REQUESTED' WHERE status IN ('PENDING', 'OVERDUE')"
        )


@contextmanager
def connection_for(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()
