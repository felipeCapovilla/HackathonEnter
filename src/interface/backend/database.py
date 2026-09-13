"""SQLite persistence for the API repository services."""

from __future__ import annotations

import re
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

CREATE TABLE IF NOT EXISTS banks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('BANCO', 'ADVOGADO_EXTERNO', 'ADMIN_GLOBAL')),
    bank_id TEXT REFERENCES banks(id),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    CHECK((role = 'ADMIN_GLOBAL' AND bank_id IS NULL) OR (role != 'ADMIN_GLOBAL' AND bank_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    csrf_token TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
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
    created_at TEXT NOT NULL
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
    policy_output TEXT,
    policy_version TEXT,
    contract_version TEXT,
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

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    actor_user_id TEXT REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    case_id TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_contracts (
    id TEXT PRIMARY KEY,
    bank_id TEXT NOT NULL REFERENCES banks(id),
    version INTEGER NOT NULL,
    parameters TEXT NOT NULL,
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(bank_id, version)
);

CREATE TABLE IF NOT EXISTS law_firms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS negotiation_outcomes (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    decision_id TEXT REFERENCES lawyer_decisions(id),
    lawyer_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('ACEITO', 'RECUSADO', 'CONTRAPROPOSTA', 'SEM_RESPOSTA')),
    offered_value REAL,
    counter_value REAL,
    closed_value REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS judicial_outcomes (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    lawyer_id TEXT,
    result TEXT NOT NULL CHECK(result IN ('EXITO', 'NAO_EXITO')),
    condemnation_value REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engagement_events (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'CASE_OPENED', 'DOCUMENT_OPENED', 'ANALYSIS_RUN', 'DECISION_REGISTERED', 'OUTCOME_REGISTERED', 'ACTIVE_TIME'
    )),
    document_id TEXT,
    active_seconds INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS divergence_balances (
    decision_id TEXT PRIMARY KEY REFERENCES lawyer_decisions(id),
    case_id TEXT NOT NULL REFERENCES cases(id),
    recommended_action TEXT NOT NULL,
    chosen_action TEXT NOT NULL,
    divergence_reason TEXT,
    recommended_path_cost REAL NOT NULL,
    real_cost REAL NOT NULL,
    balance REAL NOT NULL,
    computed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_ai_readings (
    document_id TEXT PRIMARY KEY REFERENCES documents(id),
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('COMPLETED', 'FAILED')),
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    sha256 TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    text_content TEXT NOT NULL,
    token_estimate INTEGER NOT NULL,
    embedding_model TEXT,
    embedding_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(document_id, sha256, chunk_index)
);

CREATE TABLE IF NOT EXISTS document_chat_conversations (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    -- "system" is used by the authentication-disabled test/demo mode.
    created_by_user_id TEXT NOT NULL,
    document_filter TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chat_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES document_chat_conversations(id),
    role TEXT NOT NULL CHECK(role IN ('USER', 'ASSISTANT')),
    content TEXT NOT NULL,
    citations TEXT NOT NULL DEFAULT '[]',
    retrieval_mode TEXT,
    model TEXT,
    prompt_version TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chat_retrievals (
    message_id TEXT NOT NULL REFERENCES document_chat_messages(id),
    -- Keep the historical chunk id even after its source is erased.
    chunk_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    score REAL NOT NULL,
    PRIMARY KEY(message_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS documents_case_idx ON documents(case_id);
CREATE INDEX IF NOT EXISTS document_pages_document_idx ON document_pages(document_id);
CREATE INDEX IF NOT EXISTS dossie_analyses_document_idx ON dossie_analyses(document_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS dossie_analysis_success_idx
ON dossie_analyses(document_id, sha256, model, analyzer_version) WHERE status = 'COMPLETED';
CREATE INDEX IF NOT EXISTS analyses_case_idx ON analyses(case_id, created_at);
CREATE INDEX IF NOT EXISTS requests_case_idx ON document_requests(case_id, status);
CREATE INDEX IF NOT EXISTS decisions_analysis_idx ON lawyer_decisions(analysis_id);
CREATE INDEX IF NOT EXISTS users_bank_idx ON users(bank_id, role, is_active);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions(user_id, expires_at);
CREATE INDEX IF NOT EXISTS bank_contracts_bank_idx ON bank_contracts(bank_id, version);
CREATE INDEX IF NOT EXISTS negotiation_case_idx ON negotiation_outcomes(case_id, created_at);
CREATE INDEX IF NOT EXISTS judicial_case_idx ON judicial_outcomes(case_id, created_at);
CREATE INDEX IF NOT EXISTS engagement_case_idx ON engagement_events(case_id, user_id, event_type);
CREATE INDEX IF NOT EXISTS document_chunks_document_idx ON document_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS chat_conversations_case_idx ON document_chat_conversations(case_id, created_at);
CREATE INDEX IF NOT EXISTS chat_messages_conversation_idx ON document_chat_messages(conversation_id, created_at);
"""

# Colunas adicionadas depois da primeira versão do schema: (tabela, coluna, definição).
MIGRATED_COLUMNS = (
    ("users", "law_firm_id", "TEXT REFERENCES law_firms(id)"),
    ("users", "is_manager", "INTEGER NOT NULL DEFAULT 0"),
    ("bank_contracts", "law_firm_id", "TEXT REFERENCES law_firms(id)"),
    ("bank_contracts", "justification", "TEXT"),
    ("document_requests", "unavailability_reason", "TEXT"),
    ("document_requests", "unavailability_reason_source", "TEXT"),
    ("cases", "is_simulated", "INTEGER NOT NULL DEFAULT 0"),
    ("lawyer_decisions", "lawyer_id", "TEXT"),
    ("lawyer_decisions", "divergence_reason", "TEXT"),
    ("lawyer_decisions", "requested_document", "TEXT"),
    ("negotiation_outcomes", "divergence_reason", "TEXT"),
    ("negotiation_outcomes", "reason", "TEXT"),
)


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.executescript(SCHEMA)
        case_columns = {row[1] for row in connection.execute("PRAGMA table_info(cases)")}
        for name, definition in (("bank_id", "TEXT"), ("assigned_lawyer_id", "TEXT"), ("created_by_user_id", "TEXT")):
            if name not in case_columns:
                connection.execute(f"ALTER TABLE cases ADD COLUMN {name} {definition}")
        document_columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
        # deleted_at: exclusão lógica. O documento some da tela e deixa de alimentar
        # a política, mas a linha fica — análises passadas guardam o id dele em
        # feature_provenance, e sem a linha não há como reproduzir por que uma
        # recomendação saiu daquele jeito naquele dia.
        for name in ("uploaded_by_user_id", "deleted_at", "deleted_by_user_id"):
            if name not in document_columns:
                connection.execute(f"ALTER TABLE documents ADD COLUMN {name} TEXT")
        chunk_columns = {row[1] for row in connection.execute("PRAGMA table_info(document_chunks)")}
        for name, definition in (("embedding_model", "TEXT"), ("embedding_json", "TEXT")):
            if name not in chunk_columns:
                connection.execute(f"ALTER TABLE document_chunks ADD COLUMN {name} {definition}")
        decision_columns = {row[1] for row in connection.execute("PRAGMA table_info(lawyer_decisions)")}
        for name in ("outcome", "outcome_at", "outcome_note"):
            if name not in decision_columns:
                connection.execute(f"ALTER TABLE lawyer_decisions ADD COLUMN {name} TEXT")
        connection.execute("INSERT OR IGNORE INTO banks (id, name, created_at) VALUES ('banco-unicamp', 'Banco Unicamp', '1970-01-01T00:00:00+00:00')")
        connection.execute("UPDATE cases SET bank_id = 'banco-unicamp' WHERE bank_id IS NULL")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(analyses)")}
        for name in ("pricing", "policy_output", "policy_version", "contract_version"):
            if name not in columns:
                connection.execute(f"ALTER TABLE analyses ADD COLUMN {name} TEXT")
        connection.execute(
            "UPDATE document_requests SET status = 'REQUESTED' WHERE status IN ('PENDING', 'OVERDUE')"
        )
        for table, name, definition in MIGRATED_COLUMNS:
            if name not in {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        _documento_unico_so_entre_vivos(connection)
        connection.execute("CREATE INDEX IF NOT EXISTS cases_bank_lawyer_idx ON cases(bank_id, assigned_lawyer_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS users_firm_idx ON users(law_firm_id)")


def _documento_unico_so_entre_vivos(connection: sqlite3.Connection) -> None:
    """
    O mesmo arquivo não entra duas vezes no processo, mas pode voltar depois de excluído.

    A primeira versão travava (case_id, sha256) na própria tabela, e a exclusão lógica
    mantém a linha: reenviar o documento apagado dava 409. A trava vira um índice
    parcial que só olha documentos vivos. SQLite não remove constraint de tabela,
    então bancos antigos são reconstruídos uma vez (com foreign keys desligadas,
    como manda a documentação do SQLite).
    """
    sql = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'documents'").fetchone()[0]
    if re.search(r"UNIQUE\s*\(\s*case_id\s*,\s*sha256\s*\)", sql):
        colunas = ", ".join(row[1] for row in connection.execute("PRAGMA table_info(documents)"))
        novo = re.sub(r",\s*UNIQUE\s*\(\s*case_id\s*,\s*sha256\s*\)", "", sql)
        novo = re.sub(r"^CREATE TABLE\s+(IF NOT EXISTS\s+)?\"?documents\"?", "CREATE TABLE documents_novo", novo)
        connection.commit()
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.executescript(f"""
                BEGIN;
                {novo};
                INSERT INTO documents_novo ({colunas}) SELECT {colunas} FROM documents;
                DROP TABLE documents;
                ALTER TABLE documents_novo RENAME TO documents;
                CREATE INDEX IF NOT EXISTS documents_case_idx ON documents(case_id);
                COMMIT;
            """)
        finally:
            connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS documents_case_sha_vivos_idx ON documents(case_id, sha256) WHERE deleted_at IS NULL")


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
