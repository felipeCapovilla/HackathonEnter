"""
Calcula e persiste o baseline pré-política a partir dos 60k reais.

Baseline = números de referência contra os quais toda métrica de efetividade
será comparada. Inclui volumetria, financeiro, completude × êxito e sub-assunto.

Saída: data/processed/baseline.json
"""
from __future__ import annotations

import json

import pandas as pd

from src.monitor.paths import BASELINE_JSON, CASOS_60K, DATA_PROCESSED


def _safe_mean(series: pd.Series) -> float:
    """Retorna NaN-safe mean como float; 0.0 se série vazia."""
    if series.empty:
        return 0.0
    v = series.mean()
    return 0.0 if pd.isna(v) else float(v)


def compute_baseline(df: pd.DataFrame) -> dict:
    exito = df["resultado_macro"] == "Êxito"
    nao_exito = df["resultado_macro"] == "Não Êxito"

    # Completude × êxito agrupado por subs_total
    g_comp = df.groupby("subs_total", observed=True).agg(
        n_casos=("numero_processo", "count"),
        taxa_exito=("resultado_macro", lambda s: (s == "Êxito").mean()),
    )

    # Sub-assunto (Golpe vs Genérico)
    g_sub = df.groupby("sub_assunto", observed=True).agg(
        n_casos=("numero_processo", "count"),
        taxa_exito=("resultado_macro", lambda s: (s == "Êxito").mean()),
    )

    # UF
    g_uf = df.groupby("uf", observed=True).agg(
        n_casos=("numero_processo", "count"),
        taxa_exito=("resultado_macro", lambda s: (s == "Êxito").mean()),
        valor_causa_medio=("valor_causa", "mean"),
        condenacao_media=("valor_condenacao", "mean"),
    )

    proc = df["resultado_micro"] == "Procedência"
    parc = df["resultado_micro"] == "Parcial procedência"
    acordo = df["resultado_micro"] == "Acordo"

    baseline = {
        "volumetria": {
            "total_casos": int(len(df)),
            "taxa_exito_macro": float(exito.mean()),
            "taxa_nao_exito_macro": float(nao_exito.mean()),
            "dist_resultado_micro": df["resultado_micro"]
                .value_counts(normalize=True)
                .to_dict(),
            "contagem_resultado_micro": df["resultado_micro"]
                .value_counts()
                .to_dict(),
        },
        "financeiro": {
            "valor_causa_medio": float(df["valor_causa"].mean()),
            "valor_causa_mediano": float(df["valor_causa"].median()),
            "condenacao_media_geral": float(df["valor_condenacao"].mean()),
            "condenacao_media_procedencia": _safe_mean(df.loc[proc, "valor_condenacao"]),
            "condenacao_media_parcial": _safe_mean(df.loc[parc, "valor_condenacao"]),
            "valor_medio_acordo": _safe_mean(df.loc[acordo, "valor_condenacao"]),
            "custo_total_estimado": float(df["valor_condenacao"].sum()),
        },
        "completude_vs_exito": {
            str(k): {
                "n_casos": int(row["n_casos"]),
                "taxa_exito": float(row["taxa_exito"]),
            }
            for k, row in g_comp.iterrows()
        },
        "sub_assunto": {
            str(k): {
                "n_casos": int(row["n_casos"]),
                "taxa_exito": float(row["taxa_exito"]),
            }
            for k, row in g_sub.iterrows()
        },
        "por_uf": {
            str(k): {
                "n_casos": int(row["n_casos"]),
                "taxa_exito": float(row["taxa_exito"]),
                "valor_causa_medio": float(row["valor_causa_medio"]),
                "condenacao_media": float(row["condenacao_media"]),
            }
            for k, row in g_uf.iterrows()
        },
    }
    return baseline


def build_and_save(
    casos_path=CASOS_60K,
    out_path=BASELINE_JSON,
) -> dict:
    df = pd.read_parquet(casos_path)
    baseline = compute_baseline(df)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False))
    return baseline


if __name__ == "__main__":
    b = build_and_save()
    vol = b["volumetria"]
    fin = b["financeiro"]
    print(f"Total casos: {vol['total_casos']:,}")
    print(f"Taxa êxito macro: {vol['taxa_exito_macro']:.2%}")
    print(f"% Acordo atual: {vol['dist_resultado_micro'].get('Acordo', 0):.3%}")
    print(f"Valor causa médio: R$ {fin['valor_causa_medio']:,.2f}")
    print(f"Condenação média: R$ {fin['condenacao_media_geral']:,.2f}")
    print(f"Custo total estimado: R$ {fin['custo_total_estimado']/1e6:.1f}M")
    print(f"\nSalvo: {BASELINE_JSON}")
