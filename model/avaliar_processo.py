import joblib
import numpy as np
import pandas as pd

# Carrega o artefato uma única vez
_ARTEFATO = joblib.load("/home/felipe-capovilla/Documents/Enter/politica_acordos_v1.pkl")
_MODELO_CLASSIFICACAO = _ARTEFATO["modelo_classificacao"]
_MODELO_VALOR = _ARTEFATO["modelo_valor"]
_FEATURES = _ARTEFATO["features"]
_FEATURES_CATEGORICAS = _ARTEFATO["features_categoricas"]
_PARAMS = _ARTEFATO["parametros_politica"]

_LIMIAR_ACORDO = _PARAMS["limiar_acordo"]
_RAZAO_MIN = _PARAMS["razao_min_historica"]
_RAZAO_MAX = _PARAMS["razao_max_historica"]

_PESOS_DOCUMENTOS = {"Comprovante de crédito": 0.50, "Contrato": 0.35, "Extrato": 0.15}
_SOMA_PESOS = sum(_PESOS_DOCUMENTOS.values())
_PESOS_NORMALIZADOS = {doc: peso / _SOMA_PESOS for doc, peso in _PESOS_DOCUMENTOS.items()}


def _calcular_valor_acordo(proba: float, valor_causa: float) -> float:
    fator = np.clip((proba - _LIMIAR_ACORDO) / (1 - _LIMIAR_ACORDO), 0, 1)
    razao = _RAZAO_MIN + fator * (_RAZAO_MAX - _RAZAO_MIN)
    return valor_causa * razao


def avaliar_processo(
    uf: str,
    sub_assunto: str,
    valor_causa: float,
    comprovante_credito: int,
    contrato: int,
    extrato: int,
    dossie: int,
    demonstrativo_evolucao_divida: int,
    laudo_referenciado: int,
) -> dict:
    """
    Recebe os dados de um processo e retorna a recomendação completa da política
    de acordos: probabilidade de derrota, decisão (Acordo/Defesa) e, se Acordo,
    o valor sugerido de oferta.

    Parâmetros
    ----------
    uf : str — sigla da UF (ex.: "SP")
    sub_assunto : str — "Genérico" ou "Golpe"
    valor_causa : float — valor da causa em reais (valor cru, sem log)
    comprovante_credito, contrato, extrato, dossie,
    demonstrativo_evolucao_divida, laudo_referenciado : int (0 ou 1)
        Se cada documento/subsídio foi apresentado.

    Retorna
    -------
    dict com as chaves:
        - "probabilidade_derrota": float (0 a 1)
        - "probabilidade_vitoria": float (0 a 1)
        - "valor_condenacao_previsto": float — quanto o banco pagaria SE perdesse
        - "decisao": "Acordo" ou "Defesa"
        - "valor_sugerido_acordo": float ou None (None se decisão for Defesa)
    """
    documentos = {
        "Comprovante de crédito": int(comprovante_credito),
        "Contrato": int(contrato),
        "Extrato": int(extrato),
        "Dossiê": int(dossie),
        "Demonstrativo de evolução da dívida": int(demonstrativo_evolucao_divida),
        "Laudo referenciado": int(laudo_referenciado),
    }
    score_subsidios_ponderado = round(
        sum(documentos[doc] * peso for doc, peso in _PESOS_NORMALIZADOS.items()), 2
    )
    total_documentos = sum(documentos.values())

    dados = {
        "UF": uf,
        "Assunto": "Não reconhece operação",
        "Sub-assunto": sub_assunto,
        "valor_causa_log": np.log1p(valor_causa),
        "score_subsidios_ponderado": score_subsidios_ponderado,
        "total_documentos": total_documentos,
        **documentos,
    }

    X = pd.DataFrame([dados])
    for col in _FEATURES_CATEGORICAS:
        X[col] = X[col].astype("category")
    X = X[_FEATURES]

    proba_derrota = float(_MODELO_CLASSIFICACAO.predict_proba(X)[:, 1][0])
    valor_condenacao_previsto = float(max(_MODELO_VALOR.predict(X)[0], 0))

    decisao = "Acordo" if proba_derrota >= _LIMIAR_ACORDO else "Defesa"
    valor_sugerido = (
        round(_calcular_valor_acordo(proba_derrota, valor_causa), 2)
        if decisao == "Acordo"
        else None
    )

    return {
        "probabilidade_derrota": round(proba_derrota, 4),
        "probabilidade_vitoria": round(1 - proba_derrota, 4),
        "valor_condenacao_previsto": round(valor_condenacao_previsto, 2),
        "decisao": decisao,
        "valor_sugerido_acordo": valor_sugerido,
    }


if __name__ == "__main__":
 
    exemplo_baixo_risco = avaliar_processo(
        uf="SP", sub_assunto="Genérico", valor_causa=15000.0,
        comprovante_credito=1, contrato=1, extrato=1,
        dossie=1, demonstrativo_evolucao_divida=1, laudo_referenciado=1,
    )
   
    print(exemplo_baixo_risco)
