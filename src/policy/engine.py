"""Policy entry points: Group 9 PolicyEngine and the segment-based decidir API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

import joblib
import pandas as pd

from contracts.schema import CaseFeatures, PlanoRecuperacao, Recomendacao

from . import table
from .gate import avaliar_gate, contrato_efetivo
from .constants import (
    P1, P3, P4, P5, P6,
    DEFAULT_MODEL_THRESHOLD,
    DOSSIE_STATUS_NAO_CONFORME,
    FEATURE_COLUMNS,
    MODEL_GRAY_ZONE,
    REPO_ROOT,
    SUBSIDIOS_CRITICOS,
    SUBSIDY_FIELD_MAP,
)
from .normalization import cluster_for_uf, coerce_bool, is_golpe_sub_assunto, normalize_dossie_status
from .pricing import PricingResult, calcular_faixa, calculate_agreement_pricing


FIELD_ALIASES = {
    "numero_processo": "case_id",
    "processo_id": "case_id",
    "valor_da_causa": "value_of_claim",
    "sub_assunto": "sub_subject",
    "comprovante_bacen": "comprovante_credito",
    "comprovante_de_credito": "comprovante_credito",
    "demonstrativo_evolucao_divida": "demonstrativo_divida",
    "demonstrativo_evolucao_da_divida": "demonstrativo_divida",
    "laudo": "laudo_referenciado",
    "dossie_presente": "dossie",
}


@dataclass(slots=True)
class CaseData:
    """Normalized case payload consumed by the policy engine."""

    uf: str
    value_of_claim: float | None = None
    case_id: str | None = None
    sub_subject: str | None = None
    contrato: bool = False
    extrato: bool = False
    comprovante_credito: bool = False
    dossie: bool = False
    demonstrativo_divida: bool = False
    laudo_referenciado: bool = False
    dossie_status: str = "AUSENTE"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CaseData":
        normalized: dict[str, Any] = {}
        for key, value in data.items():
            canonical_key = FIELD_ALIASES.get(key, key)
            normalized[canonical_key] = value

        claim_value = normalized.get("value_of_claim")
        if claim_value in (None, ""):
            parsed_claim_value = None
        else:
            parsed_claim_value = float(claim_value)

        return cls(
            uf=str(normalized.get("uf", "")).strip().upper(),
            value_of_claim=parsed_claim_value,
            case_id=normalized.get("case_id"),
            sub_subject=normalized.get("sub_subject"),
            contrato=coerce_bool(normalized.get("contrato")),
            extrato=coerce_bool(normalized.get("extrato")),
            comprovante_credito=coerce_bool(normalized.get("comprovante_credito")),
            dossie=coerce_bool(normalized.get("dossie")),
            demonstrativo_divida=coerce_bool(normalized.get("demonstrativo_divida")),
            laudo_referenciado=coerce_bool(normalized.get("laudo_referenciado")),
            dossie_status=normalize_dossie_status(normalized.get("dossie_status")),
        )

    def to_feature_row(self) -> dict[str, int]:
        """Build the one-row feature payload aligned with training."""
        uf_cluster = cluster_for_uf(self.uf)
        row = {
            "Contrato": int(self.contrato),
            "Extrato": int(self.extrato),
            "Comprovante de crédito": int(self.comprovante_credito),
            "Dossiê": int(self.dossie),
            "Demonstrativo de evolução da dívida": int(self.demonstrativo_divida),
            "Laudo referenciado": int(self.laudo_referenciado),
            "is_golpe": int(is_golpe_sub_assunto(self.sub_subject)),
            "uf_alto": int(uf_cluster == "ALTO"),
            "uf_medio": int(uf_cluster == "MEDIO"),
        }
        return {column: row[column] for column in FEATURE_COLUMNS}


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Auditable decision object returned by the policy engine."""

    case_id: str | None
    recommendation: str
    source: str
    decision_code: str
    confidence_label: str
    confidence_score: float
    agreement_probability: float | None
    model_threshold: float | None
    gray_zone: bool
    critical_subsidy_count: int
    critical_subsidies_present: tuple[str, ...]
    critical_subsidies_missing: tuple[str, ...]
    uf: str
    uf_cluster: str
    dossie_status: str
    is_golpe: bool
    feature_vector: dict[str, int]
    reasons: tuple[str, ...]
    pricing: PricingResult | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class PolicyEngine:
    """Rule engine with a calibrated XGBoost fallback for borderline cases."""

    def __init__(
        self,
        *,
        model_path: str | Path | None = None,
        model: Any | None = None,
        threshold: float = DEFAULT_MODEL_THRESHOLD,
    ) -> None:
        self.threshold = float(threshold)
        self.model_path = Path(model_path) if model_path else REPO_ROOT / "artefatos" / "modelo_xgboost.pkl"
        self._model = model

    def evaluate(self, case_data: CaseData | Mapping[str, Any]) -> PolicyDecision:
        case = case_data if isinstance(case_data, CaseData) else CaseData.from_mapping(case_data)

        decision = self._evaluate_rules(case)
        if decision is None:
            decision = self._evaluate_model(case)

        if decision.recommendation == "ACORDO":
            if case.value_of_claim is None or case.value_of_claim <= 0:
                reasons = decision.reasons + (
                    "Valor da causa ausente ou inválido; a faixa financeira do acordo não foi calculada.",
                )
                decision = replace(decision, reasons=reasons)
            else:
                pricing = calculate_agreement_pricing(
                    case.value_of_claim,
                    decision.critical_subsidy_count,
                    dossie_status=case.dossie_status,
                    uf=case.uf,
                )
                decision = replace(decision, pricing=pricing)

        return decision

    def _evaluate_rules(self, case: CaseData) -> PolicyDecision | None:
        uf_cluster = cluster_for_uf(case.uf)
        feature_row = case.to_feature_row()
        is_golpe = bool(feature_row["is_golpe"])
        critical_present = self._critical_subsidies_present(case)
        critical_missing = self._critical_subsidies_missing(case)
        critical_count = len(critical_present)

        base_kwargs = {
            "case_id": case.case_id,
            "critical_subsidy_count": critical_count,
            "critical_subsidies_present": critical_present,
            "critical_subsidies_missing": critical_missing,
            "uf": case.uf,
            "uf_cluster": uf_cluster,
            "dossie_status": case.dossie_status,
            "is_golpe": is_golpe,
            "feature_vector": feature_row,
        }

        if case.dossie_status == DOSSIE_STATUS_NAO_CONFORME:
            return PolicyDecision(
                recommendation="ACORDO",
                source="RULE",
                decision_code="DOSSIE_NAO_CONFORME",
                confidence_label="ALTA",
                confidence_score=1.0,
                agreement_probability=None,
                model_threshold=None,
                gray_zone=False,
                reasons=(
                    "Dossiê marcado como não conforme; a política determina acordo imediato.",
                    "A recomendação não depende do modelo nesse cenário.",
                ),
                **base_kwargs,
            )

        if critical_count <= 1:
            return PolicyDecision(
                recommendation="ACORDO",
                source="RULE",
                decision_code="CRITICOS_INSUFICIENTES",
                confidence_label="ALTA",
                confidence_score=1.0,
                agreement_probability=None,
                model_threshold=None,
                gray_zone=False,
                reasons=(
                    f"Apenas {critical_count} subsídio(s) crítico(s) presente(s): {', '.join(critical_present) or 'nenhum'}.",
                    "Com 0 ou 1 subsídio crítico, a política recomenda acordo.",
                ),
                **base_kwargs,
            )

        if uf_cluster == "ALTO" and critical_count <= 2:
            return PolicyDecision(
                recommendation="ACORDO",
                source="RULE",
                decision_code="UF_ALTO_RISCO",
                confidence_label="ALTA",
                confidence_score=1.0,
                agreement_probability=None,
                model_threshold=None,
                gray_zone=False,
                reasons=(
                    f"UF {case.uf} está no cluster de alto risco histórico.",
                    "Com até 2 subsídios críticos em UF de alto risco, a política força acordo.",
                ),
                **base_kwargs,
            )

        if critical_count >= 3:
            return PolicyDecision(
                recommendation="DEFESA",
                source="RULE",
                decision_code="PROVA_CRITICA_COMPLETA",
                confidence_label="ALTA",
                confidence_score=1.0,
                agreement_probability=None,
                model_threshold=None,
                gray_zone=False,
                reasons=(
                    "Os 3 subsídios críticos estão presentes.",
                    "Nessa configuração probatória, a política prioriza defesa.",
                ),
                **base_kwargs,
            )

        return None

    def _evaluate_model(self, case: CaseData) -> PolicyDecision:
        feature_row = case.to_feature_row()
        frame = pd.DataFrame([feature_row], columns=list(FEATURE_COLUMNS))
        probability = float(self._load_model().predict_proba(frame)[0][1])
        recommendation = "ACORDO" if probability >= self.threshold else "DEFESA"
        gray_zone = MODEL_GRAY_ZONE[0] <= probability <= MODEL_GRAY_ZONE[1]
        confidence_score = round(abs(probability - 0.5) * 2, 4)
        confidence_label = self._confidence_label(confidence_score, gray_zone)

        critical_present = self._critical_subsidies_present(case)
        critical_missing = self._critical_subsidies_missing(case)

        reasons = [
            "Caso caiu na zona intermediária da política e foi encaminhado para o modelo.",
            f"Probabilidade estimada de acordo: {probability:.1%}.",
            f"Threshold aplicado para decisão: {self.threshold:.0%}.",
        ]
        if gray_zone:
            reasons.append("A probabilidade está na zona cinzenta de 35% a 65%; revisar com atenção.")

        return PolicyDecision(
            case_id=case.case_id,
            recommendation=recommendation,
            source="MODEL",
            decision_code="MODELO_CALIBRADO",
            confidence_label=confidence_label,
            confidence_score=confidence_score,
            agreement_probability=round(probability, 4),
            model_threshold=self.threshold,
            gray_zone=gray_zone,
            critical_subsidy_count=len(critical_present),
            critical_subsidies_present=critical_present,
            critical_subsidies_missing=critical_missing,
            uf=case.uf,
            uf_cluster=cluster_for_uf(case.uf),
            dossie_status=case.dossie_status,
            is_golpe=bool(feature_row["is_golpe"]),
            feature_vector=feature_row,
            reasons=tuple(reasons),
        )

    def _load_model(self) -> Any:
        if self._model is None:
            if not self.model_path.exists():
                raise FileNotFoundError(
                    f"Modelo não encontrado em '{self.model_path}'. "
                    "Treine ou aponte outro arquivo via model_path."
                )
            self._model = joblib.load(self.model_path)
        return self._model

    @staticmethod
    def _critical_subsidies_present(case: CaseData) -> tuple[str, ...]:
        present = []
        for subsidy_name in SUBSIDIOS_CRITICOS:
            field_name = SUBSIDY_FIELD_MAP[subsidy_name]
            if getattr(case, field_name):
                present.append(subsidy_name)
        return tuple(present)

    @staticmethod
    def _critical_subsidies_missing(case: CaseData) -> tuple[str, ...]:
        missing = []
        for subsidy_name in SUBSIDIOS_CRITICOS:
            field_name = SUBSIDY_FIELD_MAP[subsidy_name]
            if not getattr(case, field_name):
                missing.append(subsidy_name)
        return tuple(missing)

    @staticmethod
    def _confidence_label(confidence_score: float, gray_zone: bool) -> str:
        if gray_zone:
            return "BAIXA"
        if confidence_score >= 0.60:
            return "ALTA"
        if confidence_score >= 0.30:
            return "MEDIA"
        return "BAIXA"


