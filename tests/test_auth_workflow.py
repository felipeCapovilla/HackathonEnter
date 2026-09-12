from pathlib import Path

from fastapi.testclient import TestClient

from src.interface.backend.auth import hash_password
from src.interface.backend.config import Settings
from src.interface.backend.main import create_app


def settings(tmp_path):
    runtime = tmp_path / "runtime"
    return Settings(runtime, runtime / "app.db", runtime / "documents", Path("artefatos"), 1024 * 1024, auth_required=True)


def add_user(app, role, email, bank_id="banco-unicamp"):
    return app.state.repository.create_user({
        "id": role + email, "name": role.title(), "email": email,
        "password_hash": hash_password("senha-segura-com-15"), "role": role,
        "bank_id": None if role == "ADMIN_GLOBAL" else bank_id, "is_active": True,
        "created_at": "2026-09-12T00:00:00+00:00",
    })


def login(client, email):
    response = client.post("/api/auth/login", json={"email": email, "password": "senha-segura-com-15"})
    assert response.status_code == 200
    assert "enteragree_session" in response.headers["set-cookie"]
    return response.json()


def test_login_roles_and_case_assignment_scope(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank_client, TestClient(app) as lawyer_client, TestClient(app) as other_client:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "advogado@unicamp.br")
        add_user(app, "ADVOGADO_EXTERNO", "outro@unicamp.br")
        assert bank_client.get("/api/auth/me").json() is None
        assert bank_client.get("/api/cases").status_code == 401
        login(bank_client, "BANCO@UNICAMP.BR")
        login(lawyer_client, "advogado@unicamp.br")
        login(other_client, "outro@unicamp.br")
        created = bank_client.post("/api/cases", json={"case_number": "role-001", "uf": "SP", "value_of_claim": 1000, "assigned_lawyer_id": lawyer["id"]})
        assert created.status_code == 201
        case_id = created.json()["id"]
        assert created.json()["assigned_lawyer_id"] == lawyer["id"]
        assert [item["id"] for item in lawyer_client.get("/api/cases").json()] == [case_id]
        assert other_client.get(f"/api/cases/{case_id}").status_code == 404
        assert lawyer_client.post(f"/api/cases/{case_id}/analyses").status_code == 201
        assert bank_client.get(f"/api/cases/{case_id}").json()["analyses"][0]["recommendation"] in {"ACORDO", "DEFESA"}


def test_admin_creates_lawyer_and_cannot_open_operational_case(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as admin_client:
        add_user(app, "ADMIN_GLOBAL", "admin@enter.ai")
        login(admin_client, "admin@enter.ai")
        banks = admin_client.get("/api/admin/banks")
        assert banks.status_code == 200 and banks.json()[0]["name"] == "Banco Unicamp"
        created = admin_client.post("/api/admin/users", json={
            "name": "Nova Advogada", "email": "nova@unicamp.br", "password": "senha-segura-com-15",
            "role": "ADVOGADO_EXTERNO", "bank_id": "banco-unicamp",
        })
        assert created.status_code == 201
        assert admin_client.get("/api/cases").status_code == 403


def test_disabled_user_session_is_revoked(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as admin_client, TestClient(app) as bank_client:
        bank = add_user(app, "BANCO", "bank@unicamp.br")
        add_user(app, "ADMIN_GLOBAL", "admin@enter.ai")
        login(bank_client, "bank@unicamp.br")
        login(admin_client, "admin@enter.ai")
        assert admin_client.patch(f"/api/admin/users/{bank['id']}", json={"is_active": False}).status_code == 200
        assert bank_client.get("/api/cases").status_code == 401
