"""Caminhos canônicos do projeto. Todos os scripts do monitor importam daqui."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"

_XLSX_FILENAME = "Hackaton_Enter_Base_Candidatos.xlsx"


def _resolve_xlsx_base() -> Path:
    """Procura o xlsx em locais comuns, na ordem de prioridade.

    1. data/Hackaton_Enter_Base_Candidatos.xlsx (versionado no repo, padrão)
    2. data/raw/Hackaton_Enter_Base_Candidatos.xlsx (legado, via symlink)

    Se nenhum existir, retorna o caminho do primeiro (mensagem de erro
    fica clara quando o script tenta ler).
    """
    candidates = [
        REPO_ROOT / "data" / _XLSX_FILENAME,
        DATA_RAW / _XLSX_FILENAME,
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


XLSX_BASE = _resolve_xlsx_base()

CASOS_60K = DATA_PROCESSED / "casos_60k.parquet"
CASOS_ENRIQUECIDOS = DATA_PROCESSED / "casos_enriquecidos.parquet"
BASELINE_JSON = DATA_PROCESSED / "baseline.json"

POLITICA_OUTPUT = DATA_PROCESSED / "politica_output.csv"
