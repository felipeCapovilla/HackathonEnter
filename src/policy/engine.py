"""Policy entry points: Group 9 PolicyEngine and the segment-based decidir API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

import joblib
import pandas as pd

from contracts.schema import CaseFeatures, ParametrosContrato, PlanoRecuperacao, Recomendacao, VereditoAcordo

from . import table
from .gate import avaliar_gate, contrato_efetivo
from .constants import (
    P4, P5, RATIO_CONDENACAO, CUSTO_MENSAL_TEMPO, DURACAO_MESES, POLICY_VERSION,
    DEFAULT_MODEL_THRESHOLD,
    DOSSIE_STATUS_NAO_CONFORME,
    FEATURE_COLUMNS,
    MODEL_GRAY_ZONE,
    REPO_ROOT,
    SUBSIDIOS_CRITICOS,
    SUBSIDY_FIELD_MAP,
)
from .normalization import cluster_for_uf, coerce_bool, is_golpe_sub_assunto, normalize_dossie_status
from .pricing import PricingResult, calculate_agreement_pricing
from .valor_acordo import avaliar_acordo


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


# ─── decidir(): a política por segmentos ──────────────────────────────────────
#
#     gate (a defesa é possível?) -> probabilidade (tabela ou fonte externa)
#       -> preço (valor_acordo.avaliar_acordo) -> recuperar o documento compensa?
#
# ÚNICO ponto de decisão da política. O PolicyEngine acima é legado e sai.


def _p_tabela(c: CaseFeatures, *, com_contrato: bool | None = None,
              com_extrato: bool | None = None) -> float:
    return table.p_perda(
        contrato=contrato_efetivo(c) if com_contrato is None else com_contrato,
        extrato=c.extrato if com_extrato is None else com_extrato,
        comprovante=c.comprovante_credito,
        sub_assunto=c.sub_assunto,
        uf=c.uf,
    )


def _avaliar(valor_causa: float, p: float, contrato: ParametrosContrato) -> VereditoAcordo:
    condenacao = RATIO_CONDENACAO.valor * valor_causa
    return avaliar_acordo(
        valor_causa, p,
        fator_tempo=contrato.fator_tempo,
        honorario_perda=contrato.honorario_defesa_perdida.em_reais(valor_causa, condenacao),
        honorario_ganho=contrato.honorario_defesa_ganha.em_reais(valor_causa, condenacao),
        honorario_acordo=contrato.honorario_acordo.em_reais(valor_causa, condenacao),
        teto_alcada=contrato.teto_alcada_fator * valor_causa if contrato.teto_alcada_fator else None,
    )


def _custo_do_melhor_caminho(v: VereditoAcordo, valor_causa: float, contrato: ParametrosContrato) -> float:
    """Custo esperado da melhor opção disponível: defender, ou acordar na abertura."""
    if v.faixa is None:
        return v.custo_defesa
    condenacao = RATIO_CONDENACAO.valor * valor_causa
    return v.faixa.abertura + contrato.honorario_acordo.em_reais(valor_causa, condenacao)


def _plano_recuperacao(c: CaseFeatures, valor_causa: float, contrato: ParametrosContrato,
                       custo_atual: float) -> PlanoRecuperacao | None:
    """
    A TERCEIRA VIA — só quando o documento muda a melhor opção.

    Dossiê que periciou assinatura em contrato => o contrato existiu.
    Laudo que descreve liberação de crédito    => o extrato daquela conta existiu.

    O ganho compara a melhor opção HOJE com a melhor opção se o documento vier.
    Recuperar só o contrato num caso também sem extrato raramente compensa:
    a defesa continua mais cara que acordar, e o banco acordaria de qualquer jeito.
    """
    if not c.contrato and c.dossie:
        forte = bool(c.analise_dossie and c.analise_dossie.analisou_assinatura_contrato)
        doc, conf = "contrato", ("alta" if forte else "media")
        fund = ("O dossiê periciou a assinatura aposta no instrumento contratual: "
                "o contrato existe e não foi juntado." if forte else
                "Dossiê presente; confirmar se periciou assinatura em contrato.")
        p_novo = _p_tabela(c, com_contrato=True)
    elif not c.extrato and c.laudo:
        doc, conf = "extrato", "media"
        fund = "O laudo descreve a liberação do crédito em conta: o extrato daquela conta existe."
        p_novo = _p_tabela(c, com_extrato=True)
    elif not c.extrato:
        doc, conf, fund = "extrato", "baixa", "Extrato ausente, sem sinal interno de que exista."
        p_novo = _p_tabela(c, com_extrato=True)
    elif not c.contrato:
        doc, conf, fund = "contrato", "baixa", "Contrato ausente, sem sinal interno de que exista."
        p_novo = _p_tabela(c, com_contrato=True)
    else:
        return None

    custo_novo = _custo_do_melhor_caminho(_avaliar(valor_causa, p_novo, contrato), valor_causa, contrato)
    prob = P4.valor if conf == "alta" else P5.valor
    ganho = prob * (custo_atual - custo_novo)
    if ganho <= 0:
        return None
    return PlanoRecuperacao(documento=doc, confianca=conf, fundamento=fund,
                            ganho_estimado=round(ganho, 2), p_perda_se_recuperado=round(p_novo, 4))


def decidir(c: CaseFeatures, contrato: ParametrosContrato | None = None, *,
            p_perda: float | None = None) -> Recomendacao:
    """
    Recomendação para um caso.

    `contrato` traz os termos do contrato vigente banco–escritório (honorários
    por desfecho, alçada, custo do tempo); sem ele valem os defaults.
    `p_perda` substitui a tabela de segmentos por uma fonte externa (um modelo),
    mantendo gate, preço e terceira via.
    """
    contrato = contrato or ParametrosContrato()
    gate = avaliar_gate(c)
    externa = p_perda is not None
    p = p_perda if externa else _p_tabela(c)
    alertas = [gate.alerta] if gate.alerta else []

    valor_informado = c.valor_causa > 0
    valor_causa = c.valor_causa if valor_informado else 1.0
    if not valor_informado:
        alertas.append("Valor da causa ausente: decisão calculada em proporção, sem valor de acordo sugerido.")

    veredito = _avaliar(valor_causa, p, contrato)
    rec = _plano_recuperacao(c, valor_causa, contrato, _custo_do_melhor_caminho(veredito, valor_causa, contrato))

    segmento = table.chave(contrato_efetivo(c), c.extrato, c.comprovante_credito, c.sub_assunto)
    fonte = "fonte externa" if externa else "tabela de segmentos"
    just = [gate.motivo,
            f"Segmento {segmento}: P(derrota) {p:.1%} ({fonte}); limiar deste caso {veredito.p_estrela:.1%}."]
    premissas = [*veredito.premissas_usadas, CUSTO_MENSAL_TEMPO.id, DURACAO_MESES.id]

    if rec and rec.confianca == "alta":
        acao = "RECUPERAR"
        just.append(f"{rec.fundamento} Ganho esperado de R$ {rec.ganho_estimado:,.2f} sobre a melhor opção atual.")
        just.append(f"Se o documento não vier: {veredito.motivo}")
        premissas.append(P4.id)
    elif veredito.decisao == "ACORDO":
        acao = "ACORDAR"
        just.append(veredito.motivo)
    else:
        acao = "DEFENDER"
        just.append(veredito.motivo)
        if not gate.defesa_disponivel:
            alertas.append("Gate fechado: defender aqui exige justificativa registrada.")
    if rec and rec.confianca != "alta":
        premissas.append(P5.id)

    just.extend(c.contradicoes)

    return Recomendacao(
        numero_processo=c.numero_processo, acao=acao,
        gate_defesa_disponivel=gate.defesa_disponivel, gate_motivo=gate.motivo,
        segmento=segmento, p_perda=round(p, 4), fonte_probabilidade="externa" if externa else "tabela",
        p_estrela=veredito.p_estrela, custo_esperado_defesa=veredito.custo_defesa,
        acordo=veredito.faixa if valor_informado else None,
        economia_no_alvo=veredito.economia_no_alvo if valor_informado else 0.0,
        recuperacao=rec,
        justificativa=just, alertas=alertas, premissas_usadas=list(dict.fromkeys(premissas)),
        versao_politica=f"{POLICY_VERSION}+{table._ARTEFATO['versao']}",
        versao_contrato=contrato.versao,
    )
