"""Faixa de negociação do acordo, ancorada nos 280 acordos reais da base."""
from __future__ import annotations

from contracts.schema import FaixaAcordo
from src.policy.constants import P2_ALVO, P2_PISO, P2_TETO
from src.policy.table import cluster_uf


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(v, hi))


def calcular_faixa(valor_causa: float, p_perda: float, uf: str | None = None,
                   dossie_nao_conforme: bool = False) -> FaixaAcordo:
    """
    Alvo parte de 30% do valor da causa e recebe ajustes explicáveis.
    Devolve QUATRO valores porque o advogado negocia com faixa, não com número.
    """
    if valor_causa <= 0:
        raise ValueError("valor_causa deve ser > 0")

    fator = P2_ALVO.valor
    if p_perda >= 0.80:
        fator += 0.03      # posição fraca: precisa oferecer mais
    elif p_perda <= 0.20:
        fator -= 0.03      # posição forte
    if dossie_nao_conforme:
        fator += 0.05
    c = cluster_uf(uf) if uf else "medio"
    fator += {"alto": 0.02, "medio": 0.0, "baixo": -0.02}[c]

    alvo = _clamp(fator, P2_PISO.valor, P2_TETO.valor)
    return FaixaAcordo(
        abertura=round(valor_causa * _clamp(alvo - 0.04, P2_PISO.valor, alvo), 2),
        alvo=round(valor_causa * alvo, 2),
        maximo_aceitavel=round(valor_causa * max(alvo, 0.35), 2),
        teto_absoluto=round(valor_causa * P2_TETO.valor, 2),
    )
