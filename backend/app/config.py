"""Runtime configuration for the API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Settings:
    runtime_dir: Path
    database_path: Path
    document_dir: Path
    artifact_dir: Path
    max_upload_bytes: int


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
    )
