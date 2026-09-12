"""Shared constants for the settlement policy modules."""

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

SUBSIDIOS = (
    "Contrato",
    "Extrato",
    "Comprovante de crédito",
    "Dossiê",
    "Demonstrativo de evolução da dívida",
    "Laudo referenciado",
)

SUBSIDIOS_CRITICOS = (
    "Contrato",
    "Extrato",
    "Comprovante de crédito",
)

SUBSIDY_FIELD_MAP = {
    "Contrato": "contrato",
    "Extrato": "extrato",
    "Comprovante de crédito": "comprovante_credito",
    "Dossiê": "dossie",
    "Demonstrativo de evolução da dívida": "demonstrativo_divida",
    "Laudo referenciado": "laudo_referenciado",
}

HIGH_RISK_UFS = frozenset({"AM", "AP"})
MEDIUM_RISK_UFS = frozenset({
    "GO",
    "RS",
    "BA",
    "RJ",
    "ES",
    "DF",
    "AL",
    "SP",
    "PE",
})

CLUSTER_UF = {
    **{uf: "ALTO" for uf in HIGH_RISK_UFS},
    **{uf: "MEDIO" for uf in MEDIUM_RISK_UFS},
}

DEFAULT_UF_CLUSTER = "BAIXO"

FEATURE_COLUMNS = (
    *SUBSIDIOS,
    "is_golpe",
    "uf_alto",
    "uf_medio",
)

DOSSIE_STATUS_CONFORME = "CONFORME"
DOSSIE_STATUS_NAO_CONFORME = "NAO_CONFORME"
DOSSIE_STATUS_AUSENTE = "AUSENTE"
DOSSIE_STATUS_INCOMPLETO = "INCOMPLETO"

VALID_DOSSIE_STATUSES = frozenset(
    {
        DOSSIE_STATUS_CONFORME,
        DOSSIE_STATUS_NAO_CONFORME,
        DOSSIE_STATUS_AUSENTE,
        DOSSIE_STATUS_INCOMPLETO,
    }
)

DEFAULT_MODEL_THRESHOLD = 0.50
MODEL_GRAY_ZONE = (0.35, 0.65)

BASE_AGREEMENT_FACTOR = 0.30
OPENING_FLOOR_FACTOR = 0.24
HISTORICAL_MAX_ACCEPTABLE_FACTOR = 0.35
ABSOLUTE_AGREEMENT_CEILING_FACTOR = 0.40


@dataclass(frozen=True)
class Premissa:
    id: str
    descricao: str
    valor: float
    fonte: str


P1 = Premissa("P1", "E[condenação | derrota] como fração do valor da causa", 0.72,
              "DERIVADO: 2/3 x 0,63 (parcial) + 1/3 x 0,90 (procedência), base 60k")
P2_ALVO = Premissa("P2", "Fator alvo do acordo", 0.30,
                   "OBSERVADO: mediana dos 280 acordos reais (média 0,298)")
P2_PISO = Premissa("P2a", "Piso da banda de acordo", 0.24, "OBSERVADO: P25 dos 280 acordos")
P2_TETO = Premissa("P2b", "Teto da banda de acordo", 0.40, "OBSERVADO: P90 dos 280 acordos")
P3 = Premissa("P3", "Probabilidade de o autor aceitar o acordo", 0.40,
              "ASSUMIDO: sem dado de recusa na base. Parametrizável (slider 0,2-0,8)")
P4 = Premissa("P4", "Recuperabilidade com sinal forte (dossiê/laudo presente)", 0.70,
              "EVIDÊNCIA POSITIVA: 17.194 casos em que o documento comprovadamente existiu")
P5 = Premissa("P5", "Recuperabilidade sem sinal forte", 0.25, "ASSUMIDO")
P6 = Premissa("P6", "Honorários sucumbenciais sobre a condenação", 0.15,
              "ASSUMIDO: praxe 10-20%, art. 85 CPC")
# P7 (custo do escritório externo por processo) NÃO é assumido de propósito.
# O banco tem esse número; inventá-lo distorce toda a política.

TODAS = [P1, P2_ALVO, P2_PISO, P2_TETO, P3, P4, P5, P6]

GATE_P_VITORIA_OBSERVADA = 0.027  # C0/E0: 2,7% de vitória em 6.493 casos
