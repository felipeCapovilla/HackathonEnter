"""Create the first admin locally; it is never exposed as a public endpoint."""

from __future__ import annotations

import argparse
import getpass
import secrets
from datetime import UTC, datetime

from src.interface.backend.auth import hash_password, normalize_email
from src.interface.backend.config import get_settings
from src.interface.backend.database import initialize_database
from src.interface.backend.repository import Repository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    arguments = parser.parse_args()
    password = getpass.getpass("Senha do admin (15+ caracteres): ")
    settings = get_settings()
    initialize_database(settings.database_path)
    repository = Repository(settings.database_path)
    try:
        repository.create_user({
            "id": secrets.token_hex(16), "name": arguments.name.strip(),
            "email": normalize_email(arguments.email), "password_hash": hash_password(password),
            "role": "ADMIN_GLOBAL", "bank_id": None, "is_active": True,
            "created_at": datetime.now(UTC).isoformat(),
        })
    except ValueError as exc:
        parser.error(str(exc))
    print("Admin criado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
