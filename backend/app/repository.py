"""Persistence operations for the EnterAgree API."""

from __future__ import annotations

import json
import sqlite3
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

    def create_case(self, payload: CaseCreate) -> dict:
        case_id = str(uuid4())
        record = {
            "id": case_id,
            **payload.model_dump(),
            "uf": payload.uf.upper(),
            "created_at": _now(),
        }
        with connection_for(self.database_path) as connection:
            try:
                connection.execute(
                    """INSERT INTO cases (id, case_number, uf, value_of_claim, sub_subject, dossie_status, created_at)
                    VALUES (:id, :case_number, :uf, :value_of_claim, :sub_subject, :dossie_status, :created_at)""",
                    record,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Número de processo já cadastrado.") from exc
        return record

    def get_case(self, case_id: str) -> dict | None:
        with connection_for(self.database_path) as connection:
            return _row(connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone())

    def list_cases(self) -> list[dict]:
        with connection_for(self.database_path) as connection:
            rows = connection.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

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
        with connection_for(self.database_path) as connection:
            rows = connection.execute(
                "SELECT text_content FROM document_pages WHERE document_id = ? ORDER BY page_number",
                (document_id,),
            ).fetchall()
        chunks: list[str] = []
        remaining = maximum_characters
        for row in rows:
            text = row["text_content"]
            chunks.append(text[:remaining])
            remaining -= len(text)
            if remaining <= 0:
                break
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
                    documentary_status, reasons, feature_vector, feature_provenance, pricing, limitations, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["id"], record["case_id"], record["recommendation"], record["decision_code"],
                    record["policy_source"], record["agreement_probability"], record["documentary_status"],
                    _json(record["reasons"]), _json(record["feature_vector"]),
                    _json(record["feature_provenance"]),
                    _json(record["pricing"]) if record.get("pricing") is not None else None,
                    _json(record["limitations"]), record["created_at"],
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
            connection.execute(
                """UPDATE document_requests SET status = ?, response_reason = ?, responded_at = ?
                WHERE id = ?""",
                (status_value, reason, _now(), request_id),
            )
        return self.get_document_request(request_id)

    def mark_request_submitted(self, request_id: str) -> None:
        with connection_for(self.database_path) as connection:
            connection.execute(
                "UPDATE document_requests SET status = ?, responded_at = ? WHERE id = ?",
                (DocumentRequestStatus.SUBMITTED.value, _now(), request_id),
            )

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
        return record
