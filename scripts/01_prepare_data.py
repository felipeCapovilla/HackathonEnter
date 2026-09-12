"""
===============================================================
PIPELINE 01 — PREPARAÇÃO DOS DADOS (versão FINAL)
===============================================================
Features finais (9 no total):
  - 6 subsídios binários (Contrato, Extrato, Comprovante BACEN,
    Dossiê, Demonstrativo, Laudo)
  - is_golpe (sub-assunto binarizado)
  - uf_alto, uf_medio (cluster UF one-hot; BAIXO é baseline)

Decisões de modelagem:
  - SEM qtd_criticos (redundante com os subsídios individuais;
    testado empiricamente: AUC/Brier idênticos com ou sem ela)
  - SEM valor da causa e faixas (baixa importância, ruído)
  - Dossiê continua binário (conformidade será tratada pelo
    agente LLM via override, não pelo modelo)
===============================================================
"""
import argparse
import json
from pathlib import Path

import pandas as pd
import numpy as np


# ---------- CONFIGURAÇÃO CENTRAL ----------

SUBSIDIOS = [
    'Contrato',
    'Extrato',
    'Comprovante de crédito',
    'Dossiê',
    'Demonstrativo de evolução da dívida',
    'Laudo referenciado',
]
SUBSIDIOS_CRITICOS = ['Contrato', 'Extrato', 'Comprovante de crédito']

# UFs agrupadas por cluster de risco (derivado da taxa de êxito histórica)
CLUSTER_UF = {
    # ALTO risco (êxito < 60%)
    'AM': 'ALTO', 'AP': 'ALTO',
    # MÉDIO risco (60-70%)
    'GO': 'MEDIO', 'RS': 'MEDIO', 'BA': 'MEDIO', 'RJ': 'MEDIO',
    'ES': 'MEDIO', 'DF': 'MEDIO', 'AL': 'MEDIO', 'SP': 'MEDIO',
    'PE': 'MEDIO',
    # BAIXO risco: default (demais UFs)
}

# Rotulamento econômico
THRESHOLD_ACORDO_PCT_CAUSA = 0.40


# ---------- FUNÇÕES ----------

def carregar_base(caminho_xlsx: str) -> pd.DataFrame:
    resultados = pd.read_excel(caminho_xlsx, sheet_name='Resultados dos processos')
    subsidios = pd.read_excel(caminho_xlsx, sheet_name='Subsídios disponibilizados', header=1)
    subsidios = subsidios.rename(columns={subsidios.columns[0]: 'Número do processo'})
    df = resultados.merge(subsidios, on='Número do processo', how='left')
    print(f"[carregar_base] Base unificada: {df.shape[0]} processos")
    return df


def rotular(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rotulamento econômico:
      ACORDO = banco pagou > 30% da causa (teria sido melhor acordar)
      DEFESA = banco ganhou ou pagou pouco (defesa foi correta)
    """
    custo_hipotetico = THRESHOLD_ACORDO_PCT_CAUSA * df['Valor da causa']
    df['label'] = np.where(
        df['Valor da condenação/indenização'] > custo_hipotetico,
        'ACORDO', 'DEFESA'
    )
    df['y'] = (df['label'] == 'ACORDO').astype(int)

    dist = df['label'].value_counts(normalize=True).round(3) * 100
    print(f"[rotular] DEFESA={dist.get('DEFESA', 0):.1f}% | "
          f"ACORDO={dist.get('ACORDO', 0):.1f}%")
    return df


def criar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Feature engineering — apenas variáveis não redundantes."""
    df['cluster_uf'] = df['UF'].map(CLUSTER_UF).fillna('BAIXO')
    df['is_golpe'] = (df['Sub-assunto'] == 'Golpe').astype(int)
    return df


def selecionar_features_modelo(df: pd.DataFrame) -> tuple:
    """X com 9 features, y binário."""
    num_feats = SUBSIDIOS + ['is_golpe']
    X = df[num_feats].copy()
    X['uf_alto'] = (df['cluster_uf'] == 'ALTO').astype(int)
    X['uf_medio'] = (df['cluster_uf'] == 'MEDIO').astype(int)
    y = df['y']
    print(f"[selecionar_features] X.shape = {X.shape}")
    return X, y


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='data/Hackaton_Enter_Base_Candidatos.xlsx')
    parser.add_argument('--output', default='artefatos')
    args = parser.parse_args()

    outdir = Path(args.output)
    outdir.mkdir(exist_ok=True)

    df = carregar_base(args.input)
    df = rotular(df)
    df = criar_features(df)
    X, y = selecionar_features_modelo(df)

    X.to_pickle(outdir / 'X.pkl')
    y.to_frame('y').to_pickle(outdir / 'y.pkl')
    df.to_pickle(outdir / 'dataset_completo.pkl')

    with open(outdir / 'features.json', 'w') as f:
        json.dump(list(X.columns), f, indent=2)

    print(f"\n[OK] Artefatos em {outdir}/")
    print(f"  Features finais: {list(X.columns)}")


if __name__ == '__main__':
    main()
