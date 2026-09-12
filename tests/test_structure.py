from pathlib import Path

from src.interface.backend.config import PROJECT_ROOT, get_settings
from src.policy.constants import REPO_ROOT


def test_relocated_configuration_still_resolves_root_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("ENTERAGREE_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.delenv("ENTERAGREE_DATABASE_PATH", raising=False)
    settings = get_settings()

    assert PROJECT_ROOT == Path(__file__).resolve().parents[1] == REPO_ROOT
    assert settings.database_path == tmp_path / "runtime" / "enteragree.db"
    assert (settings.artifact_dir / "modelo_xgboost.pkl").is_file()
