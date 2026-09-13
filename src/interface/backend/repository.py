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
from .fluxo import calcular_fase
from .schemas import (
    CaseCreate,
    DocumentRequestCreate,
    DocumentRequestStatus,
    DocumentType,
    DocumentTypeStatus,
    JudicialOutcomeCreate,
    LawyerDecisionCreate,
    NegotiationOutcomeCreate,
    SourceParty,
)

USER_COLUMNS = """users.id, users.name, users.email, users.role, users.bank_id, users.is_active, users.created_at,
users.law_firm_id, users.is_manager, banks.name AS bank_name, law_firms.name AS law_firm_name"""
USER_JOINS = "LEFT JOIN banks ON banks.id = users.bank_id LEFT JOIN law_firms ON law_firms.id = users.law_firm_id"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _trecho(texto: str, termo: str, margem: int = 70) -> str:
    """Pedaço do texto em volta do termo encontrado, numa linha só."""
    plano = " ".join(texto.split())
    posicao = plano.casefold().find(termo.casefold())
    if posicao < 0:
        return plano[: margem * 2]
    inicio, fim = max(0, posicao - margem), min(len(plano), posicao + len(termo) + margem)
    return ("…" if inicio else "") + plano[inicio:fim] + ("…" if fim < len(plano) else "")


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

    def create_law_firm(self, name: str) -> dict:
        record = {"id": str(uuid4()), "name": name.strip(), "created_at": _now()}
        with connection_for(self.database_path) as connection:
            try:
                connection.execute("INSERT INTO law_firms (id, name, created_at) VALUES (:id, :name, :created_at)", record)
            except sqlite3.IntegrityError as exc:
                raise ValueError("Escritório já cadastrado.") from exc
        return record

    def list_law_firms(self, bank_id: str | None = None) -> list[dict]:
        """Sem banco: todos. Com banco: só os escritórios com advogado ativo naquele banco."""
        with connection_for(self.database_path) as connection:
            if bank_id is None:
                rows = connection.execute("SELECT * FROM law_firms ORDER BY name").fetchall()
            else:
                rows = connection.execute(
                    """SELECT DISTINCT law_firms.* FROM law_firms JOIN users ON users.law_firm_id = law_firms.id
                    WHERE users.bank_id = ? AND users.role = 'ADVOGADO_EXTERNO' AND users.is_active = 1
                    ORDER BY law_firms.name""", (bank_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_law_firm(self, law_firm_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            return _row(connection.execute("SELECT * FROM law_firms WHERE id = ?", (law_firm_id,)).fetchone())

    def create_bank_contract(self, bank_id: str, parameters: dict, created_by_user_id: str | None,
                             law_firm_id: str | None = None, justification: str | None = None) -> dict:
        """Grava uma NOVA versão do contrato do banco (ou do banco com um escritório).

        A numeração é única por banco, mesmo entre escritórios: `banco-v7` identifica
        uma versão sem ambiguidade. Versões anteriores ficam para auditoria.
        """
        with connection_for(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM bank_contracts WHERE bank_id = ?", (bank_id,)
            ).fetchone()[0]
            record = {
                "id": str(uuid4()), "bank_id": bank_id, "version": int(current) + 1,
                "parameters": _json(parameters), "created_by_user_id": created_by_user_id, "created_at": _now(),
                "law_firm_id": law_firm_id, "justification": justification,
            }
            connection.execute(
                """INSERT INTO bank_contracts (id, bank_id, version, parameters, created_by_user_id, created_at, law_firm_id, justification)
                VALUES (:id, :bank_id, :version, :parameters, :created_by_user_id, :created_at, :law_firm_id, :justification)""", record)
        return {**record, "parameters": parameters}

    def get_active_bank_contract(self, bank_id: str, law_firm_id: str | None = None) -> dict | None:
        """Última versão exatamente deste escopo: banco (law_firm_id None) ou banco com escritório."""
        with connection_for(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM bank_contracts WHERE bank_id = ? AND law_firm_id IS ? ORDER BY version DESC LIMIT 1",
                (bank_id, law_firm_id),
            ).fetchone()
        record = _row(row)
        if record is not None:
            record["parameters"] = json.loads(record["parameters"])
        return record

    def resolve_bank_contract(self, bank_id: str, law_firm_id: str | None) -> dict | None:
        """Contrato que vale para o caso: o do escritório, se houver; senão o padrão do banco."""
        if law_firm_id:
            record = self.get_active_bank_contract(bank_id, law_firm_id)
            if record is not None:
                return record
        return self.get_active_bank_contract(bank_id)

    def create_user(self, record: dict) -> dict:
        record = {"law_firm_id": None, "is_manager": False, **record}
        with connection_for(self.database_path) as connection:
            try:
                connection.execute("""INSERT INTO users (id, name, email, password_hash, role, bank_id, is_active, created_at, law_firm_id, is_manager)
                VALUES (:id, :name, :email, :password_hash, :role, :bank_id, :is_active, :created_at, :law_firm_id, :is_manager)""", record)
            except sqlite3.IntegrityError as exc:
                raise ValueError("E-mail já cadastrado ou banco inválido.") from exc
        return self.get_user(record["id"]) or record

    def get_user(self, user_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute(f"""SELECT {USER_COLUMNS}, users.password_hash FROM users
            {USER_JOINS} WHERE users.id = ?""", (user_id,)).fetchone()
        return _row(row)

    def get_user_by_email(self, email: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute(f"""SELECT {USER_COLUMNS}, users.password_hash FROM users
            {USER_JOINS} WHERE users.email = ?""", (email,)).fetchone()
        return _row(row)

    def list_users(self, bank_id: str | None = None) -> list[dict]:
        query = f"SELECT {USER_COLUMNS} FROM users {USER_JOINS}"
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
            row = connection.execute(f"""SELECT {USER_COLUMNS}, sessions.csrf_token FROM sessions
            JOIN users ON users.id = sessions.user_id {USER_JOINS}
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
        # `outcome`/`decided` vêm da última decisão do advogado e são o que separa
        # processo ativo de encerrado — não existe coluna de status em `cases`.
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                f"""SELECT cases.*,
                       (SELECT decision.outcome FROM lawyer_decisions AS decision
                         WHERE decision.case_id = cases.id AND decision.outcome IS NOT NULL
                         ORDER BY decision.outcome_at DESC LIMIT 1) AS outcome,
                       EXISTS(SELECT 1 FROM lawyer_decisions AS decision
                               WHERE decision.case_id = cases.id) AS decided,
                       (SELECT COUNT(*) FROM documents
                         WHERE documents.case_id = cases.id AND documents.deleted_at IS NULL) AS document_count,
                       (SELECT judicial.condemnation_value FROM judicial_outcomes AS judicial
                         WHERE judicial.case_id = cases.id ORDER BY judicial.created_at DESC LIMIT 1) AS condemnation_value
                   FROM cases{where} ORDER BY cases.created_at DESC""",
                parameters,
            ).fetchall()
        return [{**dict(row), "decided": bool(row["decided"]), "active": row["outcome"] is None} for row in rows]

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
        """Leitura pública: documento excluído logicamente não existe mais."""
        with connection_for(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ? AND deleted_at IS NULL", (document_id,)
            ).fetchone()
        return self._decode_document(_row(row))

    def get_document_internal(self, document_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return self._decode_document(_row(row), include_internal=True)

    def list_documents(self, case_id: str) -> list[dict]:
        """Documentos vivos do processo. Excluídos logicamente não voltam."""
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM documents WHERE case_id = ? AND deleted_at IS NULL ORDER BY created_at",
                (case_id,),
            ).fetchall()
        return [self._decode_document(dict(row)) for row in rows]

    def soft_delete_document(self, document_id: str, user_id: str) -> str | None:
        """
        Marca o documento como removido e devolve o caminho do arquivo em disco.

        A linha permanece: análises já emitidas referenciam este id em
        `feature_provenance`, e apagá-la quebraria a reprodução da recomendação.
        Quem apaga o arquivo é o chamador — o disco não faz parte da transação.
        """
        with connection_for(self.database_path) as connection:
            row = connection.execute(
                "SELECT file_path FROM documents WHERE id = ? AND deleted_at IS NULL", (document_id,)
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE documents SET deleted_at = ?, deleted_by_user_id = ? WHERE id = ?",
                (_now(), user_id, document_id),
            )
            # The audit retains chunk identifiers in chat retrievals, but not source text after deletion.
            connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        return row["file_path"]

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
        self, request_id: str, status: DocumentRequestStatus, reason: str,
        unavailability_reason: str | None = None, unavailability_reason_source: str | None = None,
    ) -> dict | None:
        status_value = status.value if isinstance(status, DocumentRequestStatus) else str(status)
        with connection_for(self.database_path) as connection:
            cursor = connection.execute(
                """UPDATE document_requests SET status = ?, response_reason = ?, responded_at = ?,
                unavailability_reason = ?, unavailability_reason_source = ?
                WHERE id = ? AND status = ?""",
                (status_value, reason, _now(), unavailability_reason, unavailability_reason_source,
                 request_id, DocumentRequestStatus.REQUESTED.value),
            )
            if cursor.rowcount == 0:
                exists = connection.execute(
                    "SELECT 1 FROM document_requests WHERE id = ?", (request_id,)
                ).fetchone()
                if exists is None:
                    return None
                raise ValueError("A solicitação documental já foi encerrada.")
        return self.get_document_request(request_id)

    def case_stage(self, case_id: str) -> str:
        """
        Em que ponto do ciclo o processo está. Três estados, não dois.

        ABERTO      sem decisão — tudo liberado
        DECIDIDO    com decisão, sem desfecho — negociação correndo
        ENCERRADO   com desfecho — nada mais se altera

        Quem consulta isto são os guardas de escrita: depois de encerrado, mexer
        em documento, responsável ou decisão reescreveria a história de um caso
        que já acabou, e as análises emitidas deixariam de bater com a prova.
        """
        with connection_for(self.database_path) as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS total,
                          COUNT(outcome) AS com_desfecho
                   FROM lawyer_decisions WHERE case_id = ?""",
                (case_id,),
            ).fetchone()
        if row["com_desfecho"]:
            return "ENCERRADO"
        return "DECIDIDO" if row["total"] else "ABERTO"

    def create_lawyer_decision(
        self, case_id: str, analysis_id: str, payload: LawyerDecisionCreate, lawyer_id: str | None = None
    ) -> dict:
        record = {
            "id": str(uuid4()),
            "case_id": case_id,
            "analysis_id": analysis_id,
            **payload.model_dump(),
            "lawyer_id": lawyer_id,
            "created_at": _now(),
        }
        with connection_for(self.database_path) as connection:
            connection.execute(
                """INSERT INTO lawyer_decisions (
                    id, case_id, analysis_id, action, reason, proposed_value, created_at, lawyer_id,
                    divergence_reason, requested_document
                ) VALUES (:id, :case_id, :analysis_id, :action, :reason, :proposed_value, :created_at, :lawyer_id,
                    :divergence_reason, :requested_document)""",
                record,
            )
        return record

    def create_negotiation_outcome(self, case_id: str, payload: NegotiationOutcomeCreate,
                                   lawyer_id: str | None) -> dict:
        """Liga o resultado à última decisão de ACORDO do processo."""
        with connection_for(self.database_path) as connection:
            decision = connection.execute(
                """SELECT id FROM lawyer_decisions WHERE case_id = ? AND action = 'ACORDO'
                ORDER BY created_at DESC LIMIT 1""", (case_id,)).fetchone()
            if decision is None:
                raise ValueError("Registre a decisão de propor acordo antes do resultado da negociação.")
            record = {"id": str(uuid4()), "case_id": case_id, "decision_id": decision["id"], "lawyer_id": lawyer_id,
                      **payload.model_dump(mode="json"), "created_at": _now()}
            connection.execute(
                """INSERT INTO negotiation_outcomes (id, case_id, decision_id, lawyer_id, status, offered_value,
                counter_value, closed_value, created_at, divergence_reason, reason) VALUES (:id, :case_id, :decision_id,
                :lawyer_id, :status, :offered_value, :counter_value, :closed_value, :created_at, :divergence_reason, :reason)""", record)
            if record["status"] == "ACEITO":
                # Acordo aceito é desfecho: encerra o processo no ciclo de vida da decisão.
                self._close_decision(connection, decision["id"], "ACORDO_ACEITO", record["created_at"])
        return record

    @staticmethod
    def _close_decision(connection: sqlite3.Connection, decision_id: str, outcome: str, when: str) -> None:
        connection.execute(
            "UPDATE lawyer_decisions SET outcome = ?, outcome_at = ? WHERE id = ? AND outcome IS NULL",
            (outcome, when, decision_id))

    def list_negotiation_outcomes(self, case_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM negotiation_outcomes WHERE case_id = ? ORDER BY created_at DESC", (case_id,)).fetchall()
        return [dict(row) for row in rows]

    def create_judicial_outcome(self, case_id: str, payload: JudicialOutcomeCreate, lawyer_id: str | None) -> dict:
        record = {"id": str(uuid4()), "case_id": case_id, "lawyer_id": lawyer_id,
                  **payload.model_dump(mode="json"), "created_at": _now()}
        with connection_for(self.database_path) as connection:
            connection.execute(
                """INSERT INTO judicial_outcomes (id, case_id, lawyer_id, result, condemnation_value, created_at)
                VALUES (:id, :case_id, :lawyer_id, :result, :condemnation_value, :created_at)""", record)
            decision = connection.execute(
                "SELECT id FROM lawyer_decisions WHERE case_id = ? ORDER BY created_at DESC LIMIT 1", (case_id,)).fetchone()
            if decision is not None:
                outcome = "SENTENCA_FAVORAVEL" if record["result"] == "EXITO" else "SENTENCA_DESFAVORAVEL"
                self._close_decision(connection, decision["id"], outcome, record["created_at"])
        return record

    def list_judicial_outcomes(self, case_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM judicial_outcomes WHERE case_id = ? ORDER BY created_at DESC", (case_id,)).fetchall()
        return [dict(row) for row in rows]

    def record_engagement(self, case_id: str, user_id: str, event_type: str,
                          document_id: str | None = None, active_seconds: int = 0) -> None:
        with connection_for(self.database_path) as connection:
            connection.execute(
                """INSERT INTO engagement_events (id, case_id, user_id, event_type, document_id, active_seconds, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), case_id, user_id, event_type, document_id, int(active_seconds), _now()))

    def list_lawyer_decisions(self, case_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM lawyer_decisions WHERE case_id = ? ORDER BY created_at DESC", (case_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_decision(self, decision_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM lawyer_decisions WHERE id = ?", (decision_id,)
            ).fetchone()
        return _row(row)

    def register_outcome(self, decision_id: str, outcome: str, note: str | None) -> dict | None:
        """Registra como o processo terminou. Só a primeira vez — desfecho não se reescreve."""
        with connection_for(self.database_path) as connection:
            row = connection.execute(
                "SELECT outcome FROM lawyer_decisions WHERE id = ?", (decision_id,)
            ).fetchone()
            if row is None:
                return None
            if row["outcome"]:
                raise ValueError("O desfecho deste processo já foi registrado.")
            connection.execute(
                "UPDATE lawyer_decisions SET outcome = ?, outcome_at = ?, outcome_note = ? WHERE id = ?",
                (outcome, _now(), note, decision_id),
            )
            updated = connection.execute(
                "SELECT * FROM lawyer_decisions WHERE id = ?", (decision_id,)
            ).fetchone()
        return dict(updated)

    def lawyer_performance(self, lawyer_id: str, favorable: frozenset[str]) -> dict:
        """
        Números do próprio advogado.

        Êxito e aderência são coisas diferentes e ficam separados de propósito:
        aderência mede se ele seguiu a política, êxito mede se deu certo. Um
        advogado que sempre acata tem aderência de 100% e pode ter êxito baixo.
        """
        with connection_for(self.database_path) as connection:
            total_cases = int(connection.execute(
                "SELECT COUNT(*) FROM cases WHERE assigned_lawyer_id = ?", (lawyer_id,)
            ).fetchone()[0])
            rows = connection.execute(
                """SELECT decision.action AS action, decision.outcome AS outcome,
                          analysis.recommendation AS recommendation
                   FROM lawyer_decisions AS decision
                   JOIN cases ON cases.id = decision.case_id
                   LEFT JOIN analyses AS analysis ON analysis.id = decision.analysis_id
                   WHERE cases.assigned_lawyer_id = ?""",
                (lawyer_id,),
            ).fetchall()
            closed_cases = int(connection.execute(
                """SELECT COUNT(DISTINCT decision.case_id) FROM lawyer_decisions AS decision
                   JOIN cases ON cases.id = decision.case_id
                   WHERE cases.assigned_lawyer_id = ? AND decision.outcome IS NOT NULL""",
                (lawyer_id,),
            ).fetchone()[0])

        outcomes: dict[str, int] = {}
        actions: dict[str, int] = {}
        favoraveis = comparaveis = aderentes = 0
        for row in rows:
            actions[row["action"]] = actions.get(row["action"], 0) + 1
            if row["outcome"]:
                outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1
                if row["outcome"] in favorable:
                    favoraveis += 1
            if row["recommendation"] and row["action"]:
                comparaveis += 1
                if row["recommendation"].strip().upper() == row["action"].strip().upper():
                    aderentes += 1

        registrados = sum(outcomes.values())
        return {
            "total_cases": total_cases,
            "active_cases": total_cases - closed_cases,
            "closed_cases": closed_cases,
            "decisions": len(rows),
            "outcomes_recorded": registrados,
            "pending_outcome": len(rows) - registrados,
            "success_rate": round(favoraveis / registrados, 4) if registrados else None,
            "adherence_rate": round(aderentes / comparaveis, 4) if comparaveis else None,
            "outcomes": outcomes,
            "actions": actions,
        }

    def case_flow(self, case_id: str) -> dict:
        """Fase e próxima ação do processo (máquina de estados em fluxo.py)."""
        with connection_for(self.database_path) as connection:
            def linhas(sql: str) -> list[dict]:
                return [dict(row) for row in connection.execute(sql, (case_id,)).fetchall()]
            dados = {
                "caso": _row(connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()),
                "analyses": linhas("SELECT id, recommendation, pricing, created_at FROM analyses WHERE case_id = ? ORDER BY created_at DESC LIMIT 1"),
                "decisions": linhas("SELECT * FROM lawyer_decisions WHERE case_id = ? ORDER BY created_at DESC LIMIT 1"),
                "documents": linhas("SELECT created_at FROM documents WHERE case_id = ? AND deleted_at IS NULL"),
                "requests": linhas("SELECT id, document_type, status, created_at, responded_at FROM document_requests WHERE case_id = ?"),
                "negotiations": linhas("SELECT * FROM negotiation_outcomes WHERE case_id = ? ORDER BY created_at DESC"),
                "judicials": linhas("SELECT * FROM judicial_outcomes WHERE case_id = ? ORDER BY created_at DESC LIMIT 1"),
            }
        return calcular_fase(**dados)

    def lawyer_queue(self, lawyer_id: str) -> list[dict]:
        """Processos do advogado na ordem da próxima ação: o que precisa dele primeiro."""
        itens = [{**case, "fase": self.case_flow(case["id"])} for case in self.list_cases(lawyer_id=lawyer_id)]
        return sorted(itens, key=lambda item: (item["fase"]["prioridade"], -item["fase"]["dias_parado"]))

    def save_document_reading(self, document_id: str, model: str, status: str,
                              result: dict | None, error: str | None) -> dict:
        record = {"document_id": document_id, "model": model, "status": status,
                  "result": _json(result) if result is not None else None, "error": error, "created_at": _now()}
        with connection_for(self.database_path) as connection:
            connection.execute(
                """INSERT INTO document_ai_readings (document_id, model, status, result, error, created_at)
                VALUES (:document_id, :model, :status, :result, :error, :created_at)
                ON CONFLICT(document_id) DO UPDATE SET model = excluded.model, status = excluded.status,
                result = excluded.result, error = excluded.error, created_at = excluded.created_at""", record)
        return {**record, "result": result}

    def list_document_readings(self, case_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                """SELECT r.* FROM document_ai_readings r JOIN documents d ON d.id = r.document_id
                WHERE d.case_id = ? AND d.deleted_at IS NULL ORDER BY r.created_at""", (case_id,)).fetchall()
        return [{**dict(row), "result": json.loads(row["result"]) if row["result"] else None} for row in rows]

    def replace_document_chunks(self, document: dict, chunks: list[dict]) -> None:
        with connection_for(self.database_path) as connection:
            connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document["id"],))
            connection.executemany("""INSERT INTO document_chunks
                (id, document_id, sha256, chunk_index, page_start, page_end, text_content, token_estimate, created_at)
                VALUES (:id, :document_id, :sha256, :chunk_index, :page_start, :page_end, :text_content, :token_estimate, :created_at)""", chunks)

    def list_case_chunks(self, case_id: str, document_ids: list[str] | None = None) -> list[dict]:
        params: list[object] = [case_id]
        extra = ""
        if document_ids:
            extra = " AND d.id IN (" + ",".join("?" for _ in document_ids) + ")"
            params.extend(document_ids)
        with connection_for(self.database_path) as connection:
            rows = connection.execute("""SELECT c.*, d.original_filename FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.case_id = ? AND d.deleted_at IS NULL
                  AND d.status IN ('COMPLETED', 'COMPLETED_WITH_WARNINGS')""" + extra +
                " ORDER BY d.created_at, c.chunk_index", params).fetchall()
        return [dict(row) for row in rows]

    def document_chunk_count(self, document_id: str) -> int:
        with connection_for(self.database_path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM document_chunks WHERE document_id = ?", (document_id,)).fetchone()[0])

    def save_chunk_embeddings(self, chunks: list[dict], model: str, vectors: list[list[float]]) -> None:
        with connection_for(self.database_path) as connection:
            connection.executemany("UPDATE document_chunks SET embedding_model = ?, embedding_json = ? WHERE id = ?",
                [(model, _json(vector), chunk["id"]) for chunk, vector in zip(chunks, vectors, strict=True)])

    def create_chat_conversation(self, case_id: str, user_id: str, document_ids: list[str]) -> dict:
        record = {"id": str(uuid4()), "case_id": case_id, "created_by_user_id": user_id,
                  "document_filter": _json(document_ids), "created_at": _now()}
        with connection_for(self.database_path) as connection:
            connection.execute("""INSERT INTO document_chat_conversations
                (id, case_id, created_by_user_id, document_filter, created_at)
                VALUES (:id, :case_id, :created_by_user_id, :document_filter, :created_at)""", record)
        record["document_filter"] = document_ids
        return record

    def get_chat_conversation(self, conversation_id: str, case_id: str, user_id: str | None = None) -> dict | None:
        with connection_for(self.database_path) as connection:
            query, params = "SELECT * FROM document_chat_conversations WHERE id = ? AND case_id = ?", [conversation_id, case_id]
            if user_id is not None:
                query += " AND created_by_user_id = ?"; params.append(user_id)
            row = connection.execute(query, params).fetchone()
        record = _row(row)
        if record: record["document_filter"] = json.loads(record["document_filter"])
        return record

    def list_chat_conversations(self, case_id: str, user_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute("SELECT * FROM document_chat_conversations WHERE case_id = ? AND created_by_user_id = ? ORDER BY created_at DESC", (case_id, user_id)).fetchall()
        return [{**dict(row), "document_filter": json.loads(row["document_filter"])} for row in rows]

    def list_chat_messages(self, conversation_id: str) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute("SELECT * FROM document_chat_messages WHERE conversation_id = ? ORDER BY created_at", (conversation_id,)).fetchall()
        return [{**dict(row), "citations": json.loads(row["citations"])} for row in rows]

    def save_chat_message(self, conversation_id: str, role: str, content: str, citations: list[dict] | None = None,
                          retrieval_mode: str | None = None, model: str | None = None) -> dict:
        record = {"id": str(uuid4()), "conversation_id": conversation_id, "role": role, "content": content,
                  "citations": _json(citations or []), "retrieval_mode": retrieval_mode, "model": model,
                  "prompt_version": "rag-chat-v1", "created_at": _now()}
        with connection_for(self.database_path) as connection:
            connection.execute("""INSERT INTO document_chat_messages
                (id, conversation_id, role, content, citations, retrieval_mode, model, prompt_version, created_at)
                VALUES (:id, :conversation_id, :role, :content, :citations, :retrieval_mode, :model, :prompt_version, :created_at)""", record)
        record["citations"] = citations or []
        return record

    def save_chat_retrievals(self, message_id: str, chunks: list[dict]) -> None:
        with connection_for(self.database_path) as connection:
            connection.executemany("INSERT INTO document_chat_retrievals (message_id, chunk_id, rank, score) VALUES (?, ?, ?, ?)",
                [(message_id, item["id"], rank, item["score"]) for rank, item in enumerate(chunks, 1)])

    def search_cases(self, bank_id: str, termo: str, limit: int = 30) -> list[dict]:
        """
        Busca de processos da empresa pelo que a operação tem em mãos: número do processo,
        número do contrato ou nome da parte. Procura no cadastro, na leitura por IA e no
        texto extraído de cada página — o texto cobre o caso em que não houve leitura por IA.
        """
        like = f"%{termo}%"
        alvo = termo.casefold()
        encontrados: dict[str, dict] = {}

        def adicionar(row: sqlite3.Row, onde: str, trecho: str, document_id: str | None = None, pagina: int | None = None) -> None:
            item = encontrados.setdefault(row["case_id"], {
                "case_id": row["case_id"], "case_number": row["case_number"], "uf": row["uf"],
                "value_of_claim": row["value_of_claim"], "assigned_lawyer_id": row["assigned_lawyer_id"], "matches": []})
            if len(item["matches"]) < 3 and not any(m["onde"] == onde for m in item["matches"]):
                item["matches"].append({"onde": onde, "trecho": trecho, "document_id": document_id, "pagina": pagina})

        colunas = "c.id AS case_id, c.case_number, c.uf, c.value_of_claim, c.assigned_lawyer_id"
        with connection_for(self.database_path) as connection:
            for row in connection.execute(
                    f"SELECT {colunas} FROM cases c WHERE c.bank_id = ? AND c.case_number LIKE ? LIMIT ?",
                    (bank_id, like, limit)):
                adicionar(row, "Número do processo", row["case_number"])
            for row in connection.execute(
                    f"""SELECT {colunas}, r.result, d.id AS document_id, d.original_filename
                    FROM document_ai_readings r JOIN documents d ON d.id = r.document_id AND d.deleted_at IS NULL
                    JOIN cases c ON c.id = d.case_id
                    WHERE c.bank_id = ? AND r.status = 'COMPLETED' AND r.result LIKE ? LIMIT 200""", (bank_id, like)):
                leitura = json.loads(row["result"])
                if alvo in (leitura.get("numero_contrato") or "").casefold():
                    adicionar(row, f"Contrato nº {leitura['numero_contrato']}", f"Lido por IA em {row['original_filename']}", row["document_id"])
                if alvo in (leitura.get("nome_parte_autora") or "").casefold():
                    adicionar(row, "Parte autora", leitura["nome_parte_autora"], row["document_id"])
            for row in connection.execute(
                    f"""SELECT {colunas}, p.text_content, p.page_number, d.id AS document_id, d.original_filename
                    FROM document_pages p JOIN documents d ON d.id = p.document_id AND d.deleted_at IS NULL
                    JOIN cases c ON c.id = d.case_id
                    WHERE c.bank_id = ? AND p.text_content LIKE ? LIMIT 200""", (bank_id, like)):
                adicionar(row, f"{row['original_filename']}, página {row['page_number']}",
                          _trecho(row["text_content"], termo), row["document_id"], row["page_number"])
        return list(encontrados.values())[:limit]

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