def evaluate_case(
    case_data: CaseData | Mapping[str, Any],
    *,
    model_path: str | Path | None = None,
    model: Any | None = None,
    threshold: float = DEFAULT_MODEL_THRESHOLD,
) -> PolicyDecision:
    """Convenience helper for one-off evaluations."""
    engine = PolicyEngine(model_path=model_path, model=model, threshold=threshold)
    return engine.evaluate(case_data)


def custo_esperado_defesa(valor_causa: float, p_perda: float) -> float:
    """P(derrota) x quanto se paga ao perder (P1) x valor da causa, + sucumbência (P6)."""
    return p_perda * P1.valor * valor_causa * (1 + P6.valor)


def _p_perda(c: CaseFeatures, *, com_contrato: bool | None = None,
             com_extrato: bool | None = None) -> float:
    return table.p_perda(
        contrato=contrato_efetivo(c) if com_contrato is None else com_contrato,
        extrato=c.extrato if com_extrato is None else com_extrato,
        comprovante=c.comprovante_credito,
        sub_assunto=c.sub_assunto,
        uf=c.uf,
    )


def _plano_recuperacao(c: CaseFeatures, p_atual: float) -> PlanoRecuperacao | None:
    """
    A TERCEIRA VIA.

    Dossiê que periciou assinatura em contrato => o contrato existiu.
    Laudo que descreve liberação de crédito    => o extrato daquela conta existiu.
    São 17.194 casos na base (28,7%), concentrando 69,7% da exposição.

    Só o item 'analisou_assinatura_contrato' autoriza confiança alta: um dossiê
    que validou apenas RG e liveness não prova que o contrato existe.
    """
    if not c.contrato and c.dossie:
        forte = bool(c.analise_dossie and c.analise_dossie.analisou_assinatura_contrato)
        doc, conf = "contrato", ("alta" if forte else "media")
        fund = ("O dossiê periciou a assinatura aposta no instrumento contratual: "
                "o contrato existe e não foi juntado." if forte else
                "Dossiê presente; confirmar se periciou assinatura em contrato.")
        novo = _p_perda(c, com_contrato=True)
    elif not c.extrato and c.laudo:
        doc, conf = "extrato", "media"
        fund = "O laudo descreve a liberação do crédito em conta: o extrato daquela conta existe."
        novo = _p_perda(c, com_extrato=True)
    elif not contrato_efetivo(c) or not c.extrato:
        doc = "contrato" if not contrato_efetivo(c) else "extrato"
        conf, fund = "baixa", "Documento ausente, sem sinal interno de que exista."
        novo = _p_perda(c, com_contrato=True) if doc == "contrato" else _p_perda(c, com_extrato=True)
    else:
        return None

    prob = P4.valor if conf == "alta" else P5.valor
    ganho = (custo_esperado_defesa(c.valor_causa, p_atual)
             - custo_esperado_defesa(c.valor_causa, novo)) * prob
    return PlanoRecuperacao(documento=doc, confianca=conf, fundamento=fund,
                            ganho_estimado=round(ganho, 2), p_perda_se_recuperado=round(novo, 4))


