import pytest

from contracts.schema import CaseFeatures
from src.graph import build_graph, node_verificar_parecer
from src.tools.dossie_analyzer import DossieAnalyzer
from test_dossie_analyzer import TEXT, conforming, evidence, extraction


pytest.importorskip("langgraph")


def features(**overrides):
    values = dict(
        numero_processo="test-graph", uf="AM", sub_assunto="Golpe", valor_causa=15000,
        contrato=False, extrato=False, comprovante_credito=True, dossie=True,
        demonstrativo=True, laudo=True,
    )
    return CaseFeatures(**{**values, **overrides})


def graph_with_conforming_dossier():
    return build_graph(DossieAnalyzer(extractor=lambda pages: conforming()))


def test_graph_always_calculates_and_flags_unreviewed_analysis():
    result = graph_with_conforming_dossier().invoke({"dossie_texto": TEXT, "features": features()})
    assert result["encaminhamento"] == "POLITICA_COM_RESSALVA"
    assert result["recomendacao"] is not None
    assert any("não revisada" in alerta for alerta in result["recomendacao"].alertas)


def test_reviewed_signature_evidence_allows_recovery_without_faking_contract():
    case = features(extrato=True)
    extracted = graph_with_conforming_dossier().invoke({"dossie_texto": TEXT, "features": case})
    result = node_verificar_parecer({**extracted, "analise_revisada": True})
    assert result["encaminhamento"] == "POLITICA_CALCULADA"
    assert result["recomendacao"].acao == "RECUPERAR"
    assert result["recomendacao"].recuperacao.documento == "contrato"
    assert not case.contrato
    assert case.analise_dossie is None


def test_negative_verdict_uses_main_policy_instead_of_forcing_settlement():
    quote = "Parecer geral: NÃO CONFORMIDADE."
    output = extraction(verdict="nao_conforme", citations=[evidence("veredito", "nao_conforme", quote)])
    graph = build_graph(DossieAnalyzer(extractor=lambda pages: output))
    case = features(contrato=True, extrato=True, uf="MA", sub_assunto="Generico")
    extracted = graph.invoke({"dossie_texto": quote, "features": case})
    result = node_verificar_parecer({**extracted, "analise_revisada": True})
    assert result["encaminhamento"] == "POLITICA_CALCULADA"
    assert result["recomendacao"].segmento.startswith("C0")
    assert result["recomendacao"].acao == "DEFENDER"


def test_missing_dossier_file_still_gets_a_recommendation(tmp_path):
    result = graph_with_conforming_dossier().invoke(
        {"caminho_pdf": str(tmp_path / "missing.pdf"), "features": features()})
    assert result["encaminhamento"] == "POLITICA_COM_RESSALVA"
    assert result["recomendacao"].acao == "ACORDAR"
    assert any("nenhum arquivo" in alerta for alerta in result["recomendacao"].alertas)


def test_case_without_dossier_is_decided_from_flags_alone():
    case = features(dossie=False, contrato=True, extrato=True, uf="MA", sub_assunto="Generico")
    result = graph_with_conforming_dossier().invoke({"features": case})
    assert result["encaminhamento"] == "POLITICA_CALCULADA"
    assert result["recomendacao"].acao == "DEFENDER"


def test_without_case_features_nothing_is_invented():
    result = graph_with_conforming_dossier().invoke({"dossie_texto": TEXT})
    assert result["encaminhamento"] == "REVISAO_MANUAL"
    assert result["recomendacao"] is None


def test_new_extraction_resets_review_and_recalculates():
    graph = graph_with_conforming_dossier()
    first = graph.invoke({"dossie_texto": TEXT, "features": features(extrato=True)})
    reviewed = {**first, **node_verificar_parecer({**first, "analise_revisada": True}), "analise_revisada": True}
    assert reviewed["encaminhamento"] == "POLITICA_CALCULADA"
    second = graph.invoke({**reviewed, "dossie_texto": TEXT})
    assert second["analise_revisada"] is False
    assert second["encaminhamento"] == "POLITICA_COM_RESSALVA"
    assert second["recomendacao"] is not None
