"""Auditoria imutável, reset/troca de senha e classificação de tipo por IA no upload."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.interface.backend.auth import hash_password
from src.interface.backend.config import Settings
from src.interface.backend.database import connection_for
from src.interface.backend.main import create_app
from src.tools.leitor_documentos import LeituraDocumento


def settings(tmp_path: Path) -> Settings:
    runtime = tmp_path / "runtime"
    return Settings(runtime, runtime / "app.db", runtime / "documents", Path("artefatos"), 1024 * 1024, auth_required=True)


def add_user(app, role, email, bank_id="banco-unicamp", is_manager=False):
    return app.state.repository.create_user({
        "id": role + email, "name": role.title(), "email": email,
        "password_hash": hash_password("senha-segura-com-15"), "role": role,
        "bank_id": None if role == "ADMIN_GLOBAL" else bank_id, "is_active": True,
        "is_manager": is_manager, "created_at": "2026-09-12T00:00:00+00:00",
    })


def login(client, email, password="senha-segura-com-15"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()


def _create_case(client: TestClient) -> str:
    response = client.post(
        "/api/cases",
        json={"case_number": "audit-0001", "uf": "SP", "value_of_claim": 1000},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _wait_for(client, case_id, document_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        document = next(d for d in client.get(f"/api/cases/{case_id}").json()["documents"] if d["id"] == document_id)
        if document["status"] not in {"UPLOADED", "EXTRACTING"}:
            return document
        time.sleep(0.05)
    raise AssertionError("Documento não terminou de processar a tempo.")


# ---------------------------------------------------------------------------
# Auditoria imutável
# ---------------------------------------------------------------------------

def test_login_logout_and_user_management_are_audited(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as admin_client, TestClient(app) as bank_client:
        add_user(app, "ADMIN_GLOBAL", "admin@enter.ai")
        login(admin_client, "admin@enter.ai")
        created = admin_client.post("/api/admin/users", json={
            "name": "Banco Unicamp", "email": "bank@unicamp.br", "password": "senha-segura-com-15",
            "role": "BANCO", "bank_id": "banco-unicamp",
        })
        assert created.status_code == 201
        bank = created.json()
        login(bank_client, "bank@unicamp.br")
        admin_client.post("/api/auth/login", json={"email": "bank@unicamp.br", "password": "senha-errada-123456"})
        bank_client.post("/api/auth/logout")
        # A troca de senha revoga a sessão do próprio banco; testada isoladamente aqui só para o rastro.
        admin_client.patch(f"/api/admin/users/{bank['id']}", json={"password": "outra-senha-de-15-chars"})

        events = admin_client.get("/api/admin/audit-events").json()
        actions = [event["action"] for event in events]
        assert "LOGIN" in actions
        assert "LOGIN_FAILED" in actions
        assert "PASSWORD_RESET" in actions
        assert "LOGOUT" in actions
        assert "USER_CREATED" in actions


def test_audit_events_endpoint_requires_admin(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank_client:
        add_user(app, "BANCO", "bank@unicamp.br")
        login(bank_client, "bank@unicamp.br")
        assert bank_client.get("/api/admin/audit-events").status_code == 403


def test_audit_chain_is_valid_and_tamper_evident(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as admin_client:
        add_user(app, "ADMIN_GLOBAL", "admin@enter.ai")
        login(admin_client, "admin@enter.ai")
        status = admin_client.get("/api/admin/audit-events/verify").json()
        assert status["valid"] is True
        assert status["checked"] >= 1

        with connection_for(app.state.repository.database_path) as connection:
            with pytest.raises(Exception):
                connection.execute("UPDATE audit_events SET action = 'FORJADO' WHERE 1=1")
            with pytest.raises(Exception):
                connection.execute("DELETE FROM audit_events")


def test_audit_chain_detects_direct_row_replacement(tmp_path):
    """Sem o gatilho (bypass via DELETE+INSERT bruto), a verificação ainda pega a violação."""
    app = create_app(settings(tmp_path))
    with TestClient(app) as admin_client:
        add_user(app, "ADMIN_GLOBAL", "admin@enter.ai")
        login(admin_client, "admin@enter.ai")
        with connection_for(app.state.repository.database_path) as connection:
            row = connection.execute("SELECT * FROM audit_events ORDER BY rowid LIMIT 1").fetchone()
            connection.execute("DROP TRIGGER audit_events_no_update")
            connection.execute("UPDATE audit_events SET reason = 'adulterado' WHERE id = ?", (row["id"],))
        status = admin_client.get("/api/admin/audit-events/verify").json()
        assert status["valid"] is False
        assert status["broken_at_id"] == row["id"]


# ---------------------------------------------------------------------------
# Reset e troca de senha
# ---------------------------------------------------------------------------

def test_self_service_change_password(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        add_user(app, "BANCO", "bank@unicamp.br")
        login(client, "bank@unicamp.br")
        wrong = client.post("/api/auth/change-password", json={
            "current_password": "senha-errada-123456", "new_password": "nova-senha-com-15",
        })
        assert wrong.status_code == 401
        ok = client.post("/api/auth/change-password", json={
            "current_password": "senha-segura-com-15", "new_password": "nova-senha-com-15",
        })
        assert ok.status_code == 204
        # Troca de senha revoga a própria sessão: a chamada seguinte já não está autenticada.
        assert client.get("/api/cases").status_code == 401
        relogged = login(client, "bank@unicamp.br", password="nova-senha-com-15")
        assert relogged["email"] == "bank@unicamp.br"


def test_bank_manager_resets_password_within_own_bank_only(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as manager_client, TestClient(app) as lawyer_client:
        manager = add_user(app, "BANCO", "gestor@unicamp.br", is_manager=True)
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "advogado@unicamp.br")
        other_bank = app.state.repository.create_bank("Outro Banco")
        outsider = add_user(app, "BANCO", "fora@outrobanco.br", bank_id=other_bank["id"])
        login(manager_client, "gestor@unicamp.br")

        reset = manager_client.patch(f"/api/bank/users/{lawyer['id']}/password", json={"new_password": "senha-nova-com-15"})
        assert reset.status_code == 204
        login(lawyer_client, "advogado@unicamp.br", password="senha-nova-com-15")

        assert manager_client.patch(f"/api/bank/users/{outsider['id']}/password", json={"new_password": "x" * 20}).status_code == 404


def test_bank_non_manager_cannot_reset_password(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        bank = add_user(app, "BANCO", "bank@unicamp.br", is_manager=False)
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "advogado@unicamp.br")
        login(client, "bank@unicamp.br")
        assert client.patch(f"/api/bank/users/{lawyer['id']}/password", json={"new_password": "x" * 20}).status_code == 403


# ---------------------------------------------------------------------------
# Upload com classificação automática de tipo por IA
# ---------------------------------------------------------------------------

def _ai_settings(tmp_path: Path) -> Settings:
    runtime = tmp_path / "runtime"
    return Settings(
        runtime_dir=runtime, database_path=runtime / "enteragree.db", document_dir=runtime / "documents",
        artifact_dir=Path("artefatos"), max_upload_bytes=1024 * 1024, auth_required=False,
    )


def test_upload_without_declared_type_uses_ai_path_and_keyword_fallback(tmp_path):
    """Sem OPENAI_API_KEY no ambiente de teste, cai no fallback determinístico (nunca recusa por conta própria)."""
    app = create_app(_ai_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        upload = client.post(
            f"/api/cases/{case_id}/documents",
            data={"source_party": "BANCO"},
            files={"file": ("contrato.txt", "Cédula de crédito. Contrato de mútuo. Assinatura das partes.", "text/plain")},
        )
        assert upload.status_code == 201
        document_id = upload.json()["id"]
        document = _wait_for(client, case_id, document_id)
        assert document["type_source"] == "AI"
        assert document["declared_type"] == "CONTRATO"
        assert document["type_status"] == "AI_CONFIRMED"
        assert "IA indisponível" in document["ai_type_reason"]


def test_upload_with_declared_type_keeps_old_deterministic_flow(tmp_path):
    app = create_app(_ai_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        upload = client.post(
            f"/api/cases/{case_id}/documents",
            data={"declared_type": "CONTRATO", "source_party": "BANCO"},
            files={"file": ("contrato.txt", "Cédula de crédito. Contrato de mútuo. Assinatura das partes.", "text/plain")},
        )
        document = _wait_for(client, case_id, upload.json()["id"])
        assert document["type_source"] == "USER"
        assert document["type_status"] == "CONFIRMED"
        assert document["ai_type_reason"] is None


def test_ai_rejected_document_is_visible_but_does_not_feed_the_policy(tmp_path, monkeypatch):
    from src.utils import document_service as document_service_module

    monkeypatch.setattr(
        document_service_module,
        "ler_documento",
        lambda caminho, texto, tipo_declarado: LeituraDocumento(
            tipo_documento="RECUSADO", resumo="Não tem relação com o processo.",
        ),
    )
    app = create_app(_ai_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        upload = client.post(
            f"/api/cases/{case_id}/documents",
            data={"source_party": "BANCO"},
            files={"file": ("aleatorio.txt", "Receita de bolo de cenoura com cobertura de chocolate.", "text/plain")},
        )
        document = _wait_for(client, case_id, upload.json()["id"])
        assert document["type_status"] == "AI_REJECTED"
        assert document["declared_type"] == "OUTRO"
        assert document["ai_type_reason"] == "Não tem relação com o processo."

        # Continua visível na lista (não é soft-delete) e não trava a avaliação do processo.
        detail = client.get(f"/api/cases/{case_id}").json()
        assert any(d["id"] == document["id"] for d in detail["documents"])

        # A leitura fica salva no mesmo lugar usado pelo card consultivo do advogado.
        reading = next(r for r in detail["document_readings"] if r["document_id"] == document["id"])
        assert reading["status"] == "COMPLETED"
        assert reading["result"]["tipo_documento"] == "RECUSADO"

        analysis = client.post(f"/api/cases/{case_id}/analyses")
        assert analysis.status_code == 201
        assert "recusado pela IA" in " ".join(analysis.json()["limitations"])

        # O banco ainda pode excluir o documento recusado e reenviar.
        assert client.delete(f"/api/cases/{case_id}/documents/{document['id']}").status_code == 204


def test_ai_confirmed_document_reuses_the_rich_document_reading(tmp_path, monkeypatch):
    """A classificação automática usa a mesma leitura consultiva (contrato, valores, pontos de atenção)."""
    from src.utils import document_service as document_service_module

    monkeypatch.setattr(
        document_service_module,
        "ler_documento",
        lambda caminho, texto, tipo_declarado: LeituraDocumento(
            tipo_documento="CONTRATO", resumo="Contrato de mútuo entre banco e cliente.",
            numero_contrato="12345", valor_principal=5000.0, pontos_de_atencao=["Conferir assinatura na página 3"],
        ),
    )
    app = create_app(_ai_settings(tmp_path))
    with TestClient(app) as client:
        case_id = _create_case(client)
        upload = client.post(
            f"/api/cases/{case_id}/documents",
            data={"source_party": "BANCO"},
            files={"file": ("contrato.txt", "texto qualquer, a leitura está mockada", "text/plain")},
        )
        document = _wait_for(client, case_id, upload.json()["id"])
        assert document["type_status"] == "AI_CONFIRMED"
        assert document["declared_type"] == "CONTRATO"

        detail = client.get(f"/api/cases/{case_id}").json()
        reading = next(r for r in detail["document_readings"] if r["document_id"] == document["id"])
        assert reading["result"]["numero_contrato"] == "12345"
        assert reading["result"]["pontos_de_atencao"] == ["Conferir assinatura na página 3"]

        # A política já usa o documento confirmado pela IA como se fosse confirmado pelo usuário.
        analysis = client.post(f"/api/cases/{case_id}/analyses")
        assert analysis.status_code == 201
        assert analysis.json()["feature_vector"]["Contrato"] == 1
