"""
Carrega o modelo XGBoost treinado pela frente de algoritmo e aplica a política
de acordos descrita em docs/politica_acordo.md sobre os 60k casos reais.

Produz data/processed/politica_output.csv, consumido automaticamente pelo
dashboard via get_df_com_politica() quando o arquivo existe.

Artefatos esperados (vindos de origin/master, ignorados pelo git):
    artefatos/modelo_xgboost.pkl
    artefatos/features.json
    artefatos/metricas.json

Uso:
    python -m src.monitor.politica_xgboost
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from src.monitor.paths import CASOS_60K, DATA_PROCESSED, REPO_ROOT


ARTEFATOS_DIR = REPO_ROOT / "artefatos"
MODELO_PATH = ARTEFATOS_DIR / "modelo_xgboost.pkl"
FEATURES_PATH = ARTEFATOS_DIR / "features.json"
POLITICA_OUTPUT = DATA_PROCESSED / "politica_output.csv"

# Cluster de UF conforme scripts/01_prepare_data.py da frente de modelagem.
UFS_ALTO_RISCO = {"AM", "AP"}
UFS_MEDIO_RISCO = {"GO", "RS", "BA", "RJ", "ES", "DF", "AL", "SP", "PE"}
# BAIXO risco é o default (demais UFs).

# Mapa de colunas do parquet local (snake_case) para os nomes esperados pelo
# modelo (como foram treinadas). A ordem segue features.json.
MAPA_SUBSIDIOS = {
    "subs_contrato": "Contrato",
    "subs_extrato": "Extrato",
    "subs_comprovante": "Comprovante de crédito",
    "subs_dossie": "Dossiê",
    "subs_demonstrativo": "Demonstrativo de evolução da dívida",
    "subs_laudo": "Laudo referenciado",
}

# Fatores do acordo (fração do valor da causa), conforme politica_acordo.md §4.
FATOR_3_CRITICOS = 0.27
FATOR_2_CRITICOS = 0.30
FATOR_1_CRITICO = 0.33
FATOR_DOSSIE_NAO_CONFORME = 0.35

# Limiar de decisão do XGBoost quando há 2 subsídios críticos.
LIMIAR_ML = 0.50


def carregar_modelo():
    """Carrega o XGBClassifier serializado."""
    with open(MODELO_PATH, "rb") as f:
        return pickle.load(f)


def carregar_features() -> list[str]:
    """Lê a lista ordenada de 9 features do artefato features.json."""
    return json.loads(FEATURES_PATH.read_text())


def preparar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Transforma casos_60k nas 9 colunas que o modelo espera.

    Preserva a ordem exata declarada em artefatos/features.json.
    """
    features = carregar_features()
    out = pd.DataFrame(index=df.index)

    # 6 subsídios binários com os nomes originais do treino.
    for col_local, col_modelo in MAPA_SUBSIDIOS.items():
        out[col_modelo] = df[col_local].astype("int8")

    out["is_golpe"] = (df["sub_assunto"] == "Golpe").astype("int8")
    out["uf_alto"] = df["uf"].isin(UFS_ALTO_RISCO).astype("int8")
    out["uf_medio"] = df["uf"].isin(UFS_MEDIO_RISCO).astype("int8")

    return out[features]


def _fator_acordo(subs_criticos: np.ndarray, uf: np.ndarray) -> np.ndarray:
    """Fator (fração do valor da causa) aplicado a cada caso.

    Regras de docs/politica_acordo.md §4.2:
      - 3 críticos: 27% (banco forte, acordo mais baixo)
      - 2 críticos: 30%
      - 0-1 críticos: 33% (banco fraco)
      - UF alto risco: +2pp
      - UF baixo risco: -2pp
    """
    base = np.where(
        subs_criticos >= 3, FATOR_3_CRITICOS,
        np.where(subs_criticos == 2, FATOR_2_CRITICOS, FATOR_1_CRITICO),
    )
    ajuste = np.where(
        np.isin(uf, list(UFS_ALTO_RISCO)), 0.02,
        np.where(~np.isin(uf, list(UFS_ALTO_RISCO | UFS_MEDIO_RISCO)), -0.02, 0.0),
    )
    return base + ajuste