def decidir(c: CaseFeatures) -> Recomendacao:
    gate = avaliar_gate(c)
    p = _p_perda(c)
    custo_defesa = custo_esperado_defesa(c.valor_causa, p)

    nao_conforme = bool(c.analise_dossie and c.analise_dossie.veredito == "nao_conforme")
    faixa = calcular_faixa(c.valor_causa, p, c.uf, nao_conforme)
    rec = _plano_recuperacao(c, p)

    # se aceitar, paga o alvo; se recusar, o caso volta para a defesa
    custo_acordo = P3.valor * faixa.alvo + (1 - P3.valor) * custo_defesa

    segmento = table.chave(contrato_efetivo(c), c.extrato, c.comprovante_credito, c.sub_assunto)
    just = [gate.motivo, f"Segmento {segmento}: P(derrota) {p:.1%}."]
    premissas = [P1.id, P6.id, P3.id]
    alertas = [gate.alerta] if gate.alerta else []

    if rec and rec.confianca == "alta" and rec.ganho_estimado > 0:
        acao = "RECUPERAR"
        just.append(f"{rec.fundamento} Ganho esperado R$ {rec.ganho_estimado:,.2f}.")
        premissas.append(P4.id)
    elif custo_acordo < custo_defesa:
        acao = "ACORDAR"
        just.append(f"Custo esperado: acordo R$ {custo_acordo:,.2f} vs defesa R$ {custo_defesa:,.2f}.")
    else:
        acao = "DEFENDER"
        just.append(f"Defesa é o caminho mais barato: R$ {custo_defesa:,.2f} vs acordo R$ {custo_acordo:,.2f}.")
        if not gate.defesa_disponivel:
            alertas.append("Gate fechado: defender aqui exige justificativa registrada.")

    if c.contradicoes:
        just.extend(c.contradicoes)

    return Recomendacao(
        numero_processo=c.numero_processo, acao=acao,
        gate_defesa_disponivel=gate.defesa_disponivel, gate_motivo=gate.motivo,
        segmento=segmento, p_perda=round(p, 4), custo_esperado_defesa=round(custo_defesa, 2),
        acordo=faixa if acao == "ACORDAR" else None,
        recuperacao=rec if acao == "RECUPERAR" else None,
        justificativa=just, alertas=alertas, premissas_usadas=premissas,
    )
