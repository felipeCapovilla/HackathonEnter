"""Compose validated documentary evidence with the Group 9 policy engine."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from src.policy.engine import PolicyEngine

from src.interface.backend.repository import Repository
from src.interface.backend.schemas import DocumentaryStatus, DocumentStatus, DocumentTypeStatus


TYPE_TO_FEATURE = {
    "CONTRATO": "contrato",
    "EXTRATO": "extrato",
    "COMPROVANTE_CREDITO": "comprovante_credito",
    "DOSSIE": "dossie",
    "DEMONSTRATIVO_DIVIDA": "demonstrativo_divida",
    "LAUDO_REFERENCIADO": "laudo_referenciado",
}


class PolicyService:
    def __init__(self, repository: Repository, model_path: str) -> None:
        self.repository = repository
        self.engine = PolicyEngine(model_path=model_path)

    def evaluate(self, case_id: str) -> dict:
        case = self.repository.get_case(case_id)
        if case is None:
            raise LookupError("Processo não encontrado.")
        documents = self.repository.list_documents(case_id)
        input_data, provenance = self._build_policy_input(case, documents)
        decision = self.engine.evaluate(input_data)
        documentary_status, limitations = self._documentary_status(documents)
        pricing = asdict(decision.pricing) if decision.pricing else None
        record = {
            "id": str(uuid4()),
            "case_id": case_id,
            "recommendation": decision.recommendation,
            "decision_code": decision.decision_code,
            "policy_source": decision.source,
            "agreement_probability": decision.agreement_probability,
            "documentary_status": documentary_status.value,
            "reasons": list(decision.reasons),
            "feature_vector": decision.feature_vector,
            "feature_provenance": provenance,
            "pricing": pricing,
            "limitations": limitations,
            "created_at": datetime.now(UTC).isoformat(),
        }
        return self.repository.create_analysis(record)

    @staticmethod
    def _build_policy_input(case: dict, documents: list[dict]) -> tuple[dict, list[dict]]:
        input_data = {
            "case_id": case["case_number"],
            "uf": case["uf"],
            "value_of_claim": case["value_of_claim"],
            "sub_subject": case["sub_subject"],
            "dossie_status": case["dossie_status"],
            **{feature: False for feature in TYPE_TO_FEATURE.values()},
        }
        evidence: dict[str, list[str]] = {feature: [] for feature in TYPE_TO_FEATURE.values()}
        for document in documents:
            feature = TYPE_TO_FEATURE.get(document["declared_type"])
            is_usable = (
                feature is not None
                and document["status"] in {DocumentStatus.COMPLETED.value, DocumentStatus.COMPLETED_WITH_WARNINGS.value}
                and document["type_status"]
                in {DocumentTypeStatus.CONFIRMED.value, DocumentTypeStatus.USER_CONFIRMED.value}
            )
            if is_usable:
                input_data[feature] = True
                evidence[feature].append(document["id"])
        provenance = [
            {
                "feature": feature,
                "value": int(input_data[feature]),
                "document_ids": evidence[feature],
                "derivation_rule": "tipo declarado confirmado ou confirmado pelo usuário; extração concluída",
            }
            for feature in TYPE_TO_FEATURE.values()
        ]
        return input_data, provenance

    @staticmethod
    def _documentary_status(documents: list[dict]) -> tuple[DocumentaryStatus, list[str]]:
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
        limitations = [
            "Esta recomendação usa tipo e extração; a análise auxiliar de dossiê por LLM é consultada separadamente e não altera a política automaticamente.",
        ]
        if DocumentTypeStatus.UNCONFIRMED.value in type_statuses:
            limitations.append("Há documento não confirmado, que não ativou nenhuma variável da política.")
        if any(document["quality_flags"] for document in documents):
            limitations.append("Métrica de qualidade de OCR permanece pendente; páginas com pouco texto foram sinalizadas.")
        usable = any(
            document["type_status"] in {DocumentTypeStatus.CONFIRMED.value, DocumentTypeStatus.USER_CONFIRMED.value}
            for document in documents
        )
        if not usable:
            return DocumentaryStatus.INFORMACAO_INSUFICIENTE, limitations
        return DocumentaryStatus.SUSTENTADA_COM_RESSALVAS, limitations
