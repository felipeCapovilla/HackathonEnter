"""
MODELO 1 - Probabilidade de derrota.

Tabela glass-box de 16 segmentos, medida na base de 60k. Substitui modelo de
ML de propósito: nos dados, gradient boosting agrega ~+0,014 de AUC sobre
contar os 3 documentos críticos, e custa a auditabilidade por advogado.

Chave: (contrato, extrato, comprovante_credito, sub_assunto)
"""
from __future__ import annotations

import math

# (contrato, extrato, comprovante) x sub_assunto -> (n, p_perda)
TABELA: dict[tuple[int, int, int, str], tuple[int, float]] = {
    (0, 0, 0, "Generico"): (664, 0.9714),
    (0, 0, 0, "Golpe"): (3216, 0.9888),
    (0, 0, 1, "Generico"): (455, 0.9033),
    (0, 0, 1, "Golpe"): (2158, 0.9648),
    (0, 1, 0, "Generico"): (1149, 0.6075),
    (0, 1, 0, "Golpe"): (3964, 0.8151),
    (0, 1, 1, "Generico"): (1454, 0.2895),
    (0, 1, 1, "Golpe"): (3957, 0.5428),
    (1, 0, 0, "Generico"): (472, 0.6123),
    (1, 0, 0, "Golpe"): (1748, 0.7735),
    (1, 0, 1, "Generico"): (650, 0.3092),
    (1, 0, 1, "Golpe"): (1742, 0.5235),
    (1, 1, 0, "Generico"): (4177, 0.0642),
    (1, 1, 0, "Golpe"): (8196, 0.1661),
    (1, 1, 1, "Generico"): (9351, 0.0213),
    (1, 1, 1, "Golpe"): (16647, 0.0522),
}

# UF como cluster de 3. Cruzar 26 UFs x 16 segmentos daria 416 células com
# n médio de 144 — fino demais para uma taxa estável.
UF_ALTO = {"AM", "AP", "BA", "GO", "RJ", "RS"}
UF_BAIXO = {"MA", "MS", "MT", "PI", "PR", "RN", "RO", "TO"}

# Ajuste em LOG-ODDS, não multiplicativo. Multiplicar probabilidade quebra nos
# extremos: 0,9888 x 1,15 estouraria 1, e 0,9888 x 0,85 = 0,84 subestimaria
# grosseiramente um segmento onde o banco perde quase sempre. Em log-odds o
# deslocamento é uniforme e a probabilidade nunca sai de (0,1).
# Offsets medidos na base: logit(P(perda) do cluster) - logit(P(perda) global).
OFFSET_UF_LOGIT = {"alto": +0.4362, "medio": -0.0325, "baixo": -0.3252}


def cluster_uf(uf: str) -> str:
    uf = (uf or "").strip().upper()
    if uf in UF_ALTO:
        return "alto"
    if uf in UF_BAIXO:
        return "baixo"
    return "medio"


def chave(contrato: bool, extrato: bool, comprovante: bool, sub_assunto: str) -> str:
    return f"C{int(contrato)} E{int(extrato)} CC{int(comprovante)} {sub_assunto}"


def p_perda(contrato: bool, extrato: bool, comprovante: bool, sub_assunto: str,
            uf: str | None = None) -> float:
    """P(derrota) do segmento, deslocada em log-odds pelo cluster de UF."""
    _, base = TABELA[(int(contrato), int(extrato), int(comprovante), sub_assunto)]
    if not uf:
        return base
    base = min(0.9995, max(0.0005, base))
    z = math.log(base / (1 - base)) + OFFSET_UF_LOGIT[cluster_uf(uf)]
    return 1 / (1 + math.exp(-z))
