import pytest

from scripts import seed_demo
from src.interface.backend.auth import hash_password, verify_password
from src.interface.backend.database import initialize_database
from src.interface.backend.repository import Repository


def test_demo_seed_creates_expected_accounts_and_preserves_existing_data(tmp_path):
    database_path = tmp_path / "demo.db"
    assert seed_demo.seed_demo(database_path) == 3
    repository = Repository(database_path)
    before = repository.list_users()
    for expected in seed_demo.DEMO_USERS:
        user = repository.get_user_by_email(expected["email"])
        assert user["role"] == expected["role"]
        assert user["bank_id"] == expected["bank_id"]
        assert user["is_active"]
        assert verify_password(seed_demo.DEMO_PASSWORD, user["password_hash"])
    admin = repository.get_user_by_email("admin@demo.local")
    repository.create_session("test-token-hash", admin["id"], "test-csrf", "2099-01-01T00:00:00+00:00")
    assert seed_demo.seed_demo(database_path) == 0
    assert repository.list_users() == before
    assert repository.get_session_user("test-token-hash") is not None


def test_demo_seed_refuses_to_overwrite_an_existing_account(tmp_path):
    database_path = tmp_path / "demo.db"
    initialize_database(database_path)
    repository = Repository(database_path)
    repository.create_user({
        **seed_demo.DEMO_USERS[1], "id": "existing-bank", "password_hash": hash_password("senha-individual-existente"),
        "is_active": True, "created_at": "2026-09-12T00:00:00+00:00",
    })
    with pytest.raises(ValueError, match="Nenhuma conta foi sobrescrita"):
        seed_demo.seed_demo(database_path)
    assert len(repository.list_users()) == 1
    assert verify_password("senha-individual-existente", repository.get_user("existing-bank")["password_hash"])


def test_demo_cli_requires_explicit_confirmation(tmp_path, monkeypatch):
    database_path = tmp_path / "demo.db"
    monkeypatch.setattr(seed_demo, "DEMO_DATABASE_PATH", database_path)
    monkeypatch.setattr("sys.argv", ["seed_demo"])
    with pytest.raises(SystemExit) as error:
        seed_demo.main()
    assert error.value.code == 2
    assert not database_path.exists()


def test_reset_changes_only_demo_passwords_and_revokes_old_sessions(tmp_path):
    database_path = tmp_path / "demo.db"
    seed_demo.seed_demo(database_path)
    repository = Repository(database_path)
    bank = repository.get_user_by_email("banco@demo.local")
    repository.update_user(bank["id"], {"password_hash": hash_password("senha-antiga-de-demonstracao")})
    repository.create_session("old-demo-session", bank["id"], "csrf", "2099-01-01T00:00:00+00:00")
    other = repository.create_user({
        **seed_demo.DEMO_USERS[1], "email": "nao-demo@example.test", "id": "not-demo",
        "password_hash": hash_password("senha-exclusiva-nao-demo"), "is_active": True,
        "created_at": "2026-09-12T00:00:00+00:00",
    })
    assert seed_demo.seed_demo(database_path, reset_passwords=True) == 1
    assert repository.get_user(bank["id"])["id"] == bank["id"]
    assert verify_password("teste123", repository.get_user(bank["id"])["password_hash"])
    assert repository.get_session_user("old-demo-session") is None
    assert repository.get_user("not-demo") == other
    with pytest.raises(ValueError, match="15 e 128"):
        hash_password("teste123")


def test_demo_cli_does_not_write_to_configured_application_database(tmp_path, monkeypatch):
    database_path = tmp_path / "demo.db"
    application_path = tmp_path / "application.db"
    monkeypatch.setattr(seed_demo, "DEMO_DATABASE_PATH", database_path)
    monkeypatch.setenv("ENTERAGREE_DATABASE_PATH", str(application_path))
    monkeypatch.setattr("sys.argv", ["seed_demo", "--confirm-demo"])
    assert seed_demo.main() == 0
    assert database_path.exists()
    assert not application_path.exists()
