"""
LangGraph do caso: extrai o dossiê quando houver e SEMPRE calcula a política.

Revisão humana não trava a recomendação. Análise ainda não revisada, extração
incompleta, veredito inconclusivo ou dossiê indicado sem arquivo viram
ressalva visível na recomendação. Só a falta dos dados do caso impede decidir,
porque aí não há o que calcular.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from contracts.schema import CaseFeatures
from src.policy.engine import decidir
from src.state import GraphState
from src.tools.dossie_analyzer import DossieAnalyzer, analisar_dossie, analyze


def _ressalvas(state: GraphState, features: CaseFeatures) -> list[str]:
    report = state.get("dossie_resultado")
    if report is None or not report.docie_existe:
        return ["O caso indica dossiê, mas nenhum arquivo foi analisado."] if features.dossie else []
    ressalvas = []
    if not features.dossie:
        ressalvas.append("Há dossiê analisado, mas o caso não o marca como subsídio; o conteúdo não foi usado.")
    if not report.completo:
        ressalvas.append("A análise do dossiê não cobre o documento inteiro; o conteúdo não foi usado.")
    if report.analise.veredito == "inconclusivo":
        ressalvas.append("O veredito do dossiê é inconclusivo.")
    if state.get("analise_revisada") is not True:
        ressalvas.append("Análise do dossiê ainda não revisada por uma pessoa.")
    return ressalvas


def node_verificar_parecer(state: GraphState) -> dict:
    features = state.get("features")
    if features is None:
        return {"encaminhamento": "REVISAO_MANUAL", "recomendacao": None}
    features = CaseFeatures.model_validate(features)
    report = state.get("dossie_resultado")
    if report is not None and report.docie_existe and report.completo and features.dossie:
        features = features.model_copy(update={"analise_dossie": report.analise})

    recomendacao = decidir(features)
    ressalvas = _ressalvas(state, features)
    if ressalvas:
        recomendacao = recomendacao.model_copy(update={"alertas": [*recomendacao.alertas, *ressalvas]})
    return {
        "encaminhamento": "POLITICA_COM_RESSALVA" if ressalvas else "POLITICA_CALCULADA",
        "recomendacao": recomendacao,
    }


def build_graph(analyzer: DossieAnalyzer | None = None):
    from langgraph.graph import END, START, StateGraph

    extractor = analyzer or DossieAnalyzer(model=os.getenv("ENTERAGREE_DOSSIE_MODEL", "gpt-4o-mini"))

    def process(state: GraphState) -> dict:
        if "dossie_texto" in state:
            result = analisar_dossie(state, analyzer=extractor)
        elif state.get("caminho_pdf"):
            report = analyze(state["caminho_pdf"], analyzer=extractor)
            result = {"analise_dossie": report.analise, "dossie_resultado": report}
        else:
            result = {"analise_dossie": None, "dossie_resultado": None}
        # Nova extração invalida qualquer revisão anterior e qualquer recomendação antiga.
        return {**result, "analise_revisada": False, "recomendacao": None, "encaminhamento": "AUSENTE"}

    workflow = StateGraph(GraphState)
    workflow.add_node("processar_arquivo", process)
    workflow.add_node("verificar_parecer", node_verificar_parecer)
    workflow.add_edge(START, "processar_arquivo")
    workflow.add_edge("processar_arquivo", "verificar_parecer")
    workflow.add_edge("verificar_parecer", END)
    return workflow.compile()


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrai parecer de dossiê com evidências por página.")
    parser.add_argument("--document", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        state = build_graph().invoke({"caminho_pdf": str(arguments.document)})
    except Exception:
        print("Análise indisponível. Verifique dependências, configuração e arquivo de entrada.", file=sys.stderr)
        return 2
    resultado = state.get("dossie_resultado")
    output = {
        "encaminhamento": state["encaminhamento"],
        "resultado": resultado.model_dump(mode="json") if resultado is not None else None,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
