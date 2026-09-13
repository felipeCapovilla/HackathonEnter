"""Documento excluído pode ser enviado de novo; o mesmo arquivo vivo continua bloqueado."""
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from src.interface.backend.auth import hash_password
from src.interface.backend.config import Settings
from src.interface.backend.database import initialize_database
from src.interface.backend.main import create_app

SENHA = "senha-segura-com-15"
EXTRATO = b"Extrato bancario. Saldo. Lancamentos de conta. Credito do emprestimo."


def _app(tmp_path: Path):
    runtime = tmp_path / "runtime"
    return create_app(Settings(runtime, runtime / "app.db", runtime / "documents", Path("artefatos"), 1024 * 1024, auth_required=True))


def _upload(client, case_id, content=EXTRATO, name="extrato.txt"):
    return client.post(f"/api/cases/{case_id}/documents", data={"declared_type": "EXTRATO", "source_party": "BANCO"},
                       files={"file": (name, content, "text/plain")})


def _cliente_banco(app, client):
    app.state.repository.create_user({"id": "banco", "name": "Empresa", "email": "empresa@t.br", "password_hash": hash_password(SENHA),
                                      "role": "BANCO", "bank_id": "banco-unicamp", "is_active": True,
                                      "created_at": "2026-09-12T00:00:00+00:00"})
    assert client.post("/api/auth/login", json={"email": "empresa@t.br", "password": SENHA}).status_code == 200
    return client.post("/api/cases", json={"case_number": "reenvio-1", "uf": "SP", "value_of_claim": 1000}).json()["id"]


def test_documento_excluido_pode_ser_reenviado(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        case_id = _cliente_banco(app, client)
        primeiro = _upload(client, case_id)
        assert primeiro.status_code == 201
        assert _upload(client, case_id).status_code == 409, "o mesmo arquivo vivo continua bloqueado"
        assert client.delete(f"/api/cases/{case_id}/documents/{primeiro.json()['id']}").status_code == 204
        segundo = _upload(client, case_id)
        assert segundo.status_code == 201, segundo.text
        assert [d["id"] for d in client.get(f"/api/cases/{case_id}").json()["documents"]] == [segundo.json()["id"]]


def test_banco_antigo_com_trava_na_tabela_e_migrado(tmp_path):
    database = tmp_path / "antigo.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE cases (id TEXT PRIMARY KEY, case_number TEXT NOT NULL UNIQUE, uf TEXT NOT NULL,
                value_of_claim REAL, sub_subject TEXT, dossie_status TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE documents (id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                original_filename TEXT NOT NULL, file_path TEXT NOT NULL, declared_type TEXT NOT NULL, detected_type TEXT,
                type_status TEXT NOT NULL, source_party TEXT NOT NULL, status TEXT NOT NULL,
                page_count INTEGER NOT NULL DEFAULT 0, pages_extracted INTEGER NOT NULL DEFAULT 0, sha256 TEXT NOT NULL,
                quality_flags TEXT NOT NULL DEFAULT '[]', request_id TEXT, created_at TEXT NOT NULL, UNIQUE(case_id, sha256));
            INSERT INTO cases VALUES ('c1', 'p-1', 'SP', 1000, NULL, 'AUSENTE', '2026-01-01');
            INSERT INTO documents (id, case_id, original_filename, file_path, declared_type, type_status, source_party, status, sha256, created_at)
                VALUES ('d1', 'c1', 'a.txt', 'a.txt', 'EXTRATO', 'CONFIRMED', 'BANCO', 'COMPLETED', 'hash', '2026-01-01');
        """)
    initialize_database(database)
    with sqlite3.connect(database) as connection:
        sql = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'documents'").fetchone()[0]
        assert "UNIQUE" not in sql
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        connection.execute("UPDATE documents SET deleted_at = '2026-02-01' WHERE id = 'd1'")
        connection.execute("""INSERT INTO documents (id, case_id, original_filename, file_path, declared_type, type_status,
            source_party, status, sha256, created_at) VALUES ('d2', 'c1', 'a.txt', 'a.txt', 'EXTRATO', 'CONFIRMED', 'BANCO',
            'COMPLETED', 'hash', '2026-02-02')""")
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
