"""Normalization helpers shared by the policy modules."""

from __future__ import annotations

import unicodedata

from .constants import (
    CLUSTER_UF,
    DEFAULT_UF_CLUSTER,
    DOSSIE_STATUS_AUSENTE,
    DOSSIE_STATUS_CONFORME,
    DOSSIE_STATUS_INCOMPLETO,
    DOSSIE_STATUS_NAO_CONFORME,
)


TRUE_VALUES = frozenset({"1", "true", "t", "sim", "s", "yes", "y", "on", "presente"})
FALSE_VALUES = frozenset({"0", "false", "f", "nao", "n", "no", "off", "ausente", ""})


def normalize_token(value: object) -> str:
    """Normalize free-form text into a comparable uppercase token."""
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("-", " ").replace("_", " ")
    return " ".join(text.upper().split())


def normalize_uf(value: object) -> str:
    """Normalize UF to the two-letter canonical form when possible."""
    token = normalize_token(value)
    return token[:2]


def cluster_for_uf(value: object) -> str:
    """Map an UF into the cluster used by the trained model."""
    return CLUSTER_UF.get(normalize_uf(value), DEFAULT_UF_CLUSTER)


def normalize_dossie_status(value: object) -> str:
    """Normalize user input into a supported dossie status."""
    token = normalize_token(value)
    aliases = {
        "": DOSSIE_STATUS_AUSENTE,
        "CONFORME": DOSSIE_STATUS_CONFORME,
        "NAO CONFORME": DOSSIE_STATUS_NAO_CONFORME,
        "NAO CONFORME IMEDIATO": DOSSIE_STATUS_NAO_CONFORME,
        "AUSENTE": DOSSIE_STATUS_AUSENTE,
        "INCOMPLETO": DOSSIE_STATUS_INCOMPLETO,
    }
    return aliases.get(token, DOSSIE_STATUS_AUSENTE)


def is_golpe_sub_assunto(value: object) -> bool:
    """Return True when the sub-assunto is the 'Golpe' class used in training."""
    return normalize_token(value) == "GOLPE"


def coerce_bool(value: object) -> bool:
    """Coerce the common frontend payload types into booleans."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)

    token = normalize_token(value).lower()
    if token in TRUE_VALUES:
        return True
    if token in FALSE_VALUES:
        return False

    return bool(token)
