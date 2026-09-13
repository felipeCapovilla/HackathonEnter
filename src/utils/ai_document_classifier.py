"""
Fallback determinístico de tipo para o upload sem seleção manual.

A classificação em si é feita por `src.tools.leitor_documentos.ler_documento`
(mesma leitura por IA usada como complemento consultivo em todo o resto da
aplicação — um único prompt, uma única chamada por documento). Este módulo só
cobre o caso em que essa leitura não está disponível (sem OPENAI_API_KEY, ou
falha do provedor): nesse cenário, recusar de verdade exigiria o julgamento
que só a IA faz, então o fallback nunca recusa sozinho — na dúvida, marca
como "Outro" para revisão humana.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from src.interface.backend.schemas import DocumentType
from .document_type_validator import TYPE_PATTERNS, _normalize


class AIDocumentClassification(BaseModel):
    document_type: DocumentType | None
    rejected: bool
    reason: str
    source: Literal["IA", "REGRA"]


def classify_by_keywords(text: str) -> AIDocumentClassification:
    normalized = _normalize(text)
    matches_by_type = {
        document_type: [pattern.pattern for pattern in patterns if pattern.search(normalized)]
        for document_type, patterns in TYPE_PATTERNS.items()
    }
    best_type = max(matches_by_type, key=lambda item: len(matches_by_type[item])) if matches_by_type else None
    if best_type is not None and len(matches_by_type[best_type]) >= 2:
        return AIDocumentClassification(
            document_type=best_type, rejected=False,
            reason="Classificado por palavras-chave (IA indisponível).", source="REGRA",
        )
    return AIDocumentClassification(
        document_type=DocumentType.OUTRO, rejected=False,
        reason="Não foi possível identificar o tipo por palavras-chave (IA indisponível); revise manualmente.",
        source="REGRA",
    )
