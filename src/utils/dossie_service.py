"""On-demand dossier extraction, independent from settlement decisions."""

from __future__ import annotations

import os

from src.interface.backend.repository import Repository
from src.interface.backend.schemas import DossieAnalysisRecord
from src.tools.dossie_analyzer import (
    ANALYZER_VERSION,
    DossieAnalyzer,
    DossieConfigurationError,
    DossieLimitError,
    DossieProviderError,
)


class DossieUnavailableError(RuntimeError):
    pass


class DossieService:
    def __init__(self, repository: Repository, analyzer: DossieAnalyzer | None = None) -> None:
        self.repository = repository
        self.model = os.getenv("ENTERAGREE_DOSSIE_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        self.max_chunks = int(os.getenv("ENTERAGREE_DOSSIE_MAX_CHUNKS", "128"))
        self.max_chunk_chars = int(os.getenv("ENTERAGREE_DOSSIE_MAX_CHUNK_CHARS", "12000"))
        self.analyzer = analyzer or DossieAnalyzer(
            model=self.model, max_chunks=self.max_chunks, max_chunk_chars=self.max_chunk_chars,
        )

    def analyze(self, document_id: str) -> dict:
        document = self.repository.get_document_internal(document_id)
        if document is None:
            raise LookupError("Documento não encontrado.")
        self._validate_document(document)
        cached = self.repository.get_cached_dossie_analysis(
            document_id, document["sha256"], self.model, ANALYZER_VERSION
        )
        if cached is not None:
            return self.apply_document_context(cached, document)
        token = self.repository.claim_dossie_analysis(
            document, self.model, ANALYZER_VERSION, timeout_seconds=self.max_chunks * 100 + 300,
        )
        if token is None:
            raise ValueError("Uma análise deste dossiê já está em andamento. Aguarde e atualize a página.")
        try:
            cached = self.repository.get_cached_dossie_analysis(
                document_id, document["sha256"], self.model, ANALYZER_VERSION,
            )
            record = cached if cached is not None else self._analyze_document(document)
            return self.apply_document_context(record, document)
        finally:
            self.repository.release_dossie_analysis(token)

    def get(self, document_id: str) -> dict:
        document = self.repository.get_document(document_id)
        if document is None:
            raise LookupError("Documento não encontrado.")
        record = self.repository.get_dossie_analysis(document_id)
        if record is None:
            raise LookupError("Este documento ainda não possui análise de dossiê.")
        return self.apply_document_context(record, document)

    def summaries(self, case_id: str, documents: list[dict]) -> list[dict]:
        by_id = {document["id"]: document for document in documents}
        return [
            self.apply_document_context(record, by_id[record["document_id"]])
            for record in self.repository.list_current_dossie_summaries(case_id)
            if record["document_id"] in by_id
        ]

    def _analyze_document(self, document: dict) -> dict:
        try:
            report = self.analyzer.analyze_pages(self.repository.iter_document_pages(document["id"]))
        except (DossieConfigurationError, DossieProviderError, DossieLimitError) as exc:
            error_code = {
                DossieConfigurationError: "CONFIGURATION_ERROR",
                DossieProviderError: "PROVIDER_ERROR",
                DossieLimitError: "INPUT_LIMIT_EXCEEDED",
            }.get(type(exc), "PROVIDER_ERROR")
            self.repository.create_dossie_analysis(
                document=document, model=self.model, analyzer_version=ANALYZER_VERSION,
                error_code=error_code,
            )
            raise DossieUnavailableError(
                "Análise indisponível. Consulte a configuração e os limites do serviço e tente novamente."
            ) from None
        report = report.model_copy(update={"docie_existe": True})
        return self.repository.create_dossie_analysis(
            document=document, model=self.model, analyzer_version=ANALYZER_VERSION,
            result=report.model_dump(mode="json"),
        )

    @staticmethod
    def apply_document_context(record: dict, document: dict) -> dict:
        analysis = DossieAnalysisRecord.model_validate(record)
        report = analysis.result
        if report is None:
            return analysis.model_dump(mode="json")
        warnings = list(report.avisos)
        if document["type_status"] == "UNCONFIRMED":
            warnings.append("O tipo documental não foi confirmado pelo validador determinístico.")
        elif document["type_status"] == "USER_CONFIRMED":
            warnings.append("O tipo documental foi confirmado pelo usuário com ressalvas.")
        if document["status"] == "COMPLETED_WITH_WARNINGS":
            warnings.append("A extração documental terminou com ressalvas; consulte a qualidade das páginas.")
        unavailable = (
            document["declared_type"] != "DOSSIE"
            or document["type_status"] in {"REMOVED", "MISMATCH", "PENDING"}
            or document["status"] not in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}
        )
        if unavailable:
            warnings.append("Este relatório é histórico; o estado atual do documento não permite uma análise ativa de dossiê.")
        if report.paginas_processadas < document["page_count"]:
            warnings.append("Há páginas do documento sem extração disponível; a análise não cobre o arquivo completo.")
        if unavailable or report.paginas_processadas < document["page_count"]:
            report = report.model_copy(update={
                "completo": False,
                "analise": report.analise.model_copy(update={
                    "veredito": "inconclusivo", "analisou_assinatura_contrato": False,
                }),
            })
        report = report.model_copy(update={"avisos": list(dict.fromkeys(warnings)), "docie_existe": True})
        return analysis.model_copy(update={
            "result": report,
            "evidencias_total": len(report.evidencias) if analysis.evidencias_carregadas else analysis.evidencias_total,
        }).model_dump(mode="json")

    @staticmethod
    def _validate_document(document: dict) -> None:
        if document["declared_type"] != "DOSSIE":
            raise ValueError("A análise requer um documento declarado como dossiê.")
        if document["type_status"] in {"REMOVED", "MISMATCH", "PENDING"}:
            raise ValueError("O documento foi removido ou aguarda confirmação do tipo documental.")
        if document["status"] not in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}:
            raise ValueError("A extração do documento precisa estar concluída antes da análise.")
