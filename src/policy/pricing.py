"""Agreement pricing helpers derived from the written settlement policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .constants import (
    ABSOLUTE_AGREEMENT_CEILING_FACTOR,
    BASE_AGREEMENT_FACTOR,
    DOSSIE_STATUS_NAO_CONFORME,
    HISTORICAL_MAX_ACCEPTABLE_FACTOR,
    OPENING_FLOOR_FACTOR,
)
from .normalization import cluster_for_uf, normalize_dossie_status


@dataclass(frozen=True, slots=True)
class PricingAdjustment:
    key: str
    label: str
    delta_factor: float


@dataclass(frozen=True, slots=True)
class PricingResult:
    value_of_claim: float
    uf_cluster: str
    dossie_status: str
    critical_subsidy_count: int
    base_factor: float
    target_factor: float
    opening_factor: float
    max_acceptable_factor: float
    absolute_ceiling_factor: float
    opening_value: float
    target_value: float
    max_acceptable_value: float
    absolute_ceiling_value: float
    adjustments: tuple[PricingAdjustment, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _round_money(value: float) -> float:
    return round(value, 2)


def calculate_agreement_pricing(
    value_of_claim: float,
    critical_subsidy_count: int,
    *,
    dossie_status: object = None,
    uf: object = None,
) -> PricingResult:
    """
    Compute the settlement range for a case recommended to ACORDO.

    The target factor starts at 30% of the claim value and receives the
    adjustments described in the policy document. The opening offer and the
    negotiation ceiling are derived from that target in a way that preserves
    the historical corridor described by the team.
    """
    if value_of_claim <= 0:
        raise ValueError("value_of_claim must be greater than zero.")

    subsidy_count = int(critical_subsidy_count)
    if subsidy_count < 0:
        raise ValueError("critical_subsidy_count cannot be negative.")

    normalized_dossie_status = normalize_dossie_status(dossie_status)
    uf_cluster = cluster_for_uf(uf)

    adjustments: list[PricingAdjustment] = []

    if subsidy_count >= 3:
        adjustments.append(
            PricingAdjustment(
                key="forte_probatorio",
                label="Banco com 3 subsídios críticos presentes",
                delta_factor=-0.03,
            )
        )
    elif subsidy_count <= 1:
        adjustments.append(
            PricingAdjustment(
                key="fragilidade_probatoria",
                label="Banco com 0 ou 1 subsídio crítico",
                delta_factor=0.03,
            )
        )

    if normalized_dossie_status == DOSSIE_STATUS_NAO_CONFORME:
        adjustments.append(
            PricingAdjustment(
                key="dossie_nao_conforme",
                label="Dossiê não conforme",
                delta_factor=0.05,
            )
        )

    if uf_cluster == "ALTO":
        adjustments.append(
            PricingAdjustment(
                key="uf_alto_risco",
                label="UF no cluster de alto risco",
                delta_factor=0.02,
            )
        )
    elif uf_cluster == "BAIXO":
        adjustments.append(
            PricingAdjustment(
                key="uf_baixo_risco",
                label="UF no cluster de baixo risco",
                delta_factor=-0.02,
            )
        )

    target_factor = BASE_AGREEMENT_FACTOR + sum(item.delta_factor for item in adjustments)
    target_factor = _clamp(
        target_factor,
        OPENING_FLOOR_FACTOR,
        ABSOLUTE_AGREEMENT_CEILING_FACTOR,
    )

    opening_factor = _clamp(
        target_factor - 0.04,
        OPENING_FLOOR_FACTOR,
        target_factor,
    )
    max_acceptable_factor = _clamp(
        max(target_factor, HISTORICAL_MAX_ACCEPTABLE_FACTOR),
        target_factor,
        ABSOLUTE_AGREEMENT_CEILING_FACTOR,
    )
    absolute_ceiling_factor = ABSOLUTE_AGREEMENT_CEILING_FACTOR

    return PricingResult(
        value_of_claim=_round_money(value_of_claim),
        uf_cluster=uf_cluster,
        dossie_status=normalized_dossie_status,
        critical_subsidy_count=subsidy_count,
        base_factor=BASE_AGREEMENT_FACTOR,
        target_factor=round(target_factor, 4),
        opening_factor=round(opening_factor, 4),
        max_acceptable_factor=round(max_acceptable_factor, 4),
        absolute_ceiling_factor=absolute_ceiling_factor,
        opening_value=_round_money(value_of_claim * opening_factor),
        target_value=_round_money(value_of_claim * target_factor),
        max_acceptable_value=_round_money(value_of_claim * max_acceptable_factor),
        absolute_ceiling_value=_round_money(value_of_claim * absolute_ceiling_factor),
        adjustments=tuple(adjustments),
    )
