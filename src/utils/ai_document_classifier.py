"""
Classificação automática do tipo de documento no upload do banco.

Substitui a seleção manual do tipo: a IA lê uma amostra do texto extraído e
decide entre os tipos conhecidos da política, ou recusa quando o conteúdo não
tem relação alguma com o processo (documento legítimo mas fora das categorias
específicas continua como OUTRO, não é recusado). Com OPENAI_API_KEY ausente
ou falha na chamada, cai para a validação determinística por palavras-chave
já usada no fluxo antigo — nunca recusa por conta própria, só classifica ou
deixa como OUTRO para revisão humana.
"""
from __future__ import annotations

import logging
import os
from typing import Literal

from pydantic import BaseModel

from src.interface.backend.schemas import DocumentType
from .document_type_validator import TYPE_PATTERNS, _normalize

logger = logging.getLogger(__name__)

CLASSIFICATION_CHARACTERS = 8000

_TYPE_DESCRIPTIONS: dict[DocumentType, str] = {
    DocumentType.AUTOS: "Autos do processo judicial: petição inicial, despachos, citação, parte autora.",
    DocumentType.CONTRATO: "Contrato de empréstimo/cédula de crédito: cláusulas, valor mutuado, assinatura ou aceite.",
    DocumentType.EXTRATO: "Extrato bancário: lançamentos, saldo, movimentação da conta.",
    DocumentType.COMPROVANTE_CREDITO: "Comprovante de operação/liberação de crédito, registro BACEN do valor emprestado.",
    DocumentType.DOSSIE: "Dossiê pericial do processo: parecer técnico, exame documental, conformidade.",
    DocumentType.DEMONSTRATIVO_DIVIDA: "Demonstrativo de evolução da dívida: parcelas, competências, saldo devedor ao longo do tempo.",
    DocumentType.LAUDO_REFERENCIADO: "Laudo técnico referenciado: evidência, autenticação, conclusão pericial.",
    DocumentType.OUTRO: "Documento legítimo do processo que não se encaixa nas categorias acima (ex.: procuração, identidade, comprovante de residência, correspondência).",
}

_KNOWN_TYPES: tuple[str, ...] = tuple(item.value for item in _TYPE_DESCRIPTIONS)


class _Classification(BaseModel):
    tipo: Literal[
        "AUTOS", "CONTRATO", "EXTRATO", "COMPROVANTE_CREDITO", "DOSSIE",
        "DEMONSTRATIVO_DIVIDA", "LAUDO_REFERENCIADO", "OUTRO", "RECUSADO",
    ]
    justificativa: str


class AIDocumentClassification(BaseModel):
    document_type: DocumentType | None
    rejected: bool
    reason: str
    source: Literal["IA", "REGRA"]


def classify_document_type(text: str) -> AIDocumentClassification:
    """Classifica o texto extraído. Nunca levanta: falha vira fallback determinístico."""
    sample = text.strip()[:CLASSIFICATION_CHARACTERS]
    if os.getenv("OPENAI_API_KEY", "").strip() and sample:
        try:
            return _classify_with_ai(sample)
        except Exception as exc:  # noqa: BLE001 - upload não pode falhar por causa da IA
            logger.info("Classificação de tipo por IA indisponível, usando validação determinística: %s", exc)
    return _classify_by_keywords(sample)


def _classify_with_ai(sample: str) -> AIDocumentClassification:
    from openai import OpenAI

    catalogo = "\n".join(f"- {tipo}: {desc}" for tipo, desc in _TYPE_DESCRIPTIONS.items())
    with OpenAI(timeout=30.0, max_retries=1) as client:
        response = client.responses.parse(
            model=os.getenv("ENTERAGREE_DOCTYPE_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            input=[
                {"role": "system", "content": (
                    "Você classifica o tipo de um documento enviado por um banco num processo de "
                    "empréstimo não reconhecido pelo cliente. Escolha exatamente um tipo pelo "
                    "conteúdo do texto (nunca pelo nome do arquivo, que você não vê). Tipos:\n"
                    + catalogo +
                    "\nUse RECUSADO somente quando o texto não tiver relação alguma com um processo "
                    "bancário/judicial de empréstimo — por exemplo, é sobre outro assunto completamente "
                    "diferente. Um documento legítimo do processo que não se encaixe nas categorias "
                    "específicas é OUTRO, nunca RECUSADO. Justifique em uma frase curta, em português."
                )},
                {"role": "user", "content": f"Texto do documento (início):\n{sample}"},
            ],
            text_format=_Classification,
            store=False,
        )
    parsed = response.output_parsed
    if parsed is None:
        raise ValueError("Resposta da IA sem classificação estruturada.")
    if parsed.tipo == "RECUSADO":
        return AIDocumentClassification(document_type=None, rejected=True, reason=parsed.justificativa, source="IA")
    return AIDocumentClassification(
        document_type=DocumentType(parsed.tipo), rejected=False, reason=parsed.justificativa, source="IA",
    )


def _classify_by_keywords(sample: str) -> AIDocumentClassification:
    """
    Fallback conservador: nunca recusa por conta própria.

    Sem chave (ou com a IA fora do ar) o melhor que dá para afirmar é "bate com
    palavras-chave de X" ou "não bate com nada conhecido" — recusar de verdade
    exige o julgamento que só a IA faz; na dúvida, OUTRO fica para revisão humana.
    """
    normalized = _normalize(sample)
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
