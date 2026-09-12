"""
Motor contrafactual: simula qual teria sido o custo total se a política
tivesse operado retroativamente sobre os 60k reais.

Produz o insumo da métrica E02 (Economia Total vs Baseline).

Assunções centrais (ver docs/DECISOES.md):
- H1: prob_aceita = 0.40 (parametrizável)
- H2: valor de acordo recomendado = 30% do valor da causa (mock)
       Fonte única: gerar_sintetico.ACORDO_PCT_CAUSA (importado abaixo)
- H3: acordo se subs_total <= 3, senão defesa (mock)
- H4: quando política recomenda defesa, custo esperado = valor_condenacao
  (a política não altera o resultado de uma defesa, só seleciona quais casos defender)

Tudo vetorizado com np.where / máscaras booleanas: <1s em 60k linhas.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.monitor.gerar_sintetico import ACORDO_PCT_CAUSA as MOCK_ACORDO_PCT_CAUSA
from src.monitor.paths import CASOS_60K


ACAO_ACORDO = "acordo"
ACAO_DEFESA = "defesa"

# Assunção H2: limiar de subs_total para recomendar acordo no mock.
MOCK_SUBS_LIMIAR = 3

PROBS_SENSIBILIDADE_DEFAULT = (0.3, 0.5, 0.7, 0.9)


def custo_caso_sob_politica(
    df: pd.DataFrame,
    acao_col: str = "acao_recomendada_mock",
    valor_acordo_col: str = "valor_acordo_recomendado_mock",
    prob_aceita: float = 0.40,
) -> pd.Series:
    """Custo esperado por caso sob a política (vetorizado, sem apply/iterrows)."""
    acao = df[acao_col].astype(str).str.lower().str.strip()
    valor_condenacao = df["valor_condenacao"].to_numpy(dtype=float)
    valor_acordo = df[valor_acordo_col].to_numpy(dtype=float)

    # H4: defesa -> custo observado (valor_condenacao)
    # acordo -> p * acordo + (1-p) * condenacao
    custo_acordo = prob_aceita * valor_acordo + (1.0 - prob_aceita) * valor_condenacao
    is_acordo = (acao == ACAO_ACORDO).to_numpy()
    custo = np.where(is_acordo, custo_acordo, valor_condenacao)
    return pd.Series(custo, index=df.index, name="custo_politica")


def simular_politica(
    df: pd.DataFrame,
    acao_col: str = "acao_recomendada_mock",
    valor_acordo_col: str = "valor_acordo_recomendado_mock",
    prob_aceita: float = 0.40,
) -> dict:
    """Compara custo observado vs custo sob política e retorna totais."""
    n = int(len(df))
    if n == 0:
        return {
            "custo_observado_total": 0.0,
            "custo_politica_total": 0.0,
            "economia_total": 0.0,
            "economia_percentual": 0.0,
            "economia_por_caso": 0.0,
            "n_casos": 0,
            "prob_aceita_assumida": float(prob_aceita),
        }

    custo_obs = df["valor_condenacao"].to_numpy(dtype=float)
    custo_pol = custo_caso_sob_politica(
        df, acao_col=acao_col, valor_acordo_col=valor_acordo_col, prob_aceita=prob_aceita
    ).to_numpy(dtype=float)

    custo_obs_total = float(custo_obs.sum())
    custo_pol_total = float(custo_pol.sum())
    economia = custo_obs_total - custo_pol_total

    return {
        "custo_observado_total": custo_obs_total,
        "custo_politica_total": custo_pol_total,
        "economia_total": economia,
        "economia_percentual": economia / custo_obs_total if custo_obs_total else 0.0,
        "economia_por_caso": economia / n,
        "n_casos": n,
        "prob_aceita_assumida": float(prob_aceita),
    }


def simular_sensibilidade(
    df: pd.DataFrame,
    acao_col: str = "acao_recomendada_mock",
    valor_acordo_col: str = "valor_acordo_recomendado_mock",
    probs: tuple[float, ...] | list[float] | None = None,
) -> pd.DataFrame:
    """Varre prob_aceita e devolve tabela de sensibilidade (uma linha por p)."""
    probs_iter = tuple(probs) if probs is not None else PROBS_SENSIBILIDADE_DEFAULT
    linhas = [
        simular_politica(
            df,
            acao_col=acao_col,
            valor_acordo_col=valor_acordo_col,
            prob_aceita=float(p),
        )
        for p in probs_iter
    ]
    out = pd.DataFrame(linhas)
    return out[
        [
            "prob_aceita_assumida",
            "n_casos",
            "custo_observado_total",
            "custo_politica_total",
            "economia_total",
            "economia_percentual",
            "economia_por_caso",
        ]
    ]


def aplicar_politica_mock(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica H2+H3 vetorialmente e adiciona colunas acao/valor recomendados."""
    out = df.copy()
    subs_total = out["subs_total"].to_numpy()
    valor_causa = out["valor_causa"].to_numpy(dtype=float)

    is_acordo = subs_total <= MOCK_SUBS_LIMIAR
    out["acao_recomendada_mock"] = np.where(is_acordo, ACAO_ACORDO, ACAO_DEFESA)
    # Valor de acordo: 30% do valor da causa para todos os casos (só é usado quando acao==acordo)
    out["valor_acordo_recomendado_mock"] = (valor_causa * MOCK_ACORDO_PCT_CAUSA).round(2)
    return out


if __name__ == "__main__":
    df = pd.read_parquet(CASOS_60K)
    df = aplicar_politica_mock(df)
    resultado = simular_politica(df)
    print("=== simular_politica (prob_aceita=0.40) ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    print("\n=== simular_sensibilidade ===")
    sens = simular_sensibilidade(df)
    print(sens.to_string(index=False))
