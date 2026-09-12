"""
Nó LangGraph: análise do Dossiê.  [FELIPE]

Contrato de saída: contracts.schema.AnaliseDossie

PRIORIDADE (o motor trava sem os dois primeiros):
  1. veredito .......................... conforme | nao_conforme | inconclusivo
                                         -> nao_conforme força ACORDO e o
                                            documento NUNCA vai aos autos
  2. analisou_assinatura_contrato ...... bool
                                         -> se True e o contrato está ausente,
                                            o contrato EXISTE: é a terceira via
                                            (11.870 casos, R$ 56,8M)
  3. itens[] ........................... desejável
  4. numero_contrato_referenciado ...... desejável

Só o item 2 autoriza inferir recuperabilidade. Um dossiê que validou apenas
RG e liveness NÃO prova que o contrato existe.
"""
from __future__ import annotations

from typing import Any

from contracts.schema import AnaliseDossie


def analisar_dossie(state: dict[str, Any]) -> dict[str, Any]:
    """Lê state['dossie_texto'] e devolve {'analise_dossie': AnaliseDossie}."""
    raise NotImplementedError("Felipe")
