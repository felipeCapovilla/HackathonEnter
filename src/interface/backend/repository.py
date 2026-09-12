"""Persistence operations for the EnterAgree HTTP API."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .database import connection_for
from .schemas import (
    CaseCreate,
    DocumentRequestCreate,
    DocumentRequestStatus,
    DocumentType,
    DocumentTypeStatus,
    LawyerDecisionCreate,
    SourceParty,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


class Repository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def create_bank(self, name: str) -> dict:
        record = {"id": str(uuid4()), "name": name.strip(), "created_at": _now()}
        with connection_for(self.database_path) as connection:
            try:
                connection.execute("INSERT INTO banks (id, name, created_at) VALUES (:id, :name, :created_at)", record)
            except sqlite3.IntegrityError as exc:
                raise ValueError("Banco já cadastrado.") from exc
        return record

    def list_banks(self) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute("SELECT * FROM banks ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def get_bank(self, bank_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            return _row(connection.execute("SELECT * FROM banks WHERE id = ?", (bank_id,)).fetchone())

    def create_user(self, record: dict) -> dict:
        with connection_for(self.database_path) as connection:
            try:
                connection.execute("""INSERT INTO users (id, name, email, password_hash, role, bank_id, is_active, created_at)
                VALUES (:id, :name, :email, :password_hash, :role, :bank_id, :is_active, :created_at)""", record)
            except sqlite3.IntegrityError as exc:
                raise ValueError("E-mail já cadastrado ou banco inválido.") from exc
        return self.get_user(record["id"]) or record

    def get_user(self, user_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute("""SELECT users.id, users.name, users.email, users.password_hash, users.role,
            users.bank_id, users.is_active, users.created_at, banks.name AS bank_name FROM users
            LEFT JOIN banks ON banks.id = users.bank_id WHERE users.id = ?""", (user_id,)).fetchone()
        return _row(row)

    def get_user_by_email(self, email: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute("""SELECT users.id, users.name, users.email, users.password_hash, users.role,
            users.bank_id, users.is_active, users.created_at, banks.name AS bank_name FROM users
            LEFT JOIN banks ON banks.id = users.bank_id WHERE users.email = ?""", (email,)).fetchone()
        return _row(row)

    def list_users(self, bank_id: str | None = None) -> list[dict]:
        query = """SELECT users.id, users.name, users.email, users.role, users.bank_id, users.is_active, users.created_at,
        banks.name AS bank_name FROM users LEFT JOIN banks ON banks.id = users.bank_id"""
        parameters: tuple = () if bank_id is None else (bank_id,)
        if bank_id is not None:
            query += " WHERE users.bank_id = ?"
        query += " ORDER BY users.name"
        with connection_for(self.database_path) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def update_user(self, user_id: str, changes: dict) -> dict | None:
        if not changes:
            return self.get_user(user_id)
        columns = ", ".join(f"{key} = :{key}" for key in changes)
        with connection_for(self.database_path) as connection:
            connection.execute(f"UPDATE users SET {columns} WHERE id = :id", {"id": user_id, **changes})
            if "password_hash" in changes or changes.get("is_active") is False:
                connection.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (_now(), user_id))
        return self.get_user(user_id)

    def create_session(self, token_hash: str, user_id: str, csrf_token: str, expires_at: str) -> None:
        with connection_for(self.database_path) as connection:
            connection.execute("INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at) VALUES (?, ?, ?, ?)", (token_hash, user_id, csrf_token, expires_at))

    def get_session_user(self, token_hash: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute("""SELECT users.id, users.name, users.email, users.role, users.bank_id,
            users.is_active, users.created_at, banks.name AS bank_name, sessions.csrf_token FROM sessions
            JOIN users ON users.id = sessions.user_id LEFT JOIN banks ON banks.id = users.bank_id
            WHERE sessions.token_hash = ? AND sessions.revoked_at IS NULL AND sessions.expires_at > ? AND users.is_active = 1""",
            (token_hash, _now())).fetchone()
        return _row(row)

    def revoke_session(self, token_hash: str) -> None:
        with connection_for(self.database_path) as connection:
            connection.execute("UPDATE sessions SET revoked_at = ? WHERE token_hash = ?", (_now(), token_hash))

    def create_case(self, payload: CaseCreate, bank_id: str = "banco-unicamp", created_by_user_id: str | None = None) -> dict:
        case_id = str(uuid4())
        record = {
            "id": case_id,
            **payload.model_dump(),
            "uf": payload.uf.upper(),
            "bank_id": bank_id,
            "created_by_user_id": created_by_user_id,
            "assigned_lawyer_id": payload.assigned_lawyer_id,
            "created_at": _now(),
        }
        with connection_for(self.database_path) as connection:
            try:
                connection.execute(
                    """INSERT INTO cases (id, case_number, uf, value_of_claim, sub_subject, dossie_status, bank_id, assigned_lawyer_id, created_by_user_id, created_at)
                    VALUES (:id, :case_number, :uf, :value_of_claim, :sub_subject, :dossie_status, :bank_id, :assigned_lawyer_id, :created_by_user_id, :created_at)""",
                    record,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Número de processo já cadastrado.") from exc
        return record

    def get_case(self, case_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            return _row(connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone())

    def list_cases(self, bank_id: str | None = None, lawyer_id: str | None = None) -> list[dict]:
        where, parameters = "", []
        if bank_id is not None:
            where, parameters = " WHERE cases.bank_id = ?", [bank_id]
        if lawyer_id is not None:
            where += " AND" if where else " WHERE"
            where += " cases.assigned_lawyer_id = ?"
            parameters.append(lawyer_id)
        with connection_for(self.database_path) as connection:
            rows = connection.execute(f"SELECT * FROM cases{where} ORDER BY created_at DESC", parameters).fetchall()
        return [dict(row) for row in rows]

    def assign_lawyer(self, case_id: str, lawyer_id: str | None, bank_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            if lawyer_id:
                valid = connection.execute("SELECT 1 FROM users WHERE id = ? AND role = 'ADVOGADO_EXTERNO' AND bank_id = ? AND is_active = 1", (lawyer_id, bank_id)).fetchone()
                if valid is None:
                    raise ValueError("Advogado ativo do banco não encontrado.")
            cursor = connection.execute("UPDATE cases SET assigned_lawyer_id = ? WHERE id = ? AND bank_id = ?", (lawyer_id, case_id, bank_id))
            if cursor.rowcount != 1:
                return None
        return self.get_case(case_id)

    def create_document(
        self,
        *,
        case_id: str,
        original_filename: str,
        file_path: Path,
        declared_type: DocumentType,
        source_party: SourceParty,
        sha256: str,
        request_id: str | None,
    ) -> dict:
        document_id = str(uuid4())
        record = {
            "id": document_id,
            "case_id": case_id,
            "original_filename": original_filename,
            "file_path": str(file_path),
            "declared_type": declared_type.value,
            "detected_type": None,
            "type_status": DocumentTypeStatus.PENDING.value,
            "source_party": source_party.value,
            "status": "UPLOADED",
            "sha256": sha256,
            "request_id": request_id,
            "created_at": _now(),
        }
        with connection_for(self.database_path) as connection:
            if request_id:
                request = connection.execute(
                    "SELECT case_id, document_type, status FROM document_requests WHERE id = ?",
                    (request_id,),
                ).fetchone()
                if request is None:
                    raise ValueError("Solicitação documental não encontrada.")
                if request["case_id"] != case_id:
                    raise ValueError("A solicitação não pertence a este processo.")
                if request["document_type"] != declared_type.value:
                    raise ValueError("O tipo do documento não corresponde ao solicitado.")
                if source_party != SourceParty.BANCO:
                    raise ValueError("Apenas o banco pode atender uma solicitação documental.")
                if request["status"] != DocumentRequestStatus.REQUESTED.value:
                    raise ValueError("A solicitação documental já foi encerrada.")
            try:
                connection.execute(
                    """INSERT INTO documents (
                        id, case_id, original_filename, file_path, declared_type, detected_type,
                        type_status, source_party, status, sha256, request_id, created_at
                    ) VALUES (
                        :id, :case_id, :original_filename, :file_path, :declared_type, :detected_type,
                        :type_status, :source_party, :status, :sha256, :request_id, :created_at
                    )""",
                    record,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Este arquivo já foi enviado para o processo.") from exc
            if request_id:
                cursor = connection.execute(
                    """UPDATE document_requests SET status = ?, responded_at = ?
                    WHERE id = ? AND status = ?""",
                    (
                        DocumentRequestStatus.SUBMITTED.value,
                        _now(),
                        request_id,
                        DocumentRequestStatus.REQUESTED.value,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError("A solicitação documental já foi encerrada.")
        return self.get_document(document_id) or record

    def get_document(self, document_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return self._decode_document(_row(row))

    def get_document_internal(self, document_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return self._decode_document(_row(row), include_internal=True)

    def list_documents(self, case_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM documents WHERE case_id = ? ORDER BY created_at", (case_id,)
            ).fetchall()
        return [self._decode_document(dict(row)) for row in rows]

    def update_document_extraction(
        self,
        document_id: str,
        *,
        status: str,
        page_count: int,
        pages_extracted: int,
        quality_flags: list[str],
        detected_type: DocumentType | None,
        type_status: DocumentTypeStatus,
    ) -> None:
        with connection_for(self.database_path) as connection:
            connection.execute(
                """UPDATE documents SET status = ?, page_count = ?, pages_extracted = ?,
                quality_flags = ?, detected_type = ?, type_status = ? WHERE id = ?""",
                (
                    status,
                    page_count,
                    pages_extracted,
                    _json(quality_flags),
                    detected_type.value if detected_type else None,
                    type_status.value,
                    document_id,
                ),
            )

    def replace_document_pages(self, document_id: str, pages: list[dict]) -> None:
        with connection_for(self.database_path) as connection:
            connection.execute("DELETE FROM document_pages WHERE document_id = ?", (document_id,))
            connection.executemany(
                """INSERT INTO document_pages (
                    document_id, page_number, text_content, extraction_method, quality_flags
                ) VALUES (?, ?, ?, ?, ?)""",
                [
                    (
                        document_id,
                        page["page_number"],
                        page["text_content"],
                        page["extraction_method"],
                        _json(page["quality_flags"]),
                    )
                    for page in pages
                ],
            )

    def clear_document_pages(self, document_id: str) -> None:
        with connection_for(self.database_path) as connection:
            connection.execute("DELETE FROM document_pages WHERE document_id = ?", (document_id,))

    def append_document_pages(self, document_id: str, pages: list[dict]) -> None:
        if not pages:
            return
        with connection_for(self.database_path) as connection:
            connection.executemany(
                """INSERT OR REPLACE INTO document_pages (
                    document_id, page_number, text_content, extraction_method, quality_flags
                ) VALUES (?, ?, ?, ?, ?)""",
                [
                    (
                        document_id,
                        page["page_number"],
                        page["text_content"],
                        page["extraction_method"],
                        _json(page["quality_flags"]),
                    )
                    for page in pages
                ],
            )

    def get_document_text_sample(self, document_id: str, maximum_characters: int = 100_000) -> str:
        chunks: list[str] = []
        remaining = maximum_characters
        page_offset = 0
        page_batch_size = 100
        with connection_for(self.database_path) as connection:
            while remaining > 0:
                rows = connection.execute(
                    """SELECT text_content FROM document_pages WHERE document_id = ?
                    ORDER BY page_number LIMIT ? OFFSET ?""",
                    (document_id, page_batch_size, page_offset),
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    text = row["text_content"]
                    chunks.append(text[:remaining])
                    remaining -= len(text)
                    if remaining <= 0:
                        break
                page_offset += len(rows)
        return "\n".join(chunks)

    def get_page(self, document_id: str, page_number: int) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute(
                """SELECT page_number, text_content, extraction_method, quality_flags
                FROM document_pages WHERE document_id = ? AND page_number = ?""",
                (document_id, page_number),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["quality_flags"] = json.loads(record["quality_flags"])
        return record

    def iter_document_pages(self, document_id: str, batch_size: int = 32) -> Iterator[dict]:
        if batch_size < 1:
            raise ValueError("O tamanho do lote deve ser positivo.")
        last_page = 0
        while True:
            with connection_for(self.database_path) as connection:
                rows = connection.execute(
                    """SELECT page_number, text_content FROM document_pages
                    WHERE document_id = ? AND page_number > ? ORDER BY page_number LIMIT ?""",
                    (document_id, last_page, batch_size),
                ).fetchall()
            if not rows:
                return
            for row in rows:
                last_page = row["page_number"]
                yield dict(row)

    def get_cached_dossie_analysis(
        self, document_id: str, sha256: str, model: str, analyzer_version: str
    ) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute(
                """SELECT * FROM dossie_analyses WHERE document_id = ? AND sha256 = ?
                AND model = ? AND analyzer_version = ? AND status = 'COMPLETED'""",
                (document_id, sha256, model, analyzer_version),
            ).fetchone()
        return self._decode_dossie_analysis(_row(row))

    def claim_dossie_analysis(
        self, document: dict, model: str, analyzer_version: str, timeout_seconds: int
    ) -> str | None:
        token = str(uuid4())
        now = time.time()
        with connection_for(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM dossie_analysis_claims WHERE expires_at <= ?", (now,))
            cursor = connection.execute(
                """INSERT OR IGNORE INTO dossie_analysis_claims
                (document_id, sha256, model, analyzer_version, token, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (document["id"], document["sha256"], model, analyzer_version, token, now + timeout_seconds),
            )
        return token if cursor.rowcount == 1 else None

    def release_dossie_analysis(self, token: str) -> None:
        with connection_for(self.database_path) as connection:
            connection.execute("DELETE FROM dossie_analysis_claims WHERE token = ?", (token,))

    def create_dossie_analysis(
        self, *, document: dict, model: str, analyzer_version: str,
        result: dict | None = None, error_code: str | None = None,
    ) -> dict:
        record = {
            "id": str(uuid4()),
            "document_id": document["id"],
            "sha256": document["sha256"],
            "model": model,
            "analyzer_version": analyzer_version,
            "status": "FAILED" if error_code else "COMPLETED",
            "result": _json(result) if result is not None else None,
            "error_code": error_code,
            "created_at": _now(),
        }
        try:
            with connection_for(self.database_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if not error_code:
                    current = connection.execute(
                        """SELECT declared_type, type_status, status, sha256
                        FROM documents WHERE id = ?""", (document["id"],)
                    ).fetchone()
                    if current is None or any(
                        current[key] != document[key]
                        for key in ("declared_type", "type_status", "status", "sha256")
                    ):
                        raise ValueError("O documento mudou durante a análise; tente novamente.")
                connection.execute(
                    """INSERT INTO dossie_analyses
                    (id, document_id, sha256, model, analyzer_version, status, result, error_code, created_at)
                    VALUES (:id, :document_id, :sha256, :model, :analyzer_version,
                    :status, :result, :error_code, :created_at)""", record,
                )
        except sqlite3.IntegrityError:
            cached = self.get_cached_dossie_analysis(document["id"], document["sha256"], model, analyzer_version)
            if cached is not None:
                return cached
            raise
        return self._decode_dossie_analysis(record)

    def get_dossie_analysis(self, document_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute(
                """SELECT * FROM dossie_analyses WHERE document_id = ?
                ORDER BY CASE status WHEN 'COMPLETED' THEN 0 ELSE 1 END, created_at DESC, id DESC LIMIT 1""",
                (document_id,),
            ).fetchone()
        return self._decode_dossie_analysis(_row(row))

    def list_dossie_analyses(self, case_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                """SELECT analysis.* FROM dossie_analyses AS analysis
                JOIN documents AS document ON document.id = analysis.document_id
                WHERE document.case_id = ? AND document.type_status != 'REMOVED'
                ORDER BY CASE analysis.status WHEN 'COMPLETED' THEN 0 ELSE 1 END,
                analysis.created_at DESC""", (case_id,),
            ).fetchall()
        return [self._decode_dossie_analysis(dict(row)) for row in rows]

    def list_current_dossie_summaries(self, case_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                """WITH ranked AS (
                    SELECT analysis.*, ROW_NUMBER() OVER (
                        PARTITION BY analysis.document_id
                        ORDER BY CASE analysis.status WHEN 'COMPLETED' THEN 0 ELSE 1 END,
                        analysis.created_at DESC, analysis.id DESC
                    ) AS position
                    FROM dossie_analyses AS analysis
                    JOIN documents AS document ON document.id = analysis.document_id
                    WHERE document.case_id = ? AND document.type_status != 'REMOVED'
                )
                SELECT id, document_id, model, status, error_code, created_at,
                    json_set(result, '$.evidencias', json('[]')) AS result,
                    COALESCE(json_array_length(result, '$.evidencias'), 0) AS evidencias_total
                FROM ranked WHERE position = 1 ORDER BY created_at DESC""", (case_id,),
            ).fetchall()
        return [
            {**self._decode_dossie_analysis(dict(row)), "evidencias_carregadas": False}
            for row in rows
        ]

    def update_document_type(
        self,
        document_id: str,
        *,
        declared_type: DocumentType,
        detected_type: DocumentType | None,
        type_status: DocumentTypeStatus,
    ) -> None:
        with connection_for(self.database_path) as connection:
            connection.execute(
                """UPDATE documents SET declared_type = ?, detected_type = ?, type_status = ?
                WHERE id = ?""",
                (declared_type.value, detected_type.value if detected_type else None, type_status.value, document_id),
            )

    def create_analysis(self, record: dict) -> dict:
        with connection_for(self.database_path) as connection:
            connection.execute(
                """INSERT INTO analyses (
                    id, case_id, recommendation, decision_code, policy_source, agreement_probability,
                    documentary_status, reasons, feature_vector, feature_provenance, pricing, limitations,
                    policy_output, policy_version, contract_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["id"], record["case_id"], record["recommendation"], record["decision_code"],
                    record["policy_source"], record["agreement_probability"], record["documentary_status"],
                    _json(record["reasons"]), _json(record["feature_vector"]),
                    _json(record["feature_provenance"]),
                    _json(record["pricing"]) if record.get("pricing") is not None else None,
                    _json(record["limitations"]),
                    _json(record["policy_output"]) if record.get("policy_output") is not None else None,
                    record.get("policy_version"), record.get("contract_version"), record["created_at"],
                ),
            )
        return record

    def get_analysis(self, analysis_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        return self._decode_analysis(_row(row))

    def list_analyses(self, case_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM analyses WHERE case_id = ? ORDER BY created_at DESC", (case_id,)
            ).fetchall()
        return [self._decode_analysis(dict(row)) for row in rows]

    def create_document_request(self, case_id: str, payload: DocumentRequestCreate) -> dict:
        record = {
            "id": str(uuid4()),
            "case_id": case_id,
            **payload.model_dump(mode="json"),
            "due_date": None,
            "status": DocumentRequestStatus.REQUESTED.value,
            "created_at": _now(),
            "responded_at": None,
        }
        with connection_for(self.database_path) as connection:
            connection.execute(
                """INSERT INTO document_requests (
                    id, case_id, document_type, hypothesis_key, reason, due_date, status, created_at, responded_at
                ) VALUES (:id, :case_id, :document_type, :hypothesis_key, :reason, :due_date, :status, :created_at, :responded_at)""",
                record,
            )
        return record

    def get_document_request(self, request_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute("SELECT * FROM document_requests WHERE id = ?", (request_id,)).fetchone()
        return _row(row)

    def list_document_requests(self, case_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM document_requests WHERE case_id = ? ORDER BY created_at DESC", (case_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def respond_to_document_request(
        self, request_id: str, status: DocumentRequestStatus, reason: str
    ) -> dict | None:
        status_value = status.value if isinstance(status, DocumentRequestStatus) else str(status)
        with connection_for(self.database_path) as connection:
            cursor = connection.execute(
                """UPDATE document_requests SET status = ?, response_reason = ?, responded_at = ?
                WHERE id = ? AND status = ?""",
                (status_value, reason, _now(), request_id, DocumentRequestStatus.REQUESTED.value),
            )
            if cursor.rowcount == 0:
                exists = connection.execute(
                    "SELECT 1 FROM document_requests WHERE id = ?", (request_id,)
                ).fetchone()
                if exists is None:
                    return None
                raise ValueError("A solicitação documental já foi encerrada.")
        return self.get_document_request(request_id)

    def create_lawyer_decision(
        self, case_id: str, analysis_id: str, payload: LawyerDecisionCreate
    ) -> dict:
        record = {
            "id": str(uuid4()),
            "case_id": case_id,
            "analysis_id": analysis_id,
            **payload.model_dump(),
            "created_at": _now(),
        }
        with connection_for(self.database_path) as connection:
            connection.execute(
                """INSERT INTO lawyer_decisions (
                    id, case_id, analysis_id, action, reason, proposed_value, created_at
                ) VALUES (:id, :case_id, :analysis_id, :action, :reason, :proposed_value, :created_at)""",
                record,
            )
        return record

    def list_lawyer_decisions(self, case_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM lawyer_decisions WHERE case_id = ? ORDER BY created_at DESC", (case_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _decode_dossie_analysis(record: dict | None) -> dict | None:
        if record is None:
            return None
        record["result"] = json.loads(record["result"]) if record["result"] else None
        record.pop("sha256", None)
        record.pop("analyzer_version", None)
        return record

    @staticmethod
    def _decode_document(record: dict | None, *, include_internal: bool = False) -> dict | None:
        if record is None:
            return None
        record["quality_flags"] = json.loads(record["quality_flags"])
        if not include_internal:
            record.pop("file_path", None)
            record.pop("request_id", None)
        return record

    @staticmethod
    def _decode_analysis(record: dict | None) -> dict | None:
        if record is None:
            return None
        for key in ("reasons", "feature_vector", "feature_provenance", "limitations"):
            record[key] = json.loads(record[key])
        record["pricing"] = json.loads(record["pricing"]) if record.get("pricing") else None
        record["policy_output"] = json.loads(record["policy_output"]) if record.get("policy_output") else None
        return record
