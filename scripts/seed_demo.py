"""Explicit local-only demo accounts, isolated from the default application database."""

from __future__ import annotations

import argparse
import base64
import hashlib
import secrets
from datetime import UTC, datetime
from pathlib import Path

from src.interface.backend.auth import verify_password
from src.interface.backend.config import PROJECT_ROOT
from src.interface.backend.database import initialize_database
from src.interface.backend.repository import Repository


DEMO_DATABASE_PATH = PROJECT_ROOT / ".runtime" / "demo" / "enteragree.db"
DEMO_PASSWORD = "teste123"
DEMO_USERS = (
    {"name": "Admin Demo", "email": "admin@demo.local", "role": "ADMIN_GLOBAL", "bank_id": None},
    {"name": "Banco Unicamp", "email": "banco@demo.local", "role": "BANCO", "bank_id": "banco-unicamp"},
    {"name": "Ana Advogada", "email": "advogada@demo.local", "role": "ADVOGADO_EXTERNO", "bank_id": "banco-unicamp"},
)


def _demo_password_hash() -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(DEMO_PASSWORD.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def seed_demo(database_path: Path, *, reset_passwords: bool = False) -> int:
    initialize_database(database_path)
    repository = Repository(database_path)
    missing = []
    password_updates = []
    for user in DEMO_USERS:
        existing = repository.get_user_by_email(user["email"])
        if existing is None:
            missing.append(user)
        elif (
            existing["role"] != user["role"]
            or existing["bank_id"] != user["bank_id"]
            or not existing["is_active"]
        ):
            raise ValueError(f"A conta {user['email']} já existe com outra configuração. Nenhuma conta foi sobrescrita.")
        elif not verify_password(DEMO_PASSWORD, existing["password_hash"]):
            if not reset_passwords:
                raise ValueError(f"A conta {user['email']} já possui outra senha. Nenhuma conta foi sobrescrita; use --reset-passwords para redefinir as senhas demo.")
            password_updates.append(existing["id"])
    for user in missing:
        repository.create_user({
            **user, "id": secrets.token_hex(16), "password_hash": _demo_password_hash(),
            "is_active": True, "created_at": datetime.now(UTC).isoformat(),
        })
    for user_id in password_updates:
        repository.update_user(user_id, {"password_hash": _demo_password_hash()})
    return len(missing) + len(password_updates)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria contas públicas de demonstração somente em .runtime/demo/enteragree.db.")
    parser.add_argument("--confirm-demo", action="store_true", help="Confirma uso local de credenciais públicas; nunca use em produção.")
    parser.add_argument("--reset-passwords", action="store_true", help="Redefine somente as três senhas demo e revoga as sessões dessas contas.")
    arguments = parser.parse_args()
    if not arguments.confirm_demo:
        parser.error("Informe --confirm-demo para criar as contas locais de demonstração.")
    try:
        changed = seed_demo(DEMO_DATABASE_PATH, reset_passwords=arguments.reset_passwords)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Seed concluído: {changed} conta(s) criada(s) ou atualizada(s). Banco de dados: {DEMO_DATABASE_PATH}")
    print("Logins e senha de demonstração estão no README. Use somente em ambiente local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
