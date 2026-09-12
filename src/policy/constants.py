"""Shared constants for the settlement policy modules."""

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
