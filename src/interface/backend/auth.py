"""Opaque server-side sessions and password hashing for the small role MVP."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request

from .repository import Repository
from .schemas import UserRole

COOKIE_NAME = "enteragree_session"
SESSION_HOURS = 8


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def hash_password(password: str, salt: bytes | None = None) -> str:
    if not 15 <= len(password) <= 128:
        raise ValueError("A senha deve ter entre 15 e 128 caracteres.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_digest = stored.split("$")
        if algorithm != "scrypt":
            return False
        expected = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.urlsafe_b64decode(encoded_salt),
            n=int(n), r=int(r), p=int(p),
        )
        return hmac.compare_digest(expected, base64.urlsafe_b64decode(encoded_digest))
    except (ValueError, TypeError):
        return False


def session_expiry() -> str:
    return (datetime.now(UTC) + timedelta(hours=SESSION_HOURS)).isoformat()


def require_user(request: Request) -> dict:
    repository: Repository = request.app.state.repository
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Autenticação necessária.")
    user = repository.get_session_user(hashlib.sha256(token.encode()).hexdigest())
    if user is None:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    return user


def require_role(user: dict, *roles: UserRole) -> dict:
    if user["role"] == "SYSTEM":
        return user
    if user["role"] not in {role.value for role in roles}:
        raise HTTPException(403, "Seu perfil não possui permissão para esta ação.")
    return user


def require_case_access(repository: Repository, case_id: str, user: dict) -> dict:
    case = repository.get_case(case_id)
    if case is None or user["role"] == UserRole.ADMIN_GLOBAL.value:
        raise HTTPException(404, "Processo não encontrado.")
    if user["role"] != "SYSTEM" and case["bank_id"] != user["bank_id"]:
        raise HTTPException(404, "Processo não encontrado.")
    if user["role"] == UserRole.ADVOGADO_EXTERNO.value and case["assigned_lawyer_id"] != user["id"]:
        raise HTTPException(404, "Processo não encontrado.")
    return case
