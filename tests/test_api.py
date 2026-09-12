from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def _settings(tmp_path: Path) -> Settings:
    runtime = tmp_path / "runtime"
    return Settings(
        runtime_dir=runtime,
        database_path=runtime / "enteragree.db",
        document_dir=runtime / "documents",
        artifact_dir=Path(__file__).parents[1] / "artefatos",
        max_upload_bytes=1024 * 1024,
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
        assert result["decision_code"] == "CRITICOS_INSUFICIENTES"
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
