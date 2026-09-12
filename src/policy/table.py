"""
MODELO 1 - Probabilidade de derrota.

Tabela glass-box de 16 segmentos, medida na base de 60k. Substitui modelo de
ML de propósito: nos dados, gradient boosting agrega ~+0,014 de AUC sobre
contar os 3 documentos críticos, e custa a auditabilidade por advogado.

Chave: (contrato, extrato, comprovante_credito, sub_assunto)
"""
from __future__ import annotations

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

# UF como cluster de 3 (26 UFs x 16 segmentos = 416 células, n medio 144: fino demais)
UF_ALTO = {"AM", "AP", "BA", "GO", "RJ", "RS"}
UF_BAIXO = {"MA", "MS", "MT", "PI", "PR", "RN", "RO", "TO"}
AJUSTE_UF = {"alto": 1.15, "medio": 1.00, "baixo": 0.85}


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
    """P(derrota) do segmento, com ajuste multiplicativo pelo cluster de UF."""
    _, base = TABELA[(int(contrato), int(extrato), int(comprovante), sub_assunto)]
    if uf:
        base *= AJUSTE_UF[cluster_uf(uf)]
    return min(0.99, max(0.01, base))
