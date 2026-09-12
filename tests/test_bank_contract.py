"""Contrato banco–escritório versionado por banco, aplicado na análise e protegido por papel."""
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.interface.backend.auth import hash_password
from src.interface.backend.config import Settings
from src.interface.backend.main import create_app
from src.interface.backend.schemas import CaseCreate, DocumentType, DocumentTypeStatus, SourceParty

ROOT = Path(__file__).resolve().parents[1]
BANCO = "banco-unicamp"


def _settings(tmp_path: Path, auth: bool) -> Settings:
    runtime = tmp_path / "runtime"
    return Settings(runtime_dir=runtime, database_path=runtime / "app.db", document_dir=runtime / "documents",
                    artifact_dir=ROOT / "artefatos", max_upload_bytes=1024 * 1024, auth_required=auth)


def _document(app, case_id: str, declared_type: DocumentType) -> None:
    repository = app.state.repository
    document = repository.create_document(
        case_id=case_id, original_filename=f"{declared_type.value}.txt", file_path=Path("unused.txt"),
        declared_type=declared_type, source_party=SourceParty.BANCO, sha256=str(uuid4()), request_id=None)
    repository.append_document_pages(document["id"], [{
        "page_number": 1, "text_content": "conteúdo", "extraction_method": "TEXT", "quality_flags": []}])
    repository.update_document_extraction(
        document["id"], status="COMPLETED", page_count=1, pages_extracted=1, quality_flags=[],
        detected_type=declared_type, type_status=DocumentTypeStatus.CONFIRMED)


def test_contract_versions_change_the_decision_and_are_recorded(tmp_path):
    app = create_app(_settings(tmp_path, auth=False))
    with TestClient(app) as client:
        padrao = client.get(f"/api/admin/banks/{BANCO}/contract").json()
        assert padrao["version"] == 0 and padrao["parameters"]["versao"] == "padrao"

        case = app.state.repository.create_case(
            CaseCreate(case_number=str(uuid4()), uf="MA", value_of_claim=15000, sub_subject="Golpe"))
        _document(app, case["id"], DocumentType.EXTRATO)
        _document(app, case["id"], DocumentType.COMPROVANTE_CREDITO)
        antes = client.post(f"/api/cases/{case['id']}/analyses").json()
        assert antes["recommendation"] == "ACORDO"
        assert antes["contract_version"] == "padrao"

        honorario_acordo = {"honorario_acordo": {"tipo": "percentual_valor_causa", "valor": 0.15}}
        v1 = client.post(f"/api/admin/banks/{BANCO}/contract", json=honorario_acordo)
        assert v1.status_code == 201 and v1.json()["version"] == 1
        assert client.post(f"/api/admin/banks/{BANCO}/contract", json={}).json()["version"] == 2
        assert client.post(f"/api/admin/banks/{BANCO}/contract", json=honorario_acordo).json()["version"] == 3

        depois = client.post(f"/api/cases/{case['id']}/analyses").json()
        assert depois["recommendation"] == "DEFESA"
        assert depois["contract_version"] == f"{BANCO}-v3"
        assert client.get(f"/api/cases/{case['id']}").json()["analyses"][-1]["contract_version"] == "padrao"


def test_invalid_contract_is_rejected(tmp_path):
    app = create_app(_settings(tmp_path, auth=False))
    with TestClient(app) as client:
        bad = client.post(f"/api/admin/banks/{BANCO}/contract",
                          json={"honorario_defesa_ganha": {"tipo": "percentual_valor_causa", "valor": 15}})
        assert bad.status_code == 422
        assert client.post("/api/admin/banks/inexistente/contract", json={}).status_code == 404


def test_only_global_admin_edits_and_bank_only_reads(tmp_path):
    app = create_app(_settings(tmp_path, auth=True))
    with TestClient(app) as admin, TestClient(app) as bank, TestClient(app) as lawyer:
        for role, email, client in (("ADMIN_GLOBAL", "admin@t.br", admin), ("BANCO", "banco@t.br", bank),
                                    ("ADVOGADO_EXTERNO", "adv@t.br", lawyer)):
            app.state.repository.create_user({
                "id": role, "name": role.title(), "email": email, "password_hash": hash_password("senha-segura-com-15"),
                "role": role, "bank_id": None if role == "ADMIN_GLOBAL" else BANCO, "is_active": True,
                "created_at": "2026-09-12T00:00:00+00:00"})
            assert client.post("/api/auth/login", json={"email": email, "password": "senha-segura-com-15"}).status_code == 200

        assert admin.post(f"/api/admin/banks/{BANCO}/contract", json={"duracao_meses": 12}).status_code == 201
        assert bank.post(f"/api/admin/banks/{BANCO}/contract", json={}).status_code == 403
        assert lawyer.get(f"/api/admin/banks/{BANCO}/contract").status_code == 403
        assert lawyer.get("/api/bank/contract").status_code == 403
        vigente = bank.get("/api/bank/contract").json()
        assert vigente["version"] == 1 and vigente["parameters"]["duracao_meses"] == 12


def test_preview_compares_current_and_proposed_contract(tmp_path):
    if not (ROOT / "data" / "resultados.csv").is_file():
        pytest.skip("base histórica não está em data/ (gitignored)")
    app = create_app(_settings(tmp_path, auth=False))
    with TestClient(app) as client:
        response = client.post(f"/api/admin/banks/{BANCO}/contract/preview",
                               json={"honorario_acordo": {"tipo": "percentual_valor_causa", "valor": 0.15}})
        assert response.status_code == 200
        preview = response.json()
        assert preview["casos"] == 12000
        assert preview["decisoes_alteradas"] > 0
        assert preview["contrato_proposto"]["acoes"] != preview["contrato_vigente"]["acoes"]
