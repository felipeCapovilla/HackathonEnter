"""Runtime configuration for the API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)


@dataclass(frozen=True, slots=True)
class Settings:
    runtime_dir: Path
    database_path: Path
    document_dir: Path
    artifact_dir: Path
    max_upload_bytes: int
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    auth_required: bool = True
    dossie_auto_analysis: bool = True
    leitura_ia: bool = True


def get_settings() -> Settings:
    runtime_dir = Path(os.getenv("ENTERAGREE_RUNTIME_DIR", PROJECT_ROOT / ".runtime"))
    document_dir = runtime_dir / "documents"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    document_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        runtime_dir=runtime_dir,
        database_path=Path(os.getenv("ENTERAGREE_DATABASE_PATH", runtime_dir / "enteragree.db")),
        document_dir=document_dir,
        artifact_dir=PROJECT_ROOT / "artefatos",
        max_upload_bytes=int(os.getenv("ENTERAGREE_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024))),
        cors_origins=tuple(
            origin.strip()
            for origin in os.getenv("ENTERAGREE_CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)).split(",")
            if origin.strip()
        ),
        auth_required=os.getenv("ENTERAGREE_AUTH_REQUIRED", "true").lower() not in {"0", "false", "no"},
        dossie_auto_analysis=os.getenv("ENTERAGREE_DOSSIE_AUTO", "true").lower() not in {"0", "false", "no"},
        leitura_ia=os.getenv("ENTERAGREE_LEITURA_IA", "true").lower() not in {"0", "false", "no"},
    )
