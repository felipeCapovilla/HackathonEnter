"""Deterministic validation of the user-declared document type."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.interface.backend.schemas import DocumentType, DocumentTypeStatus


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.upper().split())


TYPE_PATTERNS: dict[DocumentType, tuple[re.Pattern[str], ...]] = {
    DocumentType.AUTOS: (re.compile(r"PETICAO INICIAL"), re.compile(r"AUTOS"), re.compile(r"PARTE AUTORA")),
    DocumentType.CONTRATO: (
        re.compile(r"CEDULA DE CREDITO"), re.compile(r"CONTRAT[OA]"),
        re.compile(r"MUTUO|EMPRESTIMO"), re.compile(r"ASSINATURA|ACEITE"),
    ),
    DocumentType.EXTRATO: (re.compile(r"EXTRATO"), re.compile(r"SALDO"), re.compile(r"LANCAMENTOS?|MOVIMENTACAO")),
    DocumentType.COMPROVANTE_CREDITO: (
        re.compile(r"COMPROVANTE"), re.compile(r"OPERACAO DE CREDITO|LIBERACAO DE CREDITO"),
        re.compile(r"BACEN|BANCO CENTRAL"),
    ),
    DocumentType.DOSSIE: (re.compile(r"DOSSIE"), re.compile(r"PARECER"), re.compile(r"CONFORME|NAO CONFORME")),
    DocumentType.DEMONSTRATIVO_DIVIDA: (
        re.compile(r"DEMONSTRATIVO"), re.compile(r"EVOLUCAO (DA )?DIVIDA"), re.compile(r"PARCELA|COMPETENCIA"),
    ),
    DocumentType.LAUDO_REFERENCIADO: (
        re.compile(r"LAUDO"), re.compile(r"EVIDENCIA|AUTENTICACAO"), re.compile(r"OBSERVACOES FINAIS|CONCLUSAO"),
    ),
}


@dataclass(frozen=True, slots=True)
class DocumentTypeValidation:
    declared_type: DocumentType
    detected_type: DocumentType | None
    status: DocumentTypeStatus
    declared_matches: list[str]
    alternative_matches: dict[str, list[str]]


def validate_document_type(declared_type: DocumentType, text: str) -> DocumentTypeValidation:
    if declared_type == DocumentType.OUTRO:
        return DocumentTypeValidation(declared_type, None, DocumentTypeStatus.UNCONFIRMED, [], {})

    normalized = _normalize(text)
    matches_by_type = {
        document_type: [pattern.pattern for pattern in patterns if pattern.search(normalized)]
        for document_type, patterns in TYPE_PATTERNS.items()
    }
    declared_matches = matches_by_type[declared_type]
    alternatives = {
        document_type.value: matches for document_type, matches in matches_by_type.items()
        if document_type != declared_type and matches
    }
    detected_type = max(matches_by_type, key=lambda item: len(matches_by_type[item]))
    detected_matches = matches_by_type[detected_type]

    if len(declared_matches) >= 2:
        status, detected = DocumentTypeStatus.CONFIRMED, declared_type
    elif len(detected_matches) >= 2 and detected_type != declared_type:
        status, detected = DocumentTypeStatus.MISMATCH, detected_type
    else:
        status = DocumentTypeStatus.UNCONFIRMED
        detected = detected_type if detected_matches else None

    return DocumentTypeValidation(declared_type, detected, status, declared_matches, alternatives)
