"""
Métricas de aderência (A01–A20) sobre o Conjunto B (casos_enriquecidos).

Prioriza as métricas P0 do catálogo do guia de implementação. Todas as funções
recebem `df: pd.DataFrame` já enriquecido e retornam float, pd.Series,
pd.DataFrame ou list[dict].
"""
from __future__ import annotations

import pandas as pd

from src.monitor.paths import CASOS_ENRIQUECIDOS


# ==================== P0 — Métricas críticas ====================

def taxa_seguimento_global(df: pd.DataFrame) -> float:
    """A01 — % casos em que acao_tomada == acao_recomendada."""
    return float(df["aderente"].mean())


def taxa_override(df: pd.DataFrame) -> float:
    """A02 — complemento da A01."""
    return 1.0 - taxa_seguimento_global(df)


def distribuicao_acao(df: pd.DataFrame) -> pd.DataFrame:
    """A03 — distribuição de acao_recomendada vs acao_tomada."""
    rec = df["acao_recomendada"].value_counts(normalize=True).rename("recomendada")
    tom = df["acao_tomada"].value_counts(normalize=True).rename("tomada")
    return pd.concat([rec, tom], axis=1).fillna(0.0)


def aderencia_por_advogado(df: pd.DataFrame) -> pd.DataFrame:
    """A05 — ranking de aderência por advogado.

    Quando as colunas `advogado_nome` / `numero_oab` / `escritorio_nome` existem
    no df (datasets gerados a partir de `gerar_sintetico.build`), elas são
    preservadas no ranking para que o dashboard exiba o nome próprio ao lado do
    ID. Mantém compatibilidade com dataframes mínimos usados nos testes.
    """
    agg = {
        "aderencia": ("aderente", "mean"),
        "n_casos": ("numero_processo", "count"),
        "escritorio": ("escritorio_id", "first"),
    }
    if "advogado_nome" in df.columns:
        agg["advogado_nome"] = ("advogado_nome", "first")
    if "numero_oab" in df.columns:
        agg["numero_oab"] = ("numero_oab", "first")
    if "escritorio_nome" in df.columns:
        agg["escritorio_nome"] = ("escritorio_nome", "first")

    return (
        df.groupby("advogado_id")
        .agg(**agg)
        .sort_values("aderencia")
    )


def aderencia_por_escritorio(df: pd.DataFrame) -> pd.DataFrame:
    """A06 — ranking de aderência por escritório.

    Inclui `escritorio_nome` e `cidade_sede_escritorio` quando presentes, para
    rotulagem humana no dashboard sem alterar a lógica de agregação.
    """
    agg = {
        "aderencia": ("aderente", "mean"),
        "n_casos": ("numero_processo", "count"),
        "n_advogados": ("advogado_id", "nunique"),
    }
    if "escritorio_nome" in df.columns:
        agg["escritorio_nome"] = ("escritorio_nome", "first")
    if "cidade_sede_escritorio" in df.columns:
        agg["cidade_sede"] = ("cidade_sede_escritorio", "first")

    return (
        df.groupby("escritorio_id")
        .agg(**agg)
        .sort_values("aderencia")
    )


def aderencia_por_uf(df: pd.DataFrame) -> pd.Series:
    """A07 — aderência por UF."""
    return df.groupby("uf")["aderente"].mean().sort_values()


def aderencia_por_faixa_valor(df: pd.DataFrame) -> pd.Series:
    """A08 — aderência por faixa de valor (detecta viés em casos caros)."""
    return df.groupby("faixa_valor", observed=False)["aderente"].mean()


def aderencia_por_faixa_completude(df: pd.DataFrame) -> pd.Series:
    """A04 — aderência por faixa de completude probatória."""
    return df.groupby("faixa_completude", observed=False)["aderente"].mean()


def aderencia_por_subassunto(df: pd.DataFrame) -> pd.Series:
    """A09 — aderência por sub-assunto (Golpe vs Genérico)."""
    return df.groupby("sub_assunto")["aderente"].mean()


def desvio_valor_acordo(df: pd.DataFrame) -> dict:
    """A10/A11 — desvio entre valor proposto e recomendado em acordos."""
    mask = (
        (df["acao_tomada"] == "acordo")
        & df["valor_acordo_proposto"].notna()
        & df["valor_acordo_recomendado"].notna()
    )
    sub = df.loc[mask]
    if sub.empty:
        return {"n": 0}

    desvio_abs = sub["valor_acordo_proposto"] - sub["valor_acordo_recomendado"]
    desvio_rel = desvio_abs / sub["valor_acordo_recomendado"]
    return {
        "n": int(len(sub)),
        "desvio_rel_medio": float(desvio_rel.mean()),
        "desvio_rel_mediano": float(desvio_rel.median()),
        "desvio_abs_p95": float(desvio_abs.quantile(0.95)),
    }


