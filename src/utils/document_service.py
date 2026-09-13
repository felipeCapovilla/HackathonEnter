"""Streaming document storage and deterministic text extraction."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader

from src.interface.backend.config import Settings
from .document_type_validator import validate_document_type
from src.interface.backend.repository import Repository
from src.interface.backend.schemas import DocumentStatus, DocumentType, DocumentTypeStatus, SourceParty


CHUNK_SIZE = 1024 * 1024
EXTRACTION_BATCH_SIZE = 100
TYPE_VALIDATION_CHARACTERS = 100_000
ALLOWED_SUFFIXES = {".pdf", ".txt"}
logger = logging.getLogger(__name__)


def _safe_filename(filename: str | None) -> str:
    candidate = Path(filename or "documento").name
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", candidate)
    return sanitized or "documento"


class DocumentService:
    def __init__(self, repository: Repository, settings: Settings,
                 on_extraction_completed: Callable[[str], None] | None = None) -> None:
        self.repository = repository
        self.settings = settings
        self.on_extraction_completed = on_extraction_completed
        self.settings.document_dir.mkdir(parents=True, exist_ok=True)

    async def store_upload(
        self,
        *,
        case_id: str,
        upload: UploadFile,
        declared_type: DocumentType,
        source_party: SourceParty,
        request_id: str | None,
    ) -> dict:
        filename = _safe_filename(upload.filename)
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(415, "Envie um arquivo PDF ou TXT.")

        temporary_path = self.settings.document_dir / f".upload-{uuid4().hex}.part"
        digest = hashlib.sha256()
        total_bytes = 0
        first_chunk = b""
        try:
            with temporary_path.open("wb") as destination:
                while chunk := await upload.read(CHUNK_SIZE):
                    if not first_chunk:
                        first_chunk = chunk[:16]
                    total_bytes += len(chunk)
                    if total_bytes > self.settings.max_upload_bytes:
                        raise HTTPException(413, "Arquivo excede o limite configurado.")
                    digest.update(chunk)
                    destination.write(chunk)
            if suffix == ".pdf" and not first_chunk.startswith(b"%PDF-"):
                raise HTTPException(422, "O conteúdo enviado não corresponde a um PDF.")

            case_directory = self.settings.document_dir / case_id
            case_directory.mkdir(parents=True, exist_ok=True)
            document_path = case_directory / f"{digest.hexdigest()}-{uuid4().hex}{suffix}"
            temporary_path.replace(document_path)
            try:
                document = self.repository.create_document(
                    case_id=case_id,
                    original_filename=filename,
                    file_path=document_path,
                    declared_type=declared_type,
                    source_party=source_party,
                    sha256=digest.hexdigest(),
                    request_id=request_id,
                )
            except Exception:
                document_path.unlink(missing_ok=True)
                raise
            return document
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

    def process_document(self, document_id: str) -> None:
        document = self.repository.get_document_internal(document_id)
        if document is None:
            return
        path = Path(document["file_path"])
        self.repository.update_document_extraction(
            document_id,
            status=DocumentStatus.EXTRACTING.value,
            page_count=0,
            pages_extracted=0,
            quality_flags=[],
            detected_type=None,
            type_status=DocumentTypeStatus(document["type_status"]),
        )
        try:
            self.repository.clear_document_pages(document_id)
            page_count = 0
            pages_extracted = 0
            quality_flags: set[str] = set()
            validation_sample: list[str] = []
            sample_size = 0
            batch: list[dict] = []
            for page in self._iter_pages(path):
                page_count += 1
                pages_extracted += 1
                quality_flags.update(page["quality_flags"])
                if sample_size < TYPE_VALIDATION_CHARACTERS:
                    remaining = TYPE_VALIDATION_CHARACTERS - sample_size
                    excerpt = page["text_content"][:remaining]
                    validation_sample.append(excerpt)
                    sample_size += len(excerpt)
                batch.append(page)
                if len(batch) == EXTRACTION_BATCH_SIZE:
                    self.repository.append_document_pages(document_id, batch)
                    batch = []
            if batch:
                self.repository.append_document_pages(document_id, batch)
            if page_count == 0:
                quality_flags.add("DOCUMENT_WITHOUT_PAGES")
            sample = "\n".join(validation_sample)
            validation = validate_document_type(DocumentType(document["declared_type"]), sample)
            status = (
                DocumentStatus.COMPLETED_WITH_WARNINGS.value
                if quality_flags or validation.status.value == "UNCONFIRMED"
                else DocumentStatus.COMPLETED.value
            )
            self.repository.update_document_extraction(
                document_id,
                status=status,
                page_count=page_count,
                pages_extracted=pages_extracted,
                quality_flags=sorted(quality_flags),
                detected_type=validation.detected_type,
                type_status=validation.status,
            )
            completed = True
        except Exception as exc:
            completed = False
            logger.exception("Document extraction failed for %s", document_id)
            self.repository.update_document_extraction(
                document_id,
                status=DocumentStatus.FAILED.value,
                page_count=0,
                pages_extracted=0,
                quality_flags=[f"EXTRACTION_FAILED:{type(exc).__name__}"],
                detected_type=None,
                type_status=DocumentTypeStatus(document["type_status"]),
            )
        # Fora do try da extração: uma falha no passo seguinte não marca o documento como falho.
        if completed:
            try:
                from .document_chunk_service import DocumentChunkService
                DocumentChunkService(self.repository, self.settings.rag_chunk_chars, self.settings.rag_chunk_overlap_chars,
                                     self.settings.rag_embedding_model).index_document(document_id)
            except Exception:
                logger.exception("Document indexing failed for %s", document_id)
        if completed and self.on_extraction_completed is not None:
            try:
                self.on_extraction_completed(document_id)
            except Exception:
                logger.exception("Post-extraction step failed for %s", document_id)

    def _iter_pages(self, path: Path) -> Iterable[dict]:
        if path.suffix.lower() == ".txt":
            text = path.read_text(encoding="utf-8", errors="replace")
            flags = ["LOW_TEXT_COVERAGE_TODO_OCR"] if len(text.strip()) < 50 else []
            yield self._page(1, text, flags)
            return

        reader = PdfReader(str(path))
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            flags = ["LOW_TEXT_COVERAGE_TODO_OCR"] if len(text.strip()) < 50 else []
            yield self._page(page_number, text, flags)

    @staticmethod
    def _page(page_number: int, text: str, quality_flags: list[str]) -> dict:
        return {
            "page_number": page_number,
            "text_content": text,
            "extraction_method": "PYPDF_TEXT",
            "quality_flags": quality_flags,
        }
