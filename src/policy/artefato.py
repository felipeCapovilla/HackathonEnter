"""Leitura do artefato gerado por scripts/gerar_tabela_politica.py."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CAMINHO = Path(__file__).resolve().parents[2] / "artefatos" / "politica_segmentos.json"


@lru_cache(maxsize=1)
def carregar() -> dict:
    if not CAMINHO.is_file():
        raise FileNotFoundError(f"{CAMINHO} ausente. Gere com: python scripts/gerar_tabela_politica.py")
    return json.loads(CAMINHO.read_text(encoding="utf-8"))
