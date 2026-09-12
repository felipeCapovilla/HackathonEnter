"""Optional LangGraph workflow: extract, review, then call the existing policy."""

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


def node_verificar_parecer(state: GraphState) -> dict:
    report = state["dossie_resultado"]
    features = state.get("features")
    if (
        not report.completo
        or report.analise.veredito == "inconclusivo"
        or state.get("analise_revisada") is not True
        or features is None
    ):
        return {"encaminhamento": "REVISAO_MANUAL", "recomendacao": None}
    features = CaseFeatures.model_validate(features)
    if not features.dossie:
        return {"encaminhamento": "REVISAO_MANUAL", "recomendacao": None}
    assessed = features.model_copy(update={"analise_dossie": report.analise})
    return {"encaminhamento": "POLITICA_CALCULADA", "recomendacao": decidir(assessed)}


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
            raise ValueError("Informe dossie_texto ou caminho_pdf.")
        return {**result, "analise_revisada": False, "recomendacao": None, "encaminhamento": "AUSENTE"}

    def route(state: GraphState) -> str:
        return "verificar_parecer" if state["dossie_resultado"].docie_existe else END

    workflow = StateGraph(GraphState)
    workflow.add_node("processar_arquivo", process)
    workflow.add_node("verificar_parecer", node_verificar_parecer)
    workflow.add_edge(START, "processar_arquivo")
    workflow.add_conditional_edges("processar_arquivo", route, ["verificar_parecer", END])
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
    output = {
        "encaminhamento": state["encaminhamento"],
        "resultado": state["dossie_resultado"].model_dump(mode="json"),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
