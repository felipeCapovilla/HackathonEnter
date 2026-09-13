"""Deterministic, page-aware chunks used by the document chat."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4
import os

from src.interface.backend.repository import Repository


class DocumentChunkService:
    def __init__(self, repository: Repository, chunk_chars: int = 4800, overlap_chars: int = 600, embedding_model: str = "text-embedding-3-small") -> None:
        self.repository, self.chunk_chars, self.overlap_chars, self.embedding_model = repository, chunk_chars, overlap_chars, embedding_model

    def index_document(self, document_id: str) -> int:
        document = self.repository.get_document_internal(document_id)
        if document is None:
            return 0
        chunks, text, pages, index = [], "", [], 0
        for page in self.repository.iter_document_pages(document_id):
            page_text = page["text_content"].strip()
            if not page_text:
                continue
            addition = ("\n\n" if text else "") + page_text
            if text and len(text) + len(addition) > self.chunk_chars:
                chunks.append(self._chunk(document, index, text, pages))
                index += 1
                text = text[-self.overlap_chars:] + "\n\n" + page_text
                pages = [pages[-1], page["page_number"]] if pages else [page["page_number"]]
            else:
                text += addition
                pages.append(page["page_number"])
        if text:
            chunks.append(self._chunk(document, index, text, pages))
        self.repository.replace_document_chunks(document, chunks)
        if chunks and os.getenv("OPENAI_API_KEY", "").strip():
            try:
                from openai import OpenAI
                with OpenAI(timeout=60.0, max_retries=1) as client:
                    vectors = client.embeddings.create(model=self.embedding_model, input=[c["text_content"] for c in chunks]).data
                self.repository.save_chunk_embeddings(chunks, self.embedding_model, [item.embedding for item in vectors])
            except Exception:
                # Retrieval remains available through its deterministic lexical ranking.
                pass
        return len(chunks)

    @staticmethod
    def _chunk(document: dict, index: int, text: str, pages: list[int]) -> dict:
        return {"id": str(uuid4()), "document_id": document["id"], "sha256": document["sha256"],
                "chunk_index": index, "page_start": min(pages), "page_end": max(pages),
                "text_content": text, "token_estimate": max(1, len(text) // 4),
                "created_at": datetime.now(UTC).isoformat()}
