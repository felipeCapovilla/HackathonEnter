"""
Carrega o xlsx original da Enter e persiste o Conjunto A (60k reais) em parquet.

Saída: data/processed/casos_60k.parquet com colunas em snake_case e derivados:
    numero_processo, uf, assunto, sub_assunto,
    resultado_macro, resultado_micro,
    valor_causa, valor_condenacao,
    subs_contrato, subs_extrato, subs_comprovante, subs_dossie,
    subs_demonstrativo, subs_laudo, subs_total,
    faixa_valor, faixa_completude

Regra crítica: este parquet é a fonte de treino do XGBoost e do contrafactual.
Nunca misturar com campos sintéticos (ver casos_enriquecidos.parquet).
"""
from __future__ import annotations

import pandas as pd

from src.monitor.paths import DATA_PROCESSED, CASOS_60K, XLSX_BASE


COLS_RESULTADOS = {
    "Número do processo": "numero_processo",
    "UF": "uf",
    "Assunto": "assunto",
    "Sub-assunto": "sub_assunto",
    "Resultado macro": "resultado_macro",
    "Resultado micro": "resultado_micro",
    "Valor da causa": "valor_causa",
    "Valor da condenação/indenização": "valor_condenacao",
}

COLS_SUBSIDIOS = {
    "Número do processos": "numero_processo",  # sic: typo na base original
    "Contrato": "subs_contrato",
    "Extrato": "subs_extrato",
    "Comprovante de crédito": "subs_comprovante",
    "Dossiê": "subs_dossie",
    "Demonstrativo de evolução da dívida": "subs_demonstrativo",
    "Laudo referenciado": "subs_laudo",
}

SUBS_COLS = [
    "subs_contrato", "subs_extrato", "subs_comprovante",
    "subs_dossie", "subs_demonstrativo", "subs_laudo",
]


def load_raw(xlsx_path=XLSX_BASE) -> pd.DataFrame:
    """Lê as duas abas do xlsx, normaliza nomes e faz o merge."""
    from pathlib import Path
    xlsx_path = Path(xlsx_path)
    if not xlsx_path.exists():
        raise FileNotFoundError(
            f"Arquivo base não encontrado: {xlsx_path}\n"
            "Esperado em um destes caminhos:\n"
            "  - data/Hackaton_Enter_Base_Candidatos.xlsx (padrão)\n"
            "  - data/raw/Hackaton_Enter_Base_Candidatos.xlsx (legado)\n"
            "Verifique se o arquivo está versionado ou copie-o manualmente."
        )
    res = pd.read_excel(xlsx_path, sheet_name="Resultados dos processos")
    sub = pd.read_excel(xlsx_path, sheet_name="Subsídios disponibilizados", header=1)

    missing_res = set(COLS_RESULTADOS) - set(res.columns)
    missing_sub = set(COLS_SUBSIDIOS) - set(sub.columns)
    if missing_res:
        raise ValueError(f"Colunas ausentes em Resultados: {missing_res}")
    if missing_sub:
        raise ValueError(f"Colunas ausentes em Subsídios: {missing_sub}")

    res = res.rename(columns=COLS_RESULTADOS)[list(COLS_RESULTADOS.values())]
    sub = sub.rename(columns=COLS_SUBSIDIOS)[list(COLS_SUBSIDIOS.values())]

    for c in SUBS_COLS:
        sub[c] = pd.to_numeric(sub[c], errors="coerce").fillna(0).astype("int8")

    df = res.merge(sub, on="numero_processo", how="left")

    for c in SUBS_COLS:
        df[c] = df[c].fillna(0).astype("int8")

    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona derivados: subs_total, faixa_valor, faixa_completude."""
    df = df.copy()
    df["subs_total"] = df[SUBS_COLS].sum(axis=1).astype("int8")

    df["faixa_valor"] = pd.cut(
        df["valor_causa"],
        bins=[0, 5000, 15000, float("inf")],
        labels=["Baixo", "Médio", "Alto"],
    )
    df["faixa_completude"] = pd.cut(
        df["subs_total"],
        bins=[-1, 2, 4, 6],
        labels=["Frágil", "Parcial", "Sólida"],
    )
    return df


def build_and_save(xlsx_path=XLSX_BASE, out_path=CASOS_60K) -> pd.DataFrame:
    df = enrich(load_raw(xlsx_path))
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return df


if __name__ == "__main__":
    df = build_and_save()
    print(f"Salvo: {CASOS_60K}")
    print(f"Shape: {df.shape}")
    print(f"Colunas: {df.columns.tolist()}")
    print(df.head(3))
    print("\nSubs_total distribution:")
    print(df["subs_total"].value_counts().sort_index())
