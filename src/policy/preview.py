"""
Prévia do impacto de um contrato na carteira histórica, para a tela de admin.

Compara o contrato vigente com o proposto sobre uma amostra da base: quantas
decisões mudam e quanto muda a economia estimada. Usa só as flags de presença
(sem assumir leitura de dossiê), com a metodologia de src/policy/backtest.py.
"""
from __future__ import annotations

from functools import lru_cache

from contracts.schema import ParametrosContrato
from src.policy import constants as K
from src.policy.backtest import carregar, custo_realizado, custo_sem_politica
from src.policy.engine import decidir

PASSO_PADRAO = 5  # 1 a cada 5 processos: 12 mil casos, resposta em segundos


@lru_cache(maxsize=1)
def _base() -> tuple:
    return tuple(carregar(com_extracao_ia=False))


def simular(vigente: ParametrosContrato, proposto: ParametrosContrato, passo: int = PASSO_PADRAO) -> dict:
    casos = _base()[::passo]
    pago = sum(condenacao for _, condenacao in casos)
    contratos = {"vigente": vigente, "proposto": proposto}
    sem_politica = {"vigente": 0.0, "proposto": 0.0}
    com_politica = {"vigente": 0.0, "proposto": 0.0}
    acoes: dict[str, dict[str, int]] = {"vigente": {}, "proposto": {}}
    alteradas = 0
    for c, condenacao in casos:
        recomendacoes = {chave: decidir(c, contrato) for chave, contrato in contratos.items()}
        alteradas += recomendacoes["vigente"].acao != recomendacoes["proposto"].acao
        for chave, r in recomendacoes.items():
            sem_politica[chave] += custo_sem_politica(c, condenacao, contratos[chave])
            com_politica[chave] += custo_realizado(c, condenacao, r, K.P3.valor, K.P4.valor, contratos[chave])
            acoes[chave][r.acao] = acoes[chave].get(r.acao, 0) + 1

    def resultado(chave: str) -> dict:
        economia = sem_politica[chave] - com_politica[chave]
        return {"economia": round(economia, 2),
                "economia_percentual": round(economia / sem_politica[chave], 4) if sem_politica[chave] else 0.0,
                "custo_sem_politica": round(sem_politica[chave], 2),
                "custo_com_politica": round(com_politica[chave], 2),
                "acoes": acoes[chave]}

    return {
        "casos": len(casos),
        "pago_historico": round(pago, 2),
        "contrato_vigente": resultado("vigente"),
        "contrato_proposto": resultado("proposto"),
        "decisoes_alteradas": alteradas,
        "premissas": (f"Amostra de 1 a cada {passo} processos da base histórica, só com as flags de presença; "
                      f"aceitação {K.P3.valor:.0%}, recuperação {K.P4.valor:.0%}; valores da sentença, sem juros, "
                      f"com os honorários de cada contrato. Economia medida contra defender a carteira inteira."),
    }
