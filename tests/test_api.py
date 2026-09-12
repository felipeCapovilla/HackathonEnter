from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from src.interface.backend.config import Settings
from src.interface.backend.main import create_app


def _settings(tmp_path: Path) -> Settings:
    runtime = tmp_path / "runtime"
    return Settings(
        runtime_dir=runtime,
        database_path=runtime / "enteragree.db",
        document_dir=runtime / "documents",
        artifact_dir=Path(__file__).parents[1] / "artefatos",
        max_upload_bytes=1024 * 1024,
        auth_required=False,
    )


def _create_case(client: TestClient) -> str:
    response = client.post(
        "/api/cases",
        json={"case_number": "0000001-00.2026.8.26.0001", "uf": "SP", "value_of_claim": 1000},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_upload_confirms_type_and_creates_auditable_analysis(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        upload = client.post(
            f"/api/cases/{case_id}/documents",
            data={"declared_type": "CONTRATO", "source_party": "BANCO"},
            files={"file": ("contrato.txt", "Cédula de crédito. Contrato de empréstimo. Assinatura.", "text/plain")},
        )
        assert upload.status_code == 201

        detail = client.get(f"/api/cases/{case_id}").json()
        assert detail["documents"][0]["type_status"] == "CONFIRMED"
        assert detail["documents"][0]["status"] == "COMPLETED"

        analysis = client.post(f"/api/cases/{case_id}/analyses")
        assert analysis.status_code == 201
        result = analysis.json()
        assert result["recommendation"] == "ACORDO"
        assert result["decision_code"] == "ACORDO_MAIS_BARATO"
        assert result["policy_source"] == "TABELA_SEGMENTOS"
        assert result["policy_output"]["acao"] == "ACORDAR"
        assert result["policy_version"].startswith("politica-")
        assert result["contract_version"] == "padrao"
        assert result["feature_provenance"][0]["value"] == 1
        assert result["pricing"]["target_value"] > 0

        decision = client.post(
            f"/api/cases/{case_id}/lawyer-decisions?analysis_id={result['id']}",
            json={"action": "ACORDO", "proposed_value": 300},
        )
        assert decision.status_code == 201
        monitoring = client.get("/api/monitoring").json()
        assert monitoring["adherence_rate"] == 1.0


def test_mismatched_document_requires_confirmation(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        upload = client.post(
            f"/api/cases/{case_id}/documents",
            data={"declared_type": "CONTRATO", "source_party": "BANCO"},
            files={"file": ("extrato.txt", "Extrato bancário. Saldo. Lançamentos de conta.", "text/plain")},
        )
        assert upload.status_code == 201
        document = client.get(f"/api/cases/{case_id}").json()["documents"][0]
        assert document["type_status"] == "MISMATCH"

        confirmation = client.post(
            f"/api/documents/{document['id']}/type-confirmation",
            json={"action": "RECLASSIFY", "document_type": "EXTRATO", "reason": "Revisão do advogado."},
        )
        assert confirmation.status_code == 200
        assert confirmation.json()["type_status"] == "CONFIRMED"


def test_document_request_tracks_bank_unavailability(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        created = client.post(
            f"/api/cases/{case_id}/document-requests",
            json={
                "document_type": "EXTRATO",
                "hypothesis_key": "CREDITO_NA_CONTA",
                "reason": "Verificar o crédito da operação.",
            },
        )
        assert created.status_code == 201
        request_id = created.json()["id"]
        response = client.post(
            f"/api/document-requests/{request_id}/response",
            json={"status": "DECLARED_UNAVAILABLE", "reason": "Documento não localizado."},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "DECLARED_UNAVAILABLE"


def test_request_is_closed_atomically_when_its_document_is_uploaded(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        request = client.post(
            f"/api/cases/{case_id}/document-requests",
            json={
                "document_type": "EXTRATO",
                "hypothesis_key": "CREDITO_NA_CONTA",
                "reason": "Verificar o crédito da operação.",
            },
        )
        request_id = request.json()["id"]

        upload = client.post(
            f"/api/cases/{case_id}/documents",
            data={
                "declared_type": "EXTRATO",
                "source_party": "BANCO",
                "request_id": request_id,
            },
            files={"file": ("extrato.txt", "Extrato bancário. Saldo. Lançamentos de conta.", "text/plain")},
        )
        assert upload.status_code == 201
        detail = client.get(f"/api/cases/{case_id}").json()
        assert detail["document_requests"][0]["status"] == "SUBMITTED"

        repeated_response = client.post(
            f"/api/document-requests/{request_id}/response",
            json={"status": "CANCELLED", "reason": "Pedido já atendido."},
        )
        assert repeated_response.status_code == 409


def test_request_stays_open_when_the_uploaded_document_has_another_type(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        request = client.post(
            f"/api/cases/{case_id}/document-requests",
            json={
                "document_type": "EXTRATO",
                "hypothesis_key": "CREDITO_NA_CONTA",
                "reason": "Verificar o crédito da operação.",
            },
        )
        request_id = request.json()["id"]

        upload = client.post(
            f"/api/cases/{case_id}/documents",
            data={
                "declared_type": "CONTRATO",
                "source_party": "BANCO",
                "request_id": request_id,
            },
            files={"file": ("contrato.txt", "Cédula de crédito. Contrato de empréstimo.", "text/plain")},
        )
        assert upload.status_code == 409
        detail = client.get(f"/api/cases/{case_id}").json()
        assert detail["document_requests"][0]["status"] == "REQUESTED"
        assert detail["documents"] == []


def test_dossie_document_does_not_change_the_case_assessment(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        upload = client.post(
            f"/api/cases/{case_id}/documents",
            data={"declared_type": "DOSSIE", "source_party": "BANCO"},
            files={"file": ("dossie.txt", "Dossiê de validação documental.", "text/plain")},
        )
        assert upload.status_code == 201
        detail = client.get(f"/api/cases/{case_id}").json()
        assert detail["case"]["dossie_status"] == "AUSENTE"


def test_zero_claim_value_keeps_agreement_recommendation_without_pricing(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/cases",
            json={"case_number": "0000002-00.2026.8.26.0001", "uf": "SP", "value_of_claim": 0},
        )
        case_id = response.json()["id"]

        analysis = client.post(f"/api/cases/{case_id}/analyses")
        assert analysis.status_code == 201
        assert analysis.json()["recommendation"] == "ACORDO"
        assert analysis.json()["pricing"] is None


def test_invalid_pdf_records_failure_without_breaking_the_api(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        response = client.post(
            f"/api/cases/{case_id}/documents",
            data={"declared_type": "CONTRATO", "source_party": "BANCO"},
            files={"file": ("corrupted.pdf", b"%PDF-1.7\ninvalid", "application/pdf")},
        )
        assert response.status_code == 201
        document = client.get(f"/api/cases/{case_id}").json()["documents"][0]
        assert document["status"] == "FAILED"
        assert document["quality_flags"][0].startswith("EXTRACTION_FAILED:")
        analysis = client.post(f"/api/cases/{case_id}/analyses").json()
        assert analysis["documentary_status"] == "FALHA_TECNICA"


def test_concurrent_duplicate_upload_preserves_the_original_file(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    content = b"Contrato de emprestimo. Cedula de credito. Assinatura."
    with TestClient(app) as client:
        case_id = _create_case(client)

        def upload():
            return client.post(
                f"/api/cases/{case_id}/documents",
                data={"declared_type": "CONTRATO", "source_party": "BANCO"},
                files={"file": ("contract.txt", content, "text/plain")},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: upload(), range(2)))
        assert sorted(response.status_code for response in responses) == [201, 409]
        documents = client.get(f"/api/cases/{case_id}").json()["documents"]
        assert len(documents) == 1
        download = client.get(f"/api/documents/{documents[0]['id']}/file")
        assert download.status_code == 200
        assert download.content == content


def test_contract_and_statement_lead_to_defense_by_the_segment_table(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        for document_type, content in [
            ("CONTRATO", "Cédula de crédito. Contrato de empréstimo. Assinatura."),
            ("EXTRATO", "Extrato bancário. Saldo. Lançamentos na conta corrente."),
        ]:
            response = client.post(
                f"/api/cases/{case_id}/documents",
                data={"declared_type": document_type, "source_party": "BANCO"},
                files={"file": (f"{document_type}.txt", content, "text/plain")},
            )
            assert response.status_code == 201
        analysis = client.post(f"/api/cases/{case_id}/analyses")
        assert analysis.status_code == 201
        result = analysis.json()
        assert result["policy_source"] == "TABELA_SEGMENTOS"
        assert result["recommendation"] == "DEFESA"
        assert result["pricing"] is None
        assert result["policy_output"]["segmento"].startswith("C1 E1")


def test_frontend_preview_origin_can_access_the_api(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.options(
            "/api/cases",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:4173"
        response = client.options(
            "/api/cases",
            headers={
                "Origin": "https://unconfigured.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 400