def aplicar_politica_xgboost(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica a política híbrida (matriz + ML) sobre casos_60k.

    Retorna DataFrame com as 4 colunas consumidas pelo dashboard:
      numero_processo, acao_recomendada, valor_acordo_recomendado, score_confianca
    """
    modelo = carregar_modelo()
    X = preparar_features(df)

    # Probabilidade da classe positiva (acordo recomendado pelo ML).
    prob_acordo = modelo.predict_proba(X)[:, 1]

    subs_criticos = (
        df["subs_contrato"].astype("int8")
        + df["subs_extrato"].astype("int8")
        + df["subs_comprovante"].astype("int8")
    ).to_numpy()
    uf = df["uf"].to_numpy()

    # Matriz de decisão (politica_acordo.md §3.3):
    #   0-1 críticos -> ACORDO
    #   3 críticos   -> DEFESA
    #   2 críticos   -> ML decide (limiar 0.5)
    # Override: UF alto risco + <=2 críticos -> ACORDO.
    uf_alto = np.isin(uf, list(UFS_ALTO_RISCO))
    acao_ml = np.where(prob_acordo >= LIMIAR_ML, "acordo", "defesa")
    acao = np.where(
        subs_criticos <= 1, "acordo",
        np.where(subs_criticos >= 3, "defesa", acao_ml),
    )
    # Override UF alto risco
    acao = np.where((uf_alto) & (subs_criticos <= 2), "acordo", acao)

    fator = _fator_acordo(subs_criticos, uf)
    valor_acordo = np.where(
        acao == "acordo",
        (df["valor_causa"].to_numpy() * fator).round(2),
        np.nan,
    )

    # Confiança: para acordo usa prob_acordo; para defesa usa 1 - prob_acordo.
    score = np.where(acao == "acordo", prob_acordo, 1.0 - prob_acordo)

    return pd.DataFrame({
        "numero_processo": df["numero_processo"].to_numpy(),
        "acao_recomendada": acao,
        "valor_acordo_recomendado": valor_acordo,
        "score_confianca": score.round(4),
    })


def gerar_csv_politica(
    casos_path: Path = CASOS_60K,
    out_path: Path = POLITICA_OUTPUT,
) -> pd.DataFrame:
    """Pipeline completo: lê casos_60k, aplica política, salva CSV."""
    df = pd.read_parquet(casos_path)
    resultado = aplicar_politica_xgboost(df)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    resultado.to_csv(out_path, index=False)
    return resultado


def _imprimir_estatisticas(resultado: pd.DataFrame) -> None:
    """Resumo executivo do output para validação rápida."""
    n = len(resultado)
    dist_acao = resultado["acao_recomendada"].value_counts(normalize=True)
    print(f"Total de casos: {n:,}")
    print("\nDistribuição de recomendações:")
    for acao, pct in dist_acao.items():
        print(f"  {acao}: {pct:.2%} ({int(pct * n):,} casos)")

    acordos = resultado[resultado["acao_recomendada"] == "acordo"]
    if not acordos.empty:
        # fator = valor_acordo / valor_causa exige o parquet — aqui inferimos
        # pela distribuição do valor_acordo apenas
        print("\nEstatísticas do valor do acordo (somente onde aplicável):")
        print(f"  Média:    R$ {acordos['valor_acordo_recomendado'].mean():,.2f}")
        print(f"  Mediana:  R$ {acordos['valor_acordo_recomendado'].median():,.2f}")

    print(f"\nCSV salvo em: {POLITICA_OUTPUT}")


if __name__ == "__main__":
    if not MODELO_PATH.exists():
        raise SystemExit(
            f"Modelo nao encontrado em {MODELO_PATH}.\n"
            "Rode: git checkout origin/master -- artefatos/"
        )
    resultado = gerar_csv_politica()
    _imprimir_estatisticas(resultado)
