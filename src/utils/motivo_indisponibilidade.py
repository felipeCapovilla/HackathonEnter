"""
Classifica o texto livre de "documento indisponível" num motivo estruturado.

O painel pede o motivo como lista; isto cobre respostas antigas ou vindas da API sem ele.
Com OPENAI_API_KEY usa o modelo; sem chave (ou se a chamada falhar), cai para palavras-chave.
O número de valor em jogo nunca passa pelo modelo: a IA só escolhe a categoria.
"""
from __future__ import annotations

import logging
import os
import unicodedata
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

Motivo = Literal["NAO_LOCALIZADO", "CONTRATO_FISICO_NAO_DIGITALIZADO", "CORRESPONDENTE_NAO_ENVIOU",
                 "FORA_DO_PRAZO_DE_GUARDA", "SISTEMA_SEM_EXPORTACAO", "OPERACAO_INEXISTENTE", "OUTRO"]

REGRAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("OPERACAO_INEXISTENTE", ("nao existe", "inexistente", "nunca contrat", "fraude", "golpe", "nao ha operacao")),
    ("CONTRATO_FISICO_NAO_DIGITALIZADO", ("fisico", "papel", "digitaliz", "escane", "arquivo morto")),
    ("CORRESPONDENTE_NAO_ENVIOU", ("correspondente", "parceiro", "promotora", "agente")),
    ("FORA_DO_PRAZO_DE_GUARDA", ("prazo de guarda", "temporalidade", "descart", "expurg", "retencao")),
    ("NAO_LOCALIZADO", ("nao localiz", "nao encontr", "extravi", "perdid", "sem registro")),
    ("SISTEMA_SEM_EXPORTACAO", ("sistema", "legado", "export", "integracao")),
)


class _Classificacao(BaseModel):
    motivo: Motivo


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.casefold()


def por_regra(texto: str) -> str:
    normalizado = _normalizar(texto)
    for motivo, termos in REGRAS:
        if any(termo in normalizado for termo in termos):
            return motivo
    return "OUTRO"


def classificar_motivo(texto: str, documento: str) -> tuple[str, str]:
    """Devolve (motivo, fonte) com fonte "IA" ou "REGRA"."""
    if os.getenv("OPENAI_API_KEY", "").strip():
        try:
            from openai import OpenAI

            with OpenAI(timeout=20.0, max_retries=1) as client:
                response = client.responses.parse(
                    model=os.getenv("ENTERAGREE_DOSSIE_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
                    input=[
                        {"role": "system", "content": (
                            "Você classifica por que um banco não conseguiu entregar um documento de defesa "
                            "num processo de empréstimo não reconhecido. Escolha um único motivo. "
                            "OPERACAO_INEXISTENTE só quando o texto indicar que a operação não existe ou é fraude. "
                            "Use OUTRO quando nada se aplicar.")},
                        {"role": "user", "content": f"Documento: {documento}\nResposta do banco: {texto}"},
                    ],
                    text_format=_Classificacao,
                    store=False,
                )
            if response.output_parsed is not None:
                return response.output_parsed.motivo, "IA"
        except Exception as exc:  # noqa: BLE001 - a resposta do banco não pode falhar por causa da IA
            logger.info("Classificação por IA indisponível, usando regra: %s", exc)
    return por_regra(texto), "REGRA"
