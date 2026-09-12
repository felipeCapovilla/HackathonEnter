from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pypdf import PdfWriter

from contracts.dossie import DossieChunkExtraction, DossieEvidence
from contracts.schema import ItemDossie
from src.tools.dossie_analyzer import (
    DossieAnalyzer,
    DossieConfigurationError,
    DossieLimitError,
    DossieProviderError,
    analisar_dossie,
    analyze,
)
from src.tools.text_converter import iter_document_pages


TEXT = (
    "Parecer geral: CONFORMIDADE. "
    "A assinatura manuscrita no contrato 502348719 foi periciada: COMPATÍVEL (91%). "
    "Documento de identidade: VÁLIDO. Comprovante de residência: VÁLIDO. "
    "Selfie confirmada: match facial 97,3%."
)


def evidence(field, value, quote, page=1):
    return DossieEvidence(campo=field, valor=str(value), pagina=page, trecho=quote)


def extraction(*, verdict="inconclusivo", signature=None, number=None, items=(), citations=()):
    return DossieChunkExtraction(
        veredito=verdict,
        analisou_assinatura_contrato=signature,
        numero_contrato_referenciado=number,
        itens=list(items),
        evidencias=list(citations),
    )


def conforming(page=1):
    signature_quote = "A assinatura manuscrita no contrato 502348719 foi periciada: COMPATÍVEL (91%)."
    facial_quote = "Selfie confirmada: match facial 97,3%."
    return extraction(
        verdict="conforme", signature=True, number="502348719",
        items=[
            ItemDossie(tipo="assinatura", resultado="ok", indice=0.91),
            ItemDossie(tipo="liveness", resultado="ok", indice=0.973),
            ItemDossie(tipo="documento_identidade", resultado="ok"),
            ItemDossie(tipo="comprovante_residencia", resultado="ok"),
        ],
        citations=[
            evidence("veredito", "conforme", "Parecer geral: CONFORMIDADE.", page),
            evidence("analisou_assinatura_contrato", "true", signature_quote, page),
            evidence("numero_contrato_referenciado", "502348719", signature_quote, page),
            evidence("assinatura", "ok", signature_quote, page),
            evidence("assinatura.indice", "0.91", signature_quote, page),
            evidence("liveness", "ok", facial_quote, page),
            evidence("liveness.indice", "0.973", facial_quote, page),
            evidence("documento_identidade", "ok", "Documento de identidade: VÁLIDO.", page),
            evidence("comprovante_residencia", "ok", "Comprovante de residência: VÁLIDO.", page),
        ],
    )


def test_cited_extraction_preserves_findings_and_normalized_percentages():
    analyzer = DossieAnalyzer(extractor=lambda pages: conforming())
    result = analisar_dossie({"dossie_texto": TEXT}, analyzer=analyzer)
    report = result["dossie_resultado"]
    assert report.completo
    assert report.analise.veredito == "conforme"
    assert report.analise.analisou_assinatura_contrato
    assert report.assinatura_contrato_status == "sim"
    assert report.analise.numero_contrato_referenciado == "502348719"
    assert report.analise.itens[0].indice == 0.91
    assert report.analise.itens[-1].indice == 0.973
    assert report.analise.confianca_extracao == 0.0
    assert report.paginas_processadas == report.trechos_processados == 1
    assert "recomendacao" not in result


def test_missing_information_does_not_become_false_or_zero_findings():
    report = DossieAnalyzer(extractor=lambda pages: extraction()).analyze_pages(
        [{"page_number": 1, "text_content": "Dossiê com informação insuficiente."}]
    )
    assert report.analise.veredito == "inconclusivo"
    assert report.assinatura_contrato_status == "desconhecido"
    assert not report.analise.analisou_assinatura_contrato
    assert all(item.resultado == "inconclusivo" and item.indice is None for item in report.analise.itens)


@pytest.mark.parametrize("quote", [" " * 10, "\n\t  " * 10, "a        b"])
def test_whitespace_cannot_bypass_citation_grounding(quote):
    with pytest.raises(ValidationError):
        evidence("veredito", "conforme", quote)


def test_positive_verdict_cannot_cite_a_negative_finding():
    quote = "Parecer geral: NÃO-CONFORMIDADE."
    output = extraction(verdict="conforme", citations=[evidence("veredito", "conforme", quote)])
    report = DossieAnalyzer(extractor=lambda pages: output).analyze_pages([
        {"page_number": 1, "text_content": quote},
    ])
    assert report.analise.veredito == "inconclusivo"
    assert not report.completo


