from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from contracts.dossie import DossieEvidence, DossieReport
from contracts.schema import AnaliseDossie
from src.interface.backend.config import Settings
from src.interface.backend.database import connection_for, initialize_database
from src.interface.backend.main import create_app
from src.interface.backend.schemas import CaseCreate, DocumentType, DocumentTypeStatus, SourceParty
from src.tools.dossie_analyzer import ANALYZER_VERSION, DossieConfigurationError, DossieLimitError, DossieProviderError


def _report() -> DossieReport:
    return DossieReport(
        docie_existe=True,
        analise=AnaliseDossie(veredito="inconclusivo", analisou_assinatura_contrato=False),
        evidencias=[], avisos=[], paginas_processadas=1, trechos_processados=1, completo=True,
    )


class RecordingAnalyzer:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def analyze_pages(self, pages) -> DossieReport:
        self.calls.append(list(pages))
        return _report()


@pytest.fixture
def application(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path, database_path=tmp_path / "test.db",
        document_dir=tmp_path / "documents",
        artifact_dir=Path(__file__).parents[1] / "artefatos", max_upload_bytes=1024 * 1024,
        auth_required=False,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.dossie.analyzer = RecordingAnalyzer()
        yield app, client


def _document(app, *, declared_type=DocumentType.DOSSIE, type_status=DocumentTypeStatus.CONFIRMED,
              status="COMPLETED", text="Dossiê com verificação documental.", sha256=None) -> dict:
    repository = app.state.repository
    case = repository.create_case(CaseCreate(case_number=str(uuid4()), uf="SP", value_of_claim=1000))
    document = repository.create_document(
        case_id=case["id"], original_filename="dossie.txt", file_path=Path("unused.txt"),
        declared_type=declared_type, source_party=SourceParty.BANCO,
        sha256=sha256 or str(uuid4()), request_id=None,
    )
    repository.append_document_pages(document["id"], [{
        "page_number": 1, "text_content": text, "extraction_method": "TEXT", "quality_flags": [],
    }])
    repository.update_document_extraction(
        document["id"], status=status, page_count=1, pages_extracted=1,
        quality_flags=[], detected_type=declared_type, type_status=type_status,
    )
    return repository.get_document(document["id"])


def test_analyze_caches_persists_and_does_not_change_policy(application) -> None:
    app, client = application
    document = _document(app)
    endpoint = f"/api/documents/{document['id']}/dossie-analysis"
    assert client.get(endpoint).status_code == 404
    initial_policy = client.post(f"/api/cases/{document['case_id']}/analyses").json()
    response = client.post(endpoint)
    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["result"]["analise"]["veredito"] == "inconclusivo"
    assert client.post(endpoint).json()["id"] == response.json()["id"]
    assert client.get(endpoint).json() == response.json()
    assert len(app.state.dossie.analyzer.calls) == 1
    detail = client.get(f"/api/cases/{document['case_id']}").json()
    assert detail["dossie_analyses"] == [{**response.json(), "evidencias_carregadas": False}]
    assert detail["case"]["dossie_status"] == "AUSENTE"
    final_policy = client.post(f"/api/cases/{document['case_id']}/analyses").json()
    for key in ("recommendation", "decision_code", "feature_vector"):
        assert final_policy[key] == initial_policy[key]
    assert final_policy["feature_vector"]["Contrato"] == 0


@pytest.mark.parametrize("declared_type,type_status,status", [
    (DocumentType.CONTRATO, DocumentTypeStatus.CONFIRMED, "COMPLETED"),
    (DocumentType.DOSSIE, DocumentTypeStatus.REMOVED, "COMPLETED"),
    (DocumentType.DOSSIE, DocumentTypeStatus.MISMATCH, "COMPLETED"),
    (DocumentType.DOSSIE, DocumentTypeStatus.PENDING, "COMPLETED"),
    (DocumentType.DOSSIE, DocumentTypeStatus.CONFIRMED, "UPLOADED"),
    (DocumentType.DOSSIE, DocumentTypeStatus.CONFIRMED, "EXTRACTING"),
    (DocumentType.DOSSIE, DocumentTypeStatus.CONFIRMED, "FAILED"),
])
def test_ineligible_documents_never_call_provider(application, declared_type, type_status, status) -> None:
    app, client = application
    document = _document(app, declared_type=declared_type, type_status=type_status, status=status)
    assert client.post(f"/api/documents/{document['id']}/dossie-analysis").status_code == 409
    assert app.state.dossie.analyzer.calls == []


def test_unknown_document_returns_not_found(application) -> None:
    app, client = application
    assert client.post("/api/documents/missing/dossie-analysis").status_code == 404
    assert client.get("/api/documents/missing/dossie-analysis").status_code == 404
    assert app.state.dossie.analyzer.calls == []


@pytest.mark.parametrize("type_status", [DocumentTypeStatus.UNCONFIRMED, DocumentTypeStatus.USER_CONFIRMED])
def test_unconfirmed_documents_are_allowed_with_visible_reservation(application, type_status) -> None:
    app, client = application
    document = _document(app, type_status=type_status)
    result = client.post(f"/api/documents/{document['id']}/dossie-analysis")
    assert result.status_code == 201
    assert result.json()["result"]["avisos"]


@pytest.mark.parametrize("exception,error_code", [
    (DossieConfigurationError, "CONFIGURATION_ERROR"), (DossieProviderError, "PROVIDER_ERROR"),
    (DossieLimitError, "INPUT_LIMIT_EXCEEDED"),
])
def test_failures_are_recorded_without_sensitive_provider_messages(application, exception, error_code) -> None:
    app, client = application
    document = _document(app)
    secret = "sk-secret-key CPF-document-prompt"

    class FailingAnalyzer:
        def analyze_pages(self, pages):
            raise exception(secret)

    app.state.dossie.analyzer = FailingAnalyzer()
    endpoint = f"/api/documents/{document['id']}/dossie-analysis"
    response = client.post(endpoint)
    assert response.status_code == 503
    assert secret not in response.text
    failure = client.get(endpoint).json()
    assert failure["status"] == "FAILED"
    assert failure["error_code"] == error_code
    assert failure["result"] is None
    assert secret not in json.dumps(failure)
    summary = client.get(f"/api/cases/{document['case_id']}").json()["dossie_analyses"][0]
    assert summary["result"] is None
    assert summary["evidencias_total"] == 0
    assert summary["evidencias_carregadas"] is False
    with connection_for(app.state.repository.database_path) as connection:
        rows = connection.execute("SELECT * FROM dossie_analyses").fetchall()
    assert secret not in repr([dict(row) for row in rows])
    app.state.dossie.analyzer = RecordingAnalyzer()
    assert client.post(endpoint).status_code == 201
    assert client.get(endpoint).json()["status"] == "COMPLETED"


def test_document_pages_and_cache_never_cross_document_ids(application) -> None:
    app, client = application
    first = _document(app, text="First dossier", sha256="same-content-hash")
    second = _document(app, text="Second dossier", sha256="same-content-hash")
    for document in (first, second):
        result = client.post(f"/api/documents/{document['id']}/dossie-analysis")
        assert result.status_code == 201
        assert result.json()["document_id"] == document["id"]
    assert [pages[0]["text_content"] for pages in app.state.dossie.analyzer.calls] == [
        "First dossier", "Second dossier",
    ]
    detail = client.get(f"/api/cases/{first['case_id']}").json()
    assert len(detail["dossie_analyses"]) == 1
    assert detail["dossie_analyses"][0]["document_id"] == first["id"]


def test_removed_document_cannot_use_cache_but_keeps_history(application) -> None:
    app, client = application
    document = _document(app)
    endpoint = f"/api/documents/{document['id']}/dossie-analysis"
    saved = client.post(endpoint).json()
    client.post(f"/api/documents/{document['id']}/type-confirmation", json={
        "action": "REMOVE", "reason": "Arquivo removido pelo usuário.",
    })
    assert client.post(endpoint).status_code == 409
    assert client.get(endpoint).json()["id"] == saved["id"]
    assert client.get(f"/api/cases/{document['case_id']}").json()["dossie_analyses"] == []
    assert len(app.state.dossie.analyzer.calls) == 1


def test_failure_does_not_hide_prior_success(application) -> None:
    app, client = application
    document = _document(app)
    endpoint = f"/api/documents/{document['id']}/dossie-analysis"
    saved = client.post(endpoint).json()
    app.state.repository.create_dossie_analysis(
        document=document, model="other-model", analyzer_version=ANALYZER_VERSION,
        error_code="PROVIDER_ERROR",
    )
    assert client.get(endpoint).json()["id"] == saved["id"]
    assert len(client.get(f"/api/cases/{document['case_id']}").json()["dossie_analyses"]) == 1
    assert len(app.state.repository.list_dossie_analyses(document["case_id"])) == 2


def test_document_changed_during_provider_call_does_not_save_success(application) -> None:
    app, client = application
    document = _document(app)

    class RemovingAnalyzer:
        def analyze_pages(self, pages):
            list(pages)
            app.state.repository.update_document_type(
                document["id"], declared_type=DocumentType.DOSSIE,
                detected_type=DocumentType.DOSSIE, type_status=DocumentTypeStatus.REMOVED,
            )
            return _report()

    app.state.dossie.analyzer = RemovingAnalyzer()
    endpoint = f"/api/documents/{document['id']}/dossie-analysis"
    assert client.post(endpoint).status_code == 409
    assert client.get(endpoint).status_code == 404


def test_missing_final_pages_prevent_a_complete_report(application) -> None:
    app, client = application
    document = _document(app)
    with connection_for(app.state.repository.database_path) as connection:
        connection.execute("UPDATE documents SET page_count = 2 WHERE id = ?", (document["id"],))
    response = client.post(f"/api/documents/{document['id']}/dossie-analysis")
    assert response.status_code == 201
    result = response.json()["result"]
    assert result["completo"] is False
    assert result["analise"]["veredito"] == "inconclusivo"
    assert any("arquivo completo" in warning for warning in result["avisos"])


def test_cached_reports_reapply_document_context_without_persisting_dynamic_warnings(application) -> None:
    app, client = application
    document = _document(app, type_status=DocumentTypeStatus.UNCONFIRMED)

    class WarningAnalyzer(RecordingAnalyzer):
        def analyze_pages(self, pages):
            return super().analyze_pages(pages).model_copy(update={"avisos": ["Aviso original do extrator."]})

    app.state.dossie.analyzer = WarningAnalyzer()
    endpoint = f"/api/documents/{document['id']}/dossie-analysis"
    initial = client.post(endpoint).json()
    assert any("não foi confirmado" in warning for warning in initial["result"]["avisos"])
    client.post(f"/api/documents/{document['id']}/type-confirmation", json={
        "action": "CONTINUE_WITH_RESERVATION", "reason": "Usuário aceita a ressalva documental.",
    })
    refreshed = client.post(endpoint).json()
    assert refreshed["id"] == initial["id"]
    warnings = refreshed["result"]["avisos"]
    assert "Aviso original do extrator." in warnings
    assert not any("não foi confirmado" in warning for warning in warnings)
    assert any("confirmado pelo usuário" in warning for warning in warnings)
    assert client.get(endpoint).json() == refreshed
    summary = client.get(f"/api/cases/{document['case_id']}").json()["dossie_analyses"][0]
    assert summary["result"]["avisos"] == warnings
    with connection_for(app.state.repository.database_path) as connection:
        connection.execute("UPDATE documents SET page_count = 2 WHERE id = ?", (document["id"],))
    assert client.get(endpoint).json()["result"]["completo"] is False
    assert client.post(endpoint).json()["result"]["completo"] is False
    with connection_for(app.state.repository.database_path) as connection:
        connection.execute("UPDATE documents SET page_count = 1, type_status = 'CONFIRMED' WHERE id = ?", (document["id"],))
    restored = client.get(endpoint).json()
    assert restored["result"]["completo"] is True
    assert restored["result"]["avisos"] == ["Aviso original do extrator."]
    persisted = app.state.repository.get_dossie_analysis(document["id"])
    assert persisted["result"]["avisos"] == ["Aviso original do extrator."]
    assert persisted["result"]["completo"] is True
    assert len(app.state.dossie.analyzer.calls) == 1


def test_case_summary_omits_citations_and_full_endpoint_keeps_them(application) -> None:
    app, client = application
    document = _document(app)

    class EvidenceAnalyzer(RecordingAnalyzer):
        def analyze_pages(self, pages):
            return super().analyze_pages(pages).model_copy(update={"evidencias": [
                DossieEvidence(campo="veredito", valor="inconclusivo", pagina=1,
                               trecho="Dossiê com verificação documental."),
                DossieEvidence(campo="analisou_assinatura_contrato", valor="false", pagina=1,
                               trecho="A assinatura contratual não foi analisada."),
            ]})

    app.state.dossie.analyzer = EvidenceAnalyzer()
    endpoint = f"/api/documents/{document['id']}/dossie-analysis"
    full = client.post(endpoint).json()
    assert full["evidencias_total"] == 2
    assert full["evidencias_carregadas"] is True
    assert len(full["result"]["evidencias"]) == 2
    app.state.repository.create_dossie_analysis(
        document=document, model="other-model", analyzer_version=ANALYZER_VERSION,
        error_code="PROVIDER_ERROR",
    )
    detail = client.get(f"/api/cases/{document['case_id']}").json()
    assert len(detail["dossie_analyses"]) == 1
    summary = detail["dossie_analyses"][0]
    assert summary["id"] == full["id"]
    assert summary["evidencias_total"] == 2
    assert summary["evidencias_carregadas"] is False
    assert summary["result"]["evidencias"] == []
    assert client.get(endpoint).json() == full
    assert client.post(endpoint).json() == full
    assert len(app.state.dossie.analyzer.calls) == 1
    assert len(app.state.repository.list_dossie_analyses(document["case_id"])) == 2


def test_page_batches_release_connection_before_consumer_work(application) -> None:
    app, _ = application
    document = _document(app)
    repository = app.state.repository
    repository.append_document_pages(document["id"], [
        {"page_number": number, "text_content": str(number), "extraction_method": "TEXT", "quality_flags": []}
        for number in range(2, 70)
    ])
    generator = repository.iter_document_pages(document["id"], batch_size=3)
    assert next(generator)["page_number"] == 1
    with connection_for(repository.database_path) as connection:
        connection.execute("BEGIN EXCLUSIVE")
        connection.execute("UPDATE cases SET uf = 'RJ' WHERE id = ?", (document["case_id"],))
    assert [page["page_number"] for page in generator] == list(range(2, 70))


def test_concurrent_calls_use_one_provider_request_and_release_claim(application) -> None:
    app, client = application
    document = _document(app)
    entered = Event()
    proceed = Event()

    class BlockingAnalyzer:
        def analyze_pages(self, pages):
            list(pages)
            entered.set()
            assert proceed.wait(timeout=10)
            return _report()

    app.state.dossie.analyzer = BlockingAnalyzer()
    endpoint = f"/api/documents/{document['id']}/dossie-analysis"
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(client.post, endpoint)
        try:
            assert entered.wait(timeout=10)
            assert client.post(endpoint).status_code == 409
        finally:
            proceed.set()
        assert running.result(timeout=10).status_code == 201
    assert client.post(endpoint).status_code == 201
    with connection_for(app.state.repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM dossie_analysis_claims").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM dossie_analyses").fetchone()[0] == 1


def test_expired_claim_can_be_retried(application) -> None:
    app, client = application
    document = _document(app)
    repository = app.state.repository
    repository.claim_dossie_analysis(document, app.state.dossie.model, ANALYZER_VERSION, -1)
    assert client.post(f"/api/documents/{document['id']}/dossie-analysis").status_code == 201


def test_legacy_database_adds_dossier_tables_idempotently(application) -> None:
    app, _ = application
    document = _document(app)
    path = app.state.repository.database_path
    with connection_for(path) as connection:
        connection.execute("DROP TABLE dossie_analyses")
        connection.execute("DROP TABLE dossie_analysis_claims")
    initialize_database(path)
    initialize_database(path)
    assert app.state.repository.get_document(document["id"]) is not None
    assert app.state.repository.get_dossie_analysis(document["id"]) is None
    with connection_for(path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


class ConformingAnalyzer:
    def analyze_pages(self, pages) -> DossieReport:
        list(pages)
        return DossieReport(
            docie_existe=True,
            analise=AnaliseDossie(veredito="conforme", analisou_assinatura_contrato=True,
                                  numero_contrato_referenciado="603827451"),
            evidencias=[], avisos=[], paginas_processadas=1, trechos_processados=1, completo=True,
            assinatura_contrato_status="sim",
        )


def _document_in_case(app, case_id: str, declared_type: DocumentType, text: str) -> dict:
    repository = app.state.repository
    document = repository.create_document(
        case_id=case_id, original_filename=f"{declared_type.value.lower()}.txt", file_path=Path("unused.txt"),
        declared_type=declared_type, source_party=SourceParty.BANCO, sha256=str(uuid4()), request_id=None,
    )
    repository.append_document_pages(document["id"], [{
        "page_number": 1, "text_content": text, "extraction_method": "TEXT", "quality_flags": [],
    }])
    repository.update_document_extraction(
        document["id"], status="COMPLETED", page_count=1, pages_extracted=1,
        quality_flags=[], detected_type=declared_type, type_status=DocumentTypeStatus.CONFIRMED,
    )
    return repository.get_document(document["id"])


def test_dossier_that_examined_the_contract_signature_turns_settlement_into_recovery(application) -> None:
    """A análise do dossiê alimenta a política: o contrato existe, e recuperá-lo vence acordar."""
    app, client = application
    app.state.dossie.analyzer = ConformingAnalyzer()
    case = app.state.repository.create_case(
        CaseCreate(case_number=str(uuid4()), uf="AM", value_of_claim=15000, sub_subject="Golpe"))
    _document_in_case(app, case["id"], DocumentType.EXTRATO, "Extrato bancário com crédito em conta.")
    _document_in_case(app, case["id"], DocumentType.COMPROVANTE_CREDITO, "Comprovante de crédito BACEN.")
    dossie = _document_in_case(app, case["id"], DocumentType.DOSSIE, "Dossiê com perícia da assinatura do contrato.")

    before = client.post(f"/api/cases/{case['id']}/analyses").json()
    assert before["recommendation"] == "ACORDO"
    assert any("sem análise concluída" in item for item in before["limitations"])

    assert client.post(f"/api/documents/{dossie['id']}/dossie-analysis").status_code == 201
    after = client.post(f"/api/cases/{case['id']}/analyses").json()
    assert after["recommendation"] == "RECUPERAR"
    assert after["decision_code"] == "RECUPERAR_DOCUMENTO"
    assert after["policy_output"]["recuperacao"]["documento"] == "contrato"
    assert after["pricing"]["target_value"] > 0, "a faixa fica disponível para o caso de o documento não vir"
    assert any(item["feature"] == "Análise do dossiê" for item in after["feature_provenance"])

    decision = client.post(f"/api/cases/{case['id']}/lawyer-decisions?analysis_id={after['id']}",
                           json={"action": "RECUPERAR"})
    assert decision.status_code == 201
    assert client.get("/api/monitoring").json()["adherence_rate"] == 1.0


def _upload_dossier(client, case_id: str):
    return client.post(
        f"/api/cases/{case_id}/documents",
        data={"declared_type": "DOSSIE", "source_party": "BANCO"},
        files={"file": ("dossie.txt", "Dossiê de validação documental. Parecer grafotécnico da assinatura.", "text/plain")},
    )


def test_dossier_is_analyzed_automatically_when_extraction_finishes(application, monkeypatch) -> None:
    app, client = application
    monkeypatch.setenv("OPENAI_API_KEY", "chave-de-teste-sem-rede")
    app.state.dossie.analyzer = ConformingAnalyzer()
    case = app.state.repository.create_case(CaseCreate(case_number=str(uuid4()), uf="AM", value_of_claim=15000))
    assert _upload_dossier(client, case["id"]).status_code == 201
    analyses = client.get(f"/api/cases/{case['id']}").json()["dossie_analyses"]
    assert len(analyses) == 1 and analyses[0]["status"] == "COMPLETED"


def test_without_openai_key_the_dossier_waits_for_manual_analysis(application, monkeypatch) -> None:
    app, client = application
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app.state.dossie.analyzer = ConformingAnalyzer()
    case = app.state.repository.create_case(CaseCreate(case_number=str(uuid4()), uf="AM", value_of_claim=15000))
    assert _upload_dossier(client, case["id"]).status_code == 201
    assert client.get(f"/api/cases/{case['id']}").json()["dossie_analyses"] == []
