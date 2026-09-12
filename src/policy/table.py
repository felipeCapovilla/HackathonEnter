"""
MODELO 1 - Probabilidade de derrota.

Tabela glass-box de 16 segmentos, medida na base de 60k. Substitui modelo de
ML de propósito: nos dados, gradient boosting agrega ~+0,014 de AUC sobre
contar os 3 documentos críticos, e custa a auditabilidade por advogado.

Chave: (contrato, extrato, comprovante_credito, sub_assunto)
"""
from __future__ import annotations

import math

from .artefato import carregar

# Números medidos na base e gravados por scripts/gerar_tabela_politica.py.
# Nada aqui é digitado à mão: regenerar o artefato recalibra a política.
_ARTEFATO = carregar()

# (contrato, extrato, comprovante) x sub_assunto -> (n, p_perda)
TABELA: dict[tuple[int, int, int, str], tuple[int, float]] = {
    (s["contrato"], s["extrato"], s["comprovante"], s["sub_assunto"]): (s["n"], s["p_perda"])
    for s in _ARTEFATO["segmentos"]
}

# UF como grupo de 3 pela taxa histórica de derrota.
CLUSTER_POR_UF: dict[str, str] = _ARTEFATO["uf"]["clusters"]
UF_ALTO = {uf for uf, grupo in CLUSTER_POR_UF.items() if grupo == "alto"}
UF_BAIXO = {uf for uf, grupo in CLUSTER_POR_UF.items() if grupo == "baixo"}

# Ajuste em LOG-ODDS, não multiplicativo. Multiplicar probabilidade quebra nos
# extremos: 0,9888 x 1,15 estouraria 1, e 0,9888 x 0,85 = 0,84 subestimaria
# grosseiramente um segmento onde o banco perde quase sempre. Em log-odds o
# deslocamento é uniforme e a probabilidade nunca sai de (0,1).
# Offsets: logit(P(perda) do grupo) - logit(P(perda) global).
OFFSET_UF_LOGIT: dict[str, float] = _ARTEFATO["uf"]["offset_logit"]


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
