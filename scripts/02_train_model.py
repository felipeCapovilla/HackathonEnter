"""
===============================================================
PIPELINE 02 — TREINO DO XGBOOST (versão refinada)
===============================================================
Mudanças principais:
  1. SEM scale_pos_weight — preserva calibração natural
  2. Adiciona Brier score como métrica primária
  3. Avaliação de calibração com calibration_curve
  4. Relatório de diagnóstico completo

Por que sem class weight?
  O desbalanceamento 70/30 não é severo a ponto de justificar truque.
  O scale_pos_weight melhora recall mas DISTORCE probabilidades —
  fundamental para o agente usar prob honestas ao explicar ao advogado.
===============================================================
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import joblib

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import (
    roc_auc_score, brier_score_loss, classification_report,
    confusion_matrix, log_loss
)
from sklearn.calibration import calibration_curve


# ---------- HIPERPARÂMETROS ----------
XGBOOST_PARAMS = {
    'n_estimators': 300,
    'max_depth': 5,
    'learning_rate': 0.08,
    'subsample': 0.85,
    'colsample_bytree': 0.85,
    'min_child_weight': 5,
    'reg_alpha': 0.1,
    'reg_lambda': 1.0,
    'objective': 'binary:logistic',
    'eval_metric': 'logloss',
    'random_state': 42,
    'n_jobs': -1,
    # IMPORTANTE: sem scale_pos_weight
}


# ---------- FUNÇÕES ----------

def carregar_dados(pasta: Path):
    X = pd.read_pickle(pasta / 'X.pkl')
    y = pd.read_pickle(pasta / 'y.pkl')['y']
    print(f"[carregar] X: {X.shape} | ACORDO: {y.mean()*100:.1f}%")
    return X, y


def cross_validation(X, y, params: dict, n_splits=5):
    """CV com AUC e Brier simultaneamente."""
    print(f"\n{'='*60}")
    print(f"CROSS-VALIDATION ({n_splits} folds)")
    print(f"{'='*60}")

    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    model = xgb.XGBClassifier(**params)

    auc_scores = cross_val_score(model, X, y, cv=cv, scoring='roc_auc', n_jobs=-1)
    brier_scores = -cross_val_score(model, X, y, cv=cv, scoring='neg_brier_score', n_jobs=-1)

    print(f"AUC:   {auc_scores.mean():.4f} ± {auc_scores.std():.4f}")
    print(f"Brier: {brier_scores.mean():.4f} ± {brier_scores.std():.4f}")
    print(f"       (Brier menor = probabilidades mais honestas; <0.15 é bom)")

    return {
        'auc_mean': float(auc_scores.mean()),
        'auc_std': float(auc_scores.std()),
        'brier_mean': float(brier_scores.mean()),
        'brier_std': float(brier_scores.std()),
    }


def avaliar(model, X_test, y_test) -> dict:
    """Avaliação completa no teste com foco em calibração."""
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    auc = roc_auc_score(y_test, y_proba)
    brier = brier_score_loss(y_test, y_proba)
    ll = log_loss(y_test, y_proba)
    acc = (y_pred == y_test).mean()
    cm = confusion_matrix(y_test, y_pred)

    print(f"\n{'='*60}")
    print(f"AVALIAÇÃO NO TESTE HOLD-OUT")
    print(f"{'='*60}")
    print(f"AUC:       {auc:.4f}   (ordenação de probabilidades)")
    print(f"Brier:     {brier:.4f}  (calibração - menor é melhor)")
    print(f"Log Loss:  {ll:.4f}")
    print(f"Accuracy:  {acc:.4f}")

    print(f"\nMatriz de confusão:")
    print(f"                   Prev DEFESA   Prev ACORDO")
    print(f"  Real DEFESA      {cm[0,0]:>10}    {cm[0,1]:>10}")
    print(f"  Real ACORDO      {cm[1,0]:>10}    {cm[1,1]:>10}")

    print(f"\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=['DEFESA', 'ACORDO']))

    return {
        'auc': float(auc),
        'brier_score': float(brier),
        'log_loss': float(ll),
        'accuracy': float(acc),
        'confusion_matrix': cm.tolist(),
    }


def diagnostico_calibracao(model, X_test, y_test):
    """
    Verifica se as probabilidades do modelo batem com a taxa real.
    Se gap médio < 0.05 = ótimo; < 0.10 = aceitável; > 0.10 = problema.
    """
    y_proba = model.predict_proba(X_test)[:, 1]
    prob_true, prob_pred = calibration_curve(y_test, y_proba, n_bins=10, strategy='quantile')

    print(f"\n{'='*60}")
    print(f"DIAGNÓSTICO DE CALIBRAÇÃO")
    print(f"{'='*60}")
    print(f"{'Prob prevista':<18} {'Taxa real':<15} {'Gap':<10}")
    print("-" * 45)
    for p_pred, p_true in zip(prob_pred, prob_true):
        gap = abs(p_pred - p_true)
        marker = " [OK]" if gap < 0.05 else (" [WARN]" if gap < 0.10 else " [FAIL]")
        print(f"{p_pred:<18.3f} {p_true:<15.3f} {gap:<10.4f}{marker}")

    gap_medio = float(np.abs(prob_pred - prob_true).mean())
    print(f"\nGap médio: {gap_medio:.4f}")
    if gap_medio < 0.05:
        print("-> Calibracao OTIMA: probabilidades sao honestas")
    elif gap_medio < 0.10:
        print("-> Calibracao ACEITAVEL")
    else:
        print("-> Calibracao RUIM: revisar hiperparametros ou features")

    return {'gap_medio_calibracao': gap_medio}


def distribuicao_probabilidades(model, X_test):
    """Mostra como as probabilidades se distribuem — quanto é zona cinza?"""
    y_proba = model.predict_proba(X_test)[:, 1]

    bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    dist = pd.cut(y_proba, bins=bins).value_counts().sort_index()

    print(f"\n{'='*60}")
    print(f"DISTRIBUIÇÃO DAS PROBABILIDADES NO TESTE")
    print(f"{'='*60}")
    for bin_range, count in dist.items():
        pct = count / len(y_proba) * 100
        bar = '#' * int(pct / 2)
        print(f"  {str(bin_range):<20} {count:>5} ({pct:5.1f}%)  {bar}")

    zona_cinza = ((y_proba >= 0.35) & (y_proba <= 0.65)).sum() / len(y_proba) * 100
    print(f"\nZona cinza (P entre 0.35 e 0.65): {zona_cinza:.1f}% dos casos")
    print("-> Nesses casos o agente deve sinalizar BAIXA confianca")


def feature_importance(model, feature_names):
    fi = pd.DataFrame({
        'feature': feature_names,
        'importance': model.feature_importances_,
    }).sort_values('importance', ascending=False)

    print(f"\n{'='*60}")
    print(f"FEATURE IMPORTANCE")
    print(f"{'='*60}")
    print(fi.to_string(index=False))

    # Alertas
    top = fi.iloc[0]
    if top['importance'] > 0.6:
        print(f"\n[WARN] Feature '{top['feature']}' domina o modelo ({top['importance']:.1%}).")
        print(f"   Considere verificar se existe redundância com outras features.")

    return fi


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='artefatos')
    args = parser.parse_args()

    pasta = Path(args.input)
    X, y = carregar_dados(pasta)

    # Split estratificado
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"[split] train: {X_train.shape[0]} | test: {X_test.shape[0]}")

    # Cross-validation (robustez)
    cv_metrics = cross_validation(X, y, XGBOOST_PARAMS)

    # Treino final
    print(f"\n{'='*60}")
    print(f"TREINO FINAL")
    print(f"{'='*60}")
    model = xgb.XGBClassifier(**XGBOOST_PARAMS)
    model.fit(X_train, y_train, eval_set=[(X_train, y_train)], verbose=False)
    print("[OK] Modelo treinado")

    # Avaliações
    metricas = avaliar(model, X_test, y_test)
    calib = diagnostico_calibracao(model, X_test, y_test)
    distribuicao_probabilidades(model, X_test)
    fi = feature_importance(model, X.columns.tolist())

    # Persistência
    joblib.dump(model, pasta / 'modelo_xgboost.pkl')

    with open(pasta / 'metricas.json', 'w') as f:
        json.dump({
            'cv': cv_metrics,
            'test': metricas,
            'calibracao': calib,
            'hyperparams': XGBOOST_PARAMS,
        }, f, indent=2)

    fi.to_csv(pasta / 'feature_importance.csv', index=False)

    print(f"\n[OK] Modelo salvo em {pasta}/modelo_xgboost.pkl")
    print(f"[OK] Metricas em {pasta}/metricas.json")
    print(f"[OK] Feature importance em {pasta}/feature_importance.csv")


if __name__ == '__main__':
    main()
