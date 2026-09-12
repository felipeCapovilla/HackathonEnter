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


def test_graph_requires_human_review_and_does_not_invent_a_recommendation():
    graph = build_graph(DossieAnalyzer(extractor=lambda pages: conforming()))
    result = graph.invoke({"dossie_texto": TEXT, "features": features()})
    assert result["encaminhamento"] == "REVISAO_MANUAL"
    assert result["recomendacao"] is None


def test_reviewed_signature_evidence_allows_existing_recovery_policy_without_faking_contract():
    graph = build_graph(DossieAnalyzer(extractor=lambda pages: conforming()))
    case = features()
    extracted = graph.invoke({"dossie_texto": TEXT, "features": case})
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


def test_missing_or_unconfirmed_dossier_never_reaches_policy(tmp_path):
    graph = build_graph(DossieAnalyzer(extractor=lambda pages: conforming()))
    result = graph.invoke({"caminho_pdf": str(tmp_path / "missing.pdf"), "features": features(), "analise_revisada": True})
    assert result["encaminhamento"] == "AUSENTE"
    assert result["recomendacao"] is None
    result = graph.invoke({"dossie_texto": TEXT, "features": features(dossie=False), "analise_revisada": True})
    assert result["encaminhamento"] == "REVISAO_MANUAL"
    assert result["recomendacao"] is None


def test_graph_does_not_reuse_a_previous_recommendation():
    graph = build_graph(DossieAnalyzer(extractor=lambda pages: conforming()))
    first = graph.invoke({"dossie_texto": TEXT, "features": features()})
    reviewed = {**first, **node_verificar_parecer({**first, "analise_revisada": True}), "analise_revisada": True}
    assert reviewed["recomendacao"] is not None
    second = graph.invoke({**reviewed, "dossie_texto": TEXT})
    assert second["recomendacao"] is None
    assert second["encaminhamento"] == "REVISAO_MANUAL"
    assert second["analise_revisada"] is False
