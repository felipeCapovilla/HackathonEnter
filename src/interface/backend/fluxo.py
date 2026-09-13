"""
Fase do processo na visão do advogado: o que já aconteceu e qual é a próxima ação.

É a máquina de estados de docs/fluxo_do_processo.md. As rotas de decisão, negociação
e sentença consultam isto antes de escrever, então a tela só oferece o que cabe
naquele momento e a API recusa o resto (quem escolheu acordo não "encerra como
defesa": o único caminho do acordo para a sentença é a recusa do autor).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

ROTULOS = {
    "AGUARDANDO_AVALIACAO": "Aguardando avaliação",
    "REAVALIAR": "Documentos novos",
    "PRONTO_PARA_DECIDIR": "Pronto para decidir",
    "AGUARDANDO_DOCUMENTO": "Aguardando documento",
    "EM_NEGOCIACAO": "Em negociação",
    "CONTRAPROPOSTA": "Contraproposta recebida",
    "EM_DEFESA": "Em defesa",
    "ENCERRADO": "Encerrado",
}
PROXIMA_ACAO = {
    "AGUARDANDO_AVALIACAO": "Avaliar o processo",
    "REAVALIAR": "Reavaliar: há documentos novos",
    "PRONTO_PARA_DECIDIR": "Registrar a decisão",
    "AGUARDANDO_DOCUMENTO": "Aguardar a empresa enviar o documento",
    "EM_NEGOCIACAO": "Registrar a resposta do autor",
    "CONTRAPROPOSTA": "Responder à contraproposta",
    "EM_DEFESA": "Registrar a sentença quando sair",
    "ENCERRADO": "Nada a fazer: processo encerrado",
}
PRIORIDADE = {"REAVALIAR": 1, "CONTRAPROPOSTA": 1, "PRONTO_PARA_DECIDIR": 2, "AGUARDANDO_AVALIACAO": 3,
              "EM_NEGOCIACAO": 4, "EM_DEFESA": 6, "AGUARDANDO_DOCUMENTO": 7, "ENCERRADO": 9}
DIAS_PARA_COBRAR = 7


def _dt(valor: str | None) -> datetime | None:
    if not valor:
        return None
    momento = datetime.fromisoformat(valor)
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def calcular_fase(*, caso: dict, analyses: list[dict], decisions: list[dict], documents: list[dict],
                  requests: list[dict], negotiations: list[dict], judicials: list[dict]) -> dict:
    """Listas já filtradas do processo; `analyses`, `decisions` e `negotiations` da mais nova para a mais velha."""
    analise = analyses[0] if analyses else None
    decisao = decisions[0] if decisions else None
    negociacao = next((n for n in negotiations if decisao and n["decision_id"] == decisao["id"]), None)
    mudancas = [_dt(d["created_at"]) for d in documents] + [_dt(r["responded_at"]) for r in requests if r.get("responded_at")]
    ultima_mudanca = max((m for m in mudancas if m), default=None)
    documentos_novos = bool(analise and ultima_mudanca and ultima_mudanca > _dt(analise["created_at"]))
    pedido_aberto = next((r for r in requests if r["status"] == "REQUESTED"), None)

    if decisao and decisao.get("outcome"):
        codigo = "ENCERRADO"
    elif decisao is None or decisao["action"] == "RECUPERAR":
        if decisao and pedido_aberto:
            codigo = "AGUARDANDO_DOCUMENTO"
        elif analise is None:
            codigo = "AGUARDANDO_AVALIACAO"
        elif documentos_novos or (decisao and _dt(analise["created_at"]) <= _dt(decisao["created_at"])):
            codigo = "REAVALIAR"
        else:
            codigo = "PRONTO_PARA_DECIDIR"
    elif decisao["action"] == "ACORDO":
        status = negociacao["status"] if negociacao else None
        codigo = ("CONTRAPROPOSTA" if status == "CONTRAPROPOSTA"
                  else "EM_DEFESA" if status in {"RECUSADO", "SEM_RESPOSTA"} else "EM_NEGOCIACAO")
    else:
        codigo = "EM_DEFESA"

    marcos = [_dt(caso["created_at"]) if caso else None, _dt(analise["created_at"]) if analise else None,
              _dt(decisao["created_at"]) if decisao else None, _dt(negociacao["created_at"]) if negociacao else None]
    marco = max((m for m in marcos if m), default=None)
    dias = (datetime.now(UTC) - marco).days if marco else 0
    proxima, prioridade = PROXIMA_ACAO[codigo], PRIORIDADE[codigo]
    if codigo == "EM_NEGOCIACAO" and dias >= DIAS_PARA_COBRAR:
        proxima, prioridade = f"Cobrar o autor: sem resposta há {dias} dias", 1
    return {
        "codigo": codigo, "rotulo": ROTULOS[codigo], "proxima_acao": proxima, "prioridade": prioridade,
        "dias_parado": dias,
        # Depois de decidido, documento novo não reabre a decisão: vira aviso para o advogado conferir.
        "documentos_novos": documentos_novos and codigo not in {"ENCERRADO", "REAVALIAR"},
        "recomendacao": analise["recommendation"] if analise else None,
        "decisao": decisao, "negociacao": negociacao, "pedido_aberto": pedido_aberto,
        "sentenca": judicials[0] if judicials else None,
        "pricing": json.loads(analise["pricing"]) if analise and analise.get("pricing") else None,
    }
