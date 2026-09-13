"""
Monta o caso a partir das evidências documentais e aplica a política.

Único caminho da API até a decisão: documentos confirmados viram as flags de
presença, a análise de dossiê concluída vira `AnaliseDossie`, e tudo passa por
`src.policy.engine.decidir`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from contracts.schema import AnaliseDossie, CaseFeatures, ParametrosContrato, Recomendacao
from src.policy.engine import decidir
from src.interface.backend.repository import Repository
from src.interface.backend.schemas import DocumentaryStatus, DocumentStatus, DocumentTypeStatus

TYPE_TO_FEATURE = {
    "CONTRATO": "contrato",
    "EXTRATO": "extrato",
    "COMPROVANTE_CREDITO": "comprovante_credito",
    "DOSSIE": "dossie",
    "DEMONSTRATIVO_DIVIDA": "demonstrativo",
    "LAUDO_REFERENCIADO": "laudo",
}
# Nomes de coluna da base histórica: mantidos no feature_vector para auditoria.
FEATURE_LABELS = {
    "contrato": "Contrato",
    "extrato": "Extrato",
    "comprovante_credito": "Comprovante de crédito",
    "dossie": "Dossiê",
    "demonstrativo": "Demonstrativo de evolução da dívida",
    "laudo": "Laudo referenciado",
}
ACAO_PARA_API = {"ACORDAR": "ACORDO", "DEFENDER": "DEFESA", "RECUPERAR": "RECUPERAR"}
USABLE_TYPE = {DocumentTypeStatus.CONFIRMED.value, DocumentTypeStatus.USER_CONFIRMED.value}
USABLE_STATUS = {DocumentStatus.COMPLETED.value, DocumentStatus.COMPLETED_WITH_WARNINGS.value}

# (bank_id, law_firm_id) -> contrato vigente. O escritório vem do advogado atribuído ao caso.
ContractProvider = Callable[[str | None, str | None], ParametrosContrato]


def _contrato_padrao(_bank_id: str | None, _law_firm_id: str | None = None) -> ParametrosContrato:
    return ParametrosContrato()


class PolicyService:
    def __init__(self, repository: Repository, model_path: str | None = None,
                 contract_provider: ContractProvider | None = None) -> None:
        # model_path fica aceito por compatibilidade com quem ainda o passa;
        # a política por segmentos não carrega modelo.
        self.repository = repository
        self.contract_provider = contract_provider or _contrato_padrao

    def evaluate(self, case_id: str) -> dict:
        case = self.repository.get_case(case_id)
        if case is None:
            raise LookupError("Processo não encontrado.")
        documents = self.repository.list_documents(case_id)
        features, provenance = self._build_features(case, documents)
        contrato = self.contract_provider(case.get("bank_id"), self._law_firm_of(case))
        recomendacao = decidir(features, contrato, fator_aceite=self._fator_aceite(case.get("bank_id")))
        documentary_status, limitations = self._documentary_status(documents, features)
        record = {
            "id": str(uuid4()),
            "case_id": case_id,
            "recommendation": ACAO_PARA_API[recomendacao.acao],
            "decision_code": self._decision_code(recomendacao),
            "policy_source": "TABELA_SEGMENTOS" if recomendacao.fonte_probabilidade == "tabela" else "FONTE_EXTERNA",
            "agreement_probability": None,
            "documentary_status": documentary_status.value,
            "reasons": recomendacao.justificativa,
            "feature_vector": {
                **{FEATURE_LABELS[k]: int(getattr(features, k)) for k in FEATURE_LABELS},
                "is_golpe": int(features.sub_assunto == "Golpe"),
            },
            "feature_provenance": provenance,
            "pricing": self._pricing(recomendacao),
            "limitations": [*limitations, *recomendacao.alertas],
            "policy_output": recomendacao.model_dump(mode="json"),
            "policy_version": recomendacao.versao_politica,
            "contract_version": recomendacao.versao_contrato,
            "created_at": datetime.now(UTC).isoformat(),
        }
        return self.repository.create_analysis(record)

    def _fator_aceite(self, bank_id: str | None) -> float:
        """Corrige a curva de aceite pela aceitação observada na operação (a partir de 10 respostas)."""
        from src.policy.referencia import chance_aceite

        respostas = self.repository.observed_acceptance(bank_id) if bank_id else []
        if len(respostas) < 10:
            return 1.0
        esperada = sum(chance_aceite(oferta, causa) for oferta, causa, _ in respostas) / len(respostas)
        observada = sum(aceito for *_, aceito in respostas) / len(respostas)
        return min(1.5, max(0.5, observada / esperada)) if esperada else 1.0

    def _law_firm_of(self, case: dict) -> str | None:
        lawyer = self.repository.get_user(case["assigned_lawyer_id"]) if case.get("assigned_lawyer_id") else None
        return lawyer.get("law_firm_id") if lawyer else None

    def _build_features(self, case: dict, documents: list[dict]) -> tuple[CaseFeatures, list[dict]]:
        flags = {feature: False for feature in TYPE_TO_FEATURE.values()}
        evidence: dict[str, list[str]] = {feature: [] for feature in TYPE_TO_FEATURE.values()}
        for document in documents:
            feature = TYPE_TO_FEATURE.get(document["declared_type"])
            if feature and document["status"] in USABLE_STATUS and document["type_status"] in USABLE_TYPE:
                flags[feature] = True
                evidence[feature].append(document["id"])

        analise, dossie_document_id = self._analise_dossie(case, documents)
        features = CaseFeatures(
            numero_processo=case["case_number"],
            uf=case["uf"],
            sub_assunto="Golpe" if "golpe" in (case.get("sub_subject") or "").lower() else "Generico",
            valor_causa=float(case.get("value_of_claim") or 0.0),
            analise_dossie=analise,
            **flags,
        )
        provenance = [
            {"feature": FEATURE_LABELS[feature], "value": int(flags[feature]), "document_ids": evidence[feature],
             "derivation_rule": "tipo declarado confirmado ou confirmado pelo usuário; extração concluída"}
            for feature in FEATURE_LABELS
        ]
        if analise is not None:
            provenance.append({
                "feature": "Análise do dossiê", "value": int(analise.analisou_assinatura_contrato),
                "document_ids": [dossie_document_id] if dossie_document_id else [],
                "derivation_rule": f"veredito {analise.veredito}; 1 = periciou a assinatura do contrato",
            })
        return features, provenance

    def _analise_dossie(self, case: dict, documents: list[dict]) -> tuple[AnaliseDossie | None, str | None]:
        from src.utils.dossie_service import DossieService

        usable = {d["id"]: d for d in documents
                  if d["declared_type"] == "DOSSIE" and d["type_status"] in USABLE_TYPE and d["status"] in USABLE_STATUS}
        for summary in self.repository.list_current_dossie_summaries(case["id"]):
            document = usable.get(summary["document_id"])
            if summary["status"] != "COMPLETED" or document is None:
                continue
            record = DossieService.apply_document_context(summary, document)
            if record.get("result"):
                return AnaliseDossie.model_validate(record["result"]["analise"]), document["id"]
        if (case.get("dossie_status") or "").upper() == "NAO_CONFORME":
            return AnaliseDossie(veredito="nao_conforme", analisou_assinatura_contrato=False), None
        return None, None

    @staticmethod
    def _decision_code(r: Recomendacao) -> str:
        if r.acao == "RECUPERAR":
            return "RECUPERAR_DOCUMENTO"
        if r.acao == "ACORDAR":
            return "ACORDO_GATE_FECHADO" if not r.gate_defesa_disponivel else "ACORDO_MAIS_BARATO"
        return "DEFESA_COM_JUSTIFICATIVA" if not r.gate_defesa_disponivel else "DEFESA_MAIS_BARATA"

    @staticmethod
    def _pricing(r: Recomendacao) -> dict | None:
        if r.acordo is None:
            return None
        return {
            "opening_value": r.acordo.abertura,
            "target_value": r.acordo.alvo,
            "walk_away_value": r.acordo.walk_away,
            "negotiable": r.acordo.negociavel,
            "expected_defense_cost": r.custo_esperado_defesa,
            "savings_at_target": r.economia_no_alvo,
            "loss_probability": r.p_perda,
            "indifference_probability": r.p_estrela,
            "recommended_value": r.valor_recomendado,
            "acceptance_chance": r.chance_aceite,
            "market_low": r.faixa_mercado[0] if r.faixa_mercado else None,
            "market_high": r.faixa_mercado[1] if r.faixa_mercado else None,
            "similar_cases_cost": r.custo_parecidos,
            "similar_cases_n": r.parecidos_n,
        }

    @staticmethod
    def _documentary_status(documents: list[dict], features: CaseFeatures) -> tuple[DocumentaryStatus, list[str]]:
        if not documents:
            return DocumentaryStatus.INFORMACAO_INSUFICIENTE, ["Nenhum documento foi enviado para o processo."]
        statuses = {document["status"] for document in documents}
        type_statuses = {document["type_status"] for document in documents}
        if DocumentTypeStatus.MISMATCH.value in type_statuses:
            return DocumentaryStatus.CONFIRMACAO_NECESSARIA, [
                "Há documento com tipo declarado incompatível com evidências determinísticas; confirme antes de usar.",
            ]
        if statuses <= {DocumentStatus.FAILED.value}:
            return DocumentaryStatus.FALHA_TECNICA, ["Não foi possível extrair texto dos documentos enviados."]
        if statuses & {DocumentStatus.UPLOADED.value, DocumentStatus.EXTRACTING.value}:
            return DocumentaryStatus.ANALISE_PRELIMINAR, ["A extração documental ainda está em andamento."]
        limitations = []
        if features.dossie and features.analise_dossie is None:
            limitations.append("Dossiê presente sem análise concluída: a recomendação não usa o conteúdo dele.")
        if DocumentTypeStatus.UNCONFIRMED.value in type_statuses:
            limitations.append("Há documento não confirmado, que não ativou nenhuma variável da política.")
        if any(document["quality_flags"] for document in documents):
            limitations.append("Métrica de qualidade de OCR permanece pendente; páginas com pouco texto foram sinalizadas.")
        usable = any(document["type_status"] in USABLE_TYPE for document in documents)
        if not usable:
            return DocumentaryStatus.INFORMACAO_INSUFICIENTE, limitations
        return DocumentaryStatus.SUSTENTADA_COM_RESSALVAS, limitations