def distribuicao_razoes_override(df: pd.DataFrame) -> pd.Series:
    """A13 — distribuição das razões de override."""
    return (
        df.loc[df["aderente"] == 0, "razao_override"]
        .value_counts(normalize=True)
    )


def tempo_decisao_percentis(df: pd.DataFrame) -> dict:
    """A15 — percentis do tempo até decisão (minutos)."""
    t = df["tempo_decisao_min"]
    return {
        "p10_min": float(t.quantile(0.10)),
        "mediana_min": float(t.median()),
        "p90_min": float(t.quantile(0.90)),
        "pct_abaixo_5min": float((t < 5).mean()),
        "pct_acima_48h": float((t > 2880).mean()),
    }


def drift_temporal_aderencia(df: pd.DataFrame, freq: str = "ME") -> pd.Series:
    """A18 — série mensal da taxa de aderência (freq=ME, fim de mês)."""
    return (
        df.set_index("data_decisao")["aderente"]
        .resample(freq)
        .mean()
    )


def aderencia_ponderada_por_valor(df: pd.DataFrame) -> float:
    """A20 — aderência ponderada pelo valor da causa (R$ seguindo / R$ total)."""
    total = float(df["valor_causa"].sum())
    if total == 0:
        return 0.0
    return float((df["aderente"] * df["valor_causa"]).sum() / total)


# ==================== Alertas P0 ====================

def alertas_ativos(df: pd.DataFrame) -> list[dict]:
    """Avalia thresholds P0 e retorna lista de alertas ativos."""
    alertas: list[dict] = []

    tsg = taxa_seguimento_global(df)
    if tsg < 0.70:
        alertas.append({
            "id": "A01",
            "nome": "Taxa de Seguimento Global",
            "severidade": "P0",
            "valor": tsg,
            "threshold": 0.70,
            "mensagem": f"Taxa de seguimento em {tsg:.1%} (mínimo 70%)",
        })

    tov = taxa_override(df)
    if tov > 0.30:
        alertas.append({
            "id": "A02",
            "nome": "Taxa de Override",
            "severidade": "P0",
            "valor": tov,
            "threshold": 0.30,
            "mensagem": f"Taxa de override em {tov:.1%} (máximo 30%)",
        })

    por_adv = aderencia_por_advogado(df)
    for adv_id, row in por_adv[por_adv["aderencia"] < 0.60].iterrows():
        # Usa nome próprio quando disponível (gerar_sintetico populou as
        # colunas advogado_nome / escritorio_nome); fallback pro ID em
        # datasets mais simples (df_mini dos testes).
        adv_label = row["advogado_nome"] if "advogado_nome" in row and row["advogado_nome"] else adv_id
        esc_label = (
            row["escritorio_nome"] if "escritorio_nome" in row and row["escritorio_nome"]
            else row.get("escritorio", "")
        )
        alertas.append({
            "id": "A05",
            "nome": f"Aderência individual crítica — {adv_label}",
            "severidade": "P0",
            "valor": float(row["aderencia"]),
            "threshold": 0.60,
            "mensagem": (
                f"{adv_label} ({esc_label}) em {row['aderencia']:.1%} — "
                "requer intervenção"
            ),
        })

    por_faixa = aderencia_por_faixa_valor(df)
    if "Alto" in por_faixa.index and por_faixa["Alto"] < 0.70:
        alertas.append({
            "id": "A08",
            "nome": "Aderência em casos de alto valor",
            "severidade": "P0",
            "valor": float(por_faixa["Alto"]),
            "threshold": 0.70,
            "mensagem": (
                f"Aderência em faixa Alto: {por_faixa['Alto']:.1%} — possível viés"
            ),
        })

    return alertas


if __name__ == "__main__":
    df = pd.read_parquet(CASOS_ENRIQUECIDOS)

    print(f"Taxa de seguimento global: {taxa_seguimento_global(df):.2%}")
    print(f"Taxa de override:          {taxa_override(df):.2%}")
    print(f"Aderência ponderada (R$):  {aderencia_ponderada_por_valor(df):.2%}")

    print("\nDistribuição ação (recomendada vs tomada):")
    print(distribuicao_acao(df))

    print("\nAderência por escritório:")
    print(aderencia_por_escritorio(df))

    print("\nAderência por faixa de valor:")
    print(aderencia_por_faixa_valor(df))

    print("\nAderência por faixa de completude:")
    print(aderencia_por_faixa_completude(df))

    print("\nRazões de override:")
    print(distribuicao_razoes_override(df))

    print("\nTempo de decisão (percentis):")
    print(tempo_decisao_percentis(df))

    print("\nDrift temporal (mensal):")
    print(drift_temporal_aderencia(df))

    print("\nAlertas ativos:")
    for a in alertas_ativos(df):
        print(f"  [{a['severidade']}] {a['mensagem']}")
