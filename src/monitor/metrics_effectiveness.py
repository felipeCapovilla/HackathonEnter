"""
Métricas de efetividade E01-E20 (prioridade P0) do catálogo do monitoramento.

Cada função é pura: recebe df (e opcionalmente baseline dict) e retorna
float / pd.Series / pd.DataFrame / dict. Tudo vetorizado.

Referência do guia: Passo 8, linhas 953-961 do guia-implementacao-monitoramento.md.

Observação sobre resultado_negociacao (E04): o dataset casos_60k não contém
esse campo (é atributo de casos_enriquecidos). Aqui reportamos a taxa de
aceitação como a assunção H1 (prob_aceita) explicitamente marcada como "assumida".
Quando a frente de aderência integrar casos_enriquecidos, sobrescrevemos.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.monitor import counterfactual
from src.monitor.paths import BASELINE_JSON, CASOS_60K


# ---------- Helpers ----------

def _ensure_politica_aplicada(
    df: pd.DataFrame,
    acao_col: str = "acao_recomendada_mock",
    valor_acordo_col: str = "valor_acordo_recomendado_mock",
) -> pd.DataFrame:
    """Aplica o mock se as colunas da política não existirem."""
    if acao_col not in df.columns or valor_acordo_col not in df.columns:
        return counterfactual.aplicar_politica_mock(df)
    return df


# ---------- E02: Economia Total vs Baseline ----------

def economia_total_vs_baseline(
    df: pd.DataFrame,
    baseline: dict | None = None,
    acao_col: str = "acao_recomendada_mock",
    valor_acordo_col: str = "valor_acordo_recomendado_mock",
    prob_aceita: float = 0.40,
) -> dict:
    """E02 — economia total (R$) e percentual vs baseline."""
    df = _ensure_politica_aplicada(df, acao_col, valor_acordo_col)
    sim = counterfactual.simular_politica(
        df, acao_col=acao_col, valor_acordo_col=valor_acordo_col, prob_aceita=prob_aceita
    )
    baseline_total = (
        float(baseline["financeiro"]["custo_total_estimado"])
        if baseline else sim["custo_observado_total"]
    )
    return {
        "baseline_custo_total": baseline_total,
        "custo_politica_total": sim["custo_politica_total"],
        "economia_total": baseline_total - sim["custo_politica_total"],
        "economia_percentual": (
            (baseline_total - sim["custo_politica_total"]) / baseline_total
            if baseline_total else 0.0
        ),
        "prob_aceita_assumida": sim["prob_aceita_assumida"],
    }


# ---------- E03: Custo médio por caso sob política ----------

def custo_medio_por_caso_politica(
    df: pd.DataFrame,
    acao_col: str = "acao_recomendada_mock",
    valor_acordo_col: str = "valor_acordo_recomendado_mock",
    prob_aceita: float = 0.40,
) -> float:
    """E03 — custo médio esperado por caso sob a política."""
    df = _ensure_politica_aplicada(df, acao_col, valor_acordo_col)
    if len(df) == 0:
        return 0.0
    custo = counterfactual.custo_caso_sob_politica(
        df, acao_col=acao_col, valor_acordo_col=valor_acordo_col, prob_aceita=prob_aceita
    )
    return float(custo.mean())


# ---------- E04: Taxa de aceitação de acordo ----------

def taxa_aceitacao_acordo(
    df: pd.DataFrame,
    resultado_col: str = "resultado_negociacao",
    prob_aceita_assumida: float = 0.40,
) -> dict:
    """E04 — taxa real de aceitação se a coluna existir, senão a assunção H1."""
    if resultado_col in df.columns:
        s = df[resultado_col].astype(str).str.lower().str.strip()
        mask_valid = s.isin(["aceito", "recusado", "aceita", "recusada"])
        if mask_valid.any():
            aceitos = s.isin(["aceito", "aceita"]).sum()
            total = int(mask_valid.sum())
            return {
                "fonte": "observada",
                "taxa_aceitacao": float(aceitos / total) if total else 0.0,
                "n_negociacoes": total,
            }
    return {
        "fonte": "assumida_H1",
        "taxa_aceitacao": float(prob_aceita_assumida),
        "n_negociacoes": 0,
    }


# ---------- E05: Redistribuição do resultado_micro antes vs depois ----------

def redistribuicao_resultado_micro(
    df: pd.DataFrame,
    baseline: dict,
    acao_col: str = "acao_recomendada_mock",
    prob_aceita: float = 0.40,
) -> pd.DataFrame:
    """E05 — compara distribuição de resultado_micro antes (baseline) e depois (política).

    Estimativa pós-política (vetorizada):
    - Casos onde política recomenda acordo e aceita (prob_aceita) -> 'Acordo'
    - Casos onde política recomenda acordo e recusa (1-prob_aceita) -> mantém resultado_micro real
    - Casos onde política recomenda defesa -> mantém resultado_micro real
    """
    df = _ensure_politica_aplicada(df, acao_col)
    n = len(df)
    if n == 0:
        return pd.DataFrame(columns=["resultado_micro", "antes_pct", "depois_pct", "delta_pp"])

    # Distribuição real (antes)
    antes = df["resultado_micro"].value_counts(normalize=True)

    # Pós-política: acordo+aceito vira "Acordo", senão mantém resultado_micro real.
    # peso_acordo_efetivo = prob_aceita quando acao == acordo
    is_acordo_pol = (df[acao_col].astype(str).str.lower() == "acordo").to_numpy()
    peso_vira_acordo = np.where(is_acordo_pol, prob_aceita, 0.0)
    peso_mantem = 1.0 - peso_vira_acordo

    # Agrega: para cada categoria original, soma peso_mantem dos casos com aquela categoria
    tmp = pd.DataFrame({
        "resultado_micro": df["resultado_micro"].to_numpy(),
        "peso_mantem": peso_mantem,
        "peso_acordo": peso_vira_acordo,
    })
    depois = (
        tmp.groupby("resultado_micro", observed=True)["peso_mantem"].sum() / n
    )
    depois = depois.add(
        pd.Series({"Acordo": float(tmp["peso_acordo"].sum() / n)}), fill_value=0.0
    )

    # Usa baseline como fonte de "antes" se fornecido, senão usa do df
    if baseline and "dist_resultado_micro" in baseline.get("volumetria", {}):
        antes = pd.Series(baseline["volumetria"]["dist_resultado_micro"])

    idx = sorted(set(antes.index).union(depois.index))
    out = pd.DataFrame({
        "resultado_micro": idx,
        "antes_pct": [float(antes.get(k, 0.0)) for k in idx],
        "depois_pct": [float(depois.get(k, 0.0)) for k in idx],
    })
    out["delta_pp"] = (out["depois_pct"] - out["antes_pct"]) * 100.0
    return out.sort_values("depois_pct", ascending=False).reset_index(drop=True)


# ---------- E06: Custo por faixa de completude ----------

def custo_por_faixa_completude(
    df: pd.DataFrame,
    acao_col: str = "acao_recomendada_mock",
    valor_acordo_col: str = "valor_acordo_recomendado_mock",
    prob_aceita: float = 0.40,
) -> pd.DataFrame:
    """E06 — custo observado vs política agregado por faixa_completude."""
    df = _ensure_politica_aplicada(df, acao_col, valor_acordo_col)
    if len(df) == 0:
        return pd.DataFrame(
            columns=["faixa_completude", "n_casos", "custo_observado", "custo_politica", "economia"]
        )
    custo_pol = counterfactual.custo_caso_sob_politica(
        df, acao_col=acao_col, valor_acordo_col=valor_acordo_col, prob_aceita=prob_aceita
    )
    tmp = df.assign(custo_politica=custo_pol.to_numpy())
    g = tmp.groupby("faixa_completude", observed=True).agg(
        n_casos=("numero_processo", "count"),
        custo_observado=("valor_condenacao", "sum"),
        custo_politica=("custo_politica", "sum"),
    )
    g["economia"] = g["custo_observado"] - g["custo_politica"]
    return g.reset_index()


# ---------- E07: Recall em casos de alta perda ----------

def recall_alta_perda(
    df: pd.DataFrame,
    acao_col: str = "acao_recomendada_mock",
    decil: float = 0.90,
) -> dict:
    """E07 — dos casos no top decil de valor_condenacao, quantos a política recomendou acordo."""
    df = _ensure_politica_aplicada(df, acao_col)
    if len(df) == 0:
        return {"decil": decil, "threshold": 0.0, "n_alta_perda": 0, "n_recomendou_acordo": 0, "recall": 0.0}
    threshold = float(df["valor_condenacao"].quantile(decil))
    mask_alta = df["valor_condenacao"] >= threshold
    n_alta = int(mask_alta.sum())
    is_acordo = df[acao_col].astype(str).str.lower() == "acordo"
    n_acordo_na_alta = int((mask_alta & is_acordo).sum())
    return {
        "decil": float(decil),
        "threshold": threshold,
        "n_alta_perda": n_alta,
        "n_recomendou_acordo": n_acordo_na_alta,
        "recall": (n_acordo_na_alta / n_alta) if n_alta else 0.0,
    }


# ---------- E08: Precision de defesa ----------

def precision_defesa(
    df: pd.DataFrame,
    acao_col: str = "acao_recomendada_mock",
) -> dict:
    """E08 — dos casos em que política recomendou defesa, quantos foram Êxito real."""
    df = _ensure_politica_aplicada(df, acao_col)
    if len(df) == 0:
        return {"n_defesa": 0, "n_exito": 0, "precision": 0.0}
    is_defesa = (df[acao_col].astype(str).str.lower() == "defesa")
    n_def = int(is_defesa.sum())
    if n_def == 0:
        return {"n_defesa": 0, "n_exito": 0, "precision": 0.0}
    exito_mask = df["resultado_macro"] == "Êxito"
    n_exito = int((is_defesa & exito_mask).sum())
    return {
        "n_defesa": n_def,
        "n_exito": n_exito,
        "precision": n_exito / n_def,
    }


# ---------- E09: Economia acumulada temporal ----------

def economia_acumulada_temporal(
    df: pd.DataFrame,
    acao_col: str = "acao_recomendada_mock",
    valor_acordo_col: str = "valor_acordo_recomendado_mock",
    prob_aceita: float = 0.40,
    data_col: str = "data_decisao",
    n_meses: int = 12,
    seed: int = 42,
) -> pd.DataFrame:
    """E09 — série mensal de economia acumulada.

    Se data_col não existir, distribui casos uniformemente nos últimos n_meses.
    """
    df = _ensure_politica_aplicada(df, acao_col, valor_acordo_col)
    if len(df) == 0:
        return pd.DataFrame(columns=["mes", "economia_mes", "economia_acumulada"])

    custo_pol = counterfactual.custo_caso_sob_politica(
        df, acao_col=acao_col, valor_acordo_col=valor_acordo_col, prob_aceita=prob_aceita
    ).to_numpy(dtype=float)
    economia_caso = df["valor_condenacao"].to_numpy(dtype=float) - custo_pol

    if data_col in df.columns:
        mes = pd.to_datetime(df[data_col], errors="coerce").dt.to_period("M").astype(str)
    else:
        rng = np.random.default_rng(seed)
        idx_mes = rng.integers(0, n_meses, size=len(df))
        base = pd.Timestamp.today().to_period("M")
        mes = pd.Series(
            [str((base - int(n_meses - 1 - i))) for i in idx_mes],
            index=df.index,
        )

    tmp = pd.DataFrame({"mes": mes.to_numpy(), "economia_mes": economia_caso})
    agg = tmp.groupby("mes", observed=True)["economia_mes"].sum().sort_index()
    out = agg.reset_index()
    out["economia_acumulada"] = out["economia_mes"].cumsum()
    return out


# ---------- E10: Distribuição dos valores de acordo ----------

def distribuicao_valores_acordo(
    df: pd.DataFrame,
    acao_col: str = "acao_recomendada_mock",
    valor_acordo_col: str = "valor_acordo_recomendado_mock",
) -> dict:
    """E10 — estatísticas descritivas dos valores de acordo recomendados."""
    df = _ensure_politica_aplicada(df, acao_col, valor_acordo_col)
    mask_acordo = df[acao_col].astype(str).str.lower() == "acordo"
    valores = df.loc[mask_acordo, valor_acordo_col].astype(float)
    if valores.empty:
        return {"n": 0, "mean": 0.0, "median": 0.0, "p25": 0.0, "p75": 0.0, "min": 0.0, "max": 0.0}
    return {
        "n": int(valores.shape[0]),
        "mean": float(valores.mean()),
        "median": float(valores.median()),
        "p25": float(valores.quantile(0.25)),
        "p75": float(valores.quantile(0.75)),
        "min": float(valores.min()),
        "max": float(valores.max()),
    }


# ---------- Main demo ----------

def _print_section(titulo: str) -> None:
    print(f"\n=== {titulo} ===")


if __name__ == "__main__":
    df = pd.read_parquet(CASOS_60K)
    df = counterfactual.aplicar_politica_mock(df)
    baseline = json.loads(BASELINE_JSON.read_text())

    _print_section("E02 — Economia total vs baseline")
    print(json.dumps(economia_total_vs_baseline(df, baseline), indent=2, ensure_ascii=False))

    _print_section("E03 — Custo médio por caso (política)")
    print(f"R$ {custo_medio_por_caso_politica(df):,.2f}")

    _print_section("E04 — Taxa de aceitação de acordo")
    print(json.dumps(taxa_aceitacao_acordo(df), indent=2, ensure_ascii=False))

    _print_section("E05 — Redistribuição resultado_micro")
    print(redistribuicao_resultado_micro(df, baseline).to_string(index=False))

    _print_section("E06 — Custo por faixa de completude")
    print(custo_por_faixa_completude(df).to_string(index=False))

    _print_section("E07 — Recall em alta perda (top decil)")
    print(json.dumps(recall_alta_perda(df), indent=2, ensure_ascii=False))

    _print_section("E08 — Precision de defesa")
    print(json.dumps(precision_defesa(df), indent=2, ensure_ascii=False))

    _print_section("E09 — Economia acumulada (12 meses)")
    print(economia_acumulada_temporal(df).to_string(index=False))

    _print_section("E10 — Distribuição dos valores de acordo")
    print(json.dumps(distribuicao_valores_acordo(df), indent=2, ensure_ascii=False))