def test_signature_mentioned_but_not_examined_cannot_enable_recovery():
    quote = "A assinatura no contrato não foi periciada neste dossiê."
    output = extraction(signature=True, citations=[evidence("analisou_assinatura_contrato", "true", quote)])
    report = DossieAnalyzer(extractor=lambda pages: output).analyze_pages([
        {"page_number": 1, "text_content": quote},
    ])
    assert not report.analise.analisou_assinatura_contrato
    assert report.assinatura_contrato_status == "desconhecido"


def test_empty_existing_file_is_not_reported_as_missing(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    report = analyze(path)
    assert report.docie_existe and not report.completo


def test_liveness_does_not_prove_contract_signature_examined():
    quote = "Selfie confirmada: match facial 97,3%."
    output = extraction(
        signature=True,
        citations=[evidence("analisou_assinatura_contrato", "true", quote)],
    )
    report = DossieAnalyzer(extractor=lambda pages: output).analyze_pages(
        [{"page_number": 1, "text_content": quote}]
    )
    assert not report.analise.analisou_assinatura_contrato
    assert report.assinatura_contrato_status == "desconhecido"
    assert not report.completo


@pytest.mark.parametrize("citation", [
    evidence("veredito", "conforme", "Parecer completamente inventado."),
    evidence("veredito", "conforme", "Parecer geral: CONFORMIDADE.", 2),
    evidence("veredito", "nao_conforme", "Parecer geral: CONFORMIDADE."),
])
def test_unsupported_or_misattributed_citation_is_not_accepted(citation):
    output = extraction(verdict="conforme", citations=[citation])
    report = DossieAnalyzer(extractor=lambda pages: output).analyze_pages(
        [{"page_number": 1, "text_content": TEXT}]
    )
    assert report.analise.veredito == "inconclusivo"
    assert report.evidencias == []
    assert not report.completo


def test_conflicting_verdicts_across_chunks_require_review():
    negative = "Parecer geral: NÃO CONFORMIDADE."
    calls = []

    def extract(pages):
        calls.append(pages)
        if len(calls) == 1:
            return conforming()
        return extraction(verdict="nao_conforme", citations=[evidence("veredito", "nao_conforme", negative, 2)])

    report = DossieAnalyzer(max_chunk_chars=512, extractor=extract).analyze_pages([
        {"page_number": 1, "text_content": TEXT + " " * (512 - len(TEXT))},
        {"page_number": 2, "text_content": negative},
    ])
    assert report.analise.veredito == "inconclusivo"
    assert not report.analise.analisou_assinatura_contrato
    assert not report.completo
    assert any("conflitantes" in warning for warning in report.avisos)
    assert {item.pagina for item in report.evidencias} == {1, 2}


def test_explicit_inconclusive_verdict_conflicts_with_conformity():
    quote = "Parecer final: análise inconclusiva."
    calls = iter([
        conforming(),
        extraction(verdict="inconclusivo", citations=[evidence("veredito", "inconclusivo", quote, 2)]),
    ])
    report = DossieAnalyzer(max_chunk_chars=512, extractor=lambda pages: next(calls)).analyze_pages([
        {"page_number": 1, "text_content": TEXT + " " * (512 - len(TEXT))},
        {"page_number": 2, "text_content": quote},
    ])
    assert report.analise.veredito == "inconclusivo"
    assert any("conflitantes" in warning for warning in report.avisos)


def test_index_must_match_percentage_in_source():
    output = extraction(
        items=[ItemDossie(tipo="liveness", resultado="ok", indice=0.5)],
        citations=[
            evidence("liveness", "ok", "Selfie confirmada: match facial 97,3%."),
            evidence("liveness.indice", "0.5", "Selfie confirmada: match facial 97,3%."),
        ],
    )
    report = DossieAnalyzer(extractor=lambda pages: output).analyze_pages(
        [{"page_number": 1, "text_content": TEXT}]
    )
    assert report.analise.itens[-1].indice is None
    assert not report.completo


@pytest.mark.parametrize("index", [-0.1, 1.1, float("nan"), float("inf")])
def test_out_of_range_indices_are_rejected(index):
    with pytest.raises(ValidationError):
        ItemDossie(tipo="assinatura", resultado="ok", indice=index)


def test_blank_and_missing_file_never_call_llm(tmp_path):
    def unexpected(pages):
        pytest.fail("LLM must not run without text")

    analyzer = DossieAnalyzer(extractor=unexpected)
    missing = analyze(tmp_path / "absent.pdf", analyzer=analyzer)
    assert not missing.docie_existe and not missing.completo
    report = analyzer.analyze_pages([{"page_number": 1, "text_content": " "}])
    assert report.docie_existe and not report.completo
    assert report.trechos_processados == 0


def test_blank_page_or_gap_invalidates_full_document_verdict():
    for extra_page in [
        {"page_number": 2, "text_content": ""},
        {"page_number": 3, "text_content": "Folha final."},
    ]:
        report = DossieAnalyzer(extractor=lambda pages: conforming()).analyze_pages([
            {"page_number": 1, "text_content": TEXT}, extra_page,
        ])
        assert not report.completo
        assert report.analise.veredito == "inconclusivo"


def test_thousand_pages_are_batched_and_final_page_is_not_truncated():
    batches = []

    def extract(pages):
        assert sum(len(page["text_content"]) for page in pages) <= 12000
        batches.append(pages)
        return conforming(1200) if any(page["page_number"] == 1200 for page in pages) else extraction()

    pages = (
        {"page_number": number, "text_content": TEXT if number == 1200 else "Página de contexto. " * 10}
        for number in range(1, 1201)
    )
    report = DossieAnalyzer(extractor=extract).analyze_pages(pages)
    assert report.paginas_processadas == 1200
    assert report.analise.veredito == "conforme"
    assert 1 < len(batches) < 128
    assert all(item.pagina == 1200 for item in report.evidencias)


def test_chunk_limit_is_explicit_instead_of_returning_partial_success():
    calls = []

    def extract(pages):
        calls.append(pages)
        return extraction()

    with pytest.raises(DossieLimitError):
        DossieAnalyzer(max_chunk_chars=512, max_chunks=1, extractor=extract).analyze_pages(
            [{"page_number": 1, "text_content": "Longo documento " * 500}]
        )
    assert len(calls) == 1


def test_no_api_key_is_not_a_fake_conforming_result(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(DossieConfigurationError):
        DossieAnalyzer().analyze_pages([{"page_number": 1, "text_content": TEXT}])


def test_invalid_structured_output_is_reported_as_provider_failure():
    analyzer = DossieAnalyzer(extractor=lambda pages: {"veredito": "qualquer coisa"})
    with pytest.raises(DossieProviderError):
        analyzer.analyze_pages([{"page_number": 1, "text_content": TEXT}])


def test_pdf_conversion_preserves_pages_without_sidecar(tmp_path):
    path = tmp_path / "dossie.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    writer.write(path)
    assert [page["page_number"] for page in iter_document_pages(path)] == [1, 2]
    assert not path.with_suffix(".md").exists()


def test_encrypted_pdf_is_rejected_before_llm(tmp_path):
    path = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    writer.write(path)
    with pytest.raises(ValueError, match="protegido"):
        list(iter_document_pages(path))


def test_text_fragments_preserve_one_logical_page(tmp_path):
    path = tmp_path / "dossie.txt"
    path.write_text("Contexto " * 3000, encoding="utf-8")
    fragments = list(iter_document_pages(path))
    assert len(fragments) > 1
    assert {page["page_number"] for page in fragments} == {1}
    report = analyze(path, analyzer=DossieAnalyzer(extractor=lambda pages: extraction()))
    assert report.paginas_processadas == 1


@pytest.mark.parametrize("status, parsed", [("incomplete", None), ("completed", None)])
def test_refusal_or_incomplete_provider_output_is_not_an_assessment(monkeypatch, status, parsed):
    openai = pytest.importorskip("openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")

    class Client:
        def __enter__(self):
            self.responses = SimpleNamespace(parse=lambda **kwargs: SimpleNamespace(status=status, output_parsed=parsed))
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: Client())
    with pytest.raises(DossieProviderError):
        DossieAnalyzer().analyze_pages([{"page_number": 1, "text_content": TEXT}])


def test_sdk_request_uses_structured_output_without_storage(monkeypatch):
    import json
    import httpx

    openai = pytest.importorskip("openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    constructor = openai.OpenAI
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 1,
            "model": "gpt-4o-mini", "status": "completed",
            "output": [{"id": "msg_test", "type": "message", "status": "completed",
                        "role": "assistant", "content": [{"type": "output_text",
                        "text": conforming().model_dump_json(), "annotations": []}]}],
        })

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: constructor(
        api_key="test-not-a-real-key", http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs
    ))
    report = DossieAnalyzer().analyze_pages([{"page_number": 1, "text_content": TEXT}])
    assert report.analise.veredito == "conforme"
    assert requests[0]["store"] is False
    assert requests[0]["text"]["format"]["type"] == "json_schema"
    assert requests[0]["text"]["format"]["strict"] is True
    assert requests[0]["model"] == "gpt-4o-mini"
    assert "tools" not in requests[0]
