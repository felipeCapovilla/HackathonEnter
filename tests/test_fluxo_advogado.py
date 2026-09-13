"""Máquina de estados do processo na visão do advogado (docs/fluxo_do_processo.md)."""
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.interface.backend.auth import hash_password
from src.interface.backend.config import Settings
from src.interface.backend.main import create_app
from src.interface.backend.schemas import CaseCreate, DocumentType, DocumentTypeStatus, SourceParty

SENHA = "senha-segura-com-15"


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = tmp_path / "runtime"
    app = create_app(Settings(runtime, runtime / "app.db", runtime / "documents", Path("artefatos"), 1024 * 1024, auth_required=True))
    with TestClient(app) as empresa, TestClient(app) as advogado:
        ids = {}
        for role, email, client in (("BANCO", "empresa@t.br", empresa), ("ADVOGADO_EXTERNO", "adv@t.br", advogado)):
            ids[role] = app.state.repository.create_user({
                "id": str(uuid4()), "name": email, "email": email, "password_hash": hash_password(SENHA), "role": role,
                "bank_id": "banco-unicamp", "is_active": True, "created_at": "2026-09-12T00:00:00+00:00"})["id"]
            assert client.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
        yield app, empresa, advogado, ids["ADVOGADO_EXTERNO"]


def _caso(app, lawyer_id):
    """MA, golpe, extrato + comprovante: a política recomenda acordo."""
    repository = app.state.repository
    case = repository.create_case(CaseCreate(case_number=str(uuid4()), uf="MA", value_of_claim=15000, sub_subject="Golpe",
                                             assigned_lawyer_id=lawyer_id))
    for tipo in (DocumentType.EXTRATO, DocumentType.COMPROVANTE_CREDITO):
        document = repository.create_document(case_id=case["id"], original_filename=f"{tipo.value}.txt", file_path=Path("x.txt"),
                                              declared_type=tipo, source_party=SourceParty.BANCO, sha256=str(uuid4()), request_id=None)
        repository.append_document_pages(document["id"], [{"page_number": 1, "text_content": "texto", "extraction_method": "TEXT", "quality_flags": []}])
        repository.update_document_extraction(document["id"], status="COMPLETED", page_count=1, pages_extracted=1, quality_flags=[],
                                              detected_type=tipo, type_status=DocumentTypeStatus.CONFIRMED)
    return case["id"]


def _fase(client, case_id):
    return client.get(f"/api/cases/{case_id}").json()["fase"]


def _avaliar(client, case_id):
    analysis = client.post(f"/api/cases/{case_id}/analyses").json()
    assert analysis["recommendation"] == "ACORDO"
    return analysis


def test_fila_e_acordo_com_contraproposta_dentro_do_maximo(ambiente):
    app, _, advogado, lawyer_id = ambiente
    case_id = _caso(app, lawyer_id)
    assert advogado.get("/api/lawyer/queue").json()[0]["fase"]["codigo"] == "AGUARDANDO_AVALIACAO"
    analysis = _avaliar(advogado, case_id)
    pricing = analysis["pricing"]
    fila = advogado.get("/api/lawyer/queue").json()[0]["fase"]
    assert (fila["codigo"], fila["proxima_acao"]) == ("PRONTO_PARA_DECIDIR", "Registrar a decisão")

    decidir = lambda corpo: advogado.post(f"/api/cases/{case_id}/lawyer-decisions?analysis_id={analysis['id']}", json=corpo)
    assert decidir({"action": "ACORDO"}).status_code == 422
    acima = decidir({"action": "ACORDO", "proposed_value": pricing["walk_away_value"] + 1000})
    assert acima.status_code == 422 and "valor máximo" in acima.json()["detail"]
    assert decidir({"action": "ACORDO", "proposed_value": pricing["opening_value"]}).status_code == 201
    assert _fase(advogado, case_id)["codigo"] == "EM_NEGOCIACAO"
    assert advogado.post(f"/api/cases/{case_id}/judicial-outcomes", json={"result": "EXITO"}).status_code == 409

    contra = pricing["walk_away_value"] - 100
    assert advogado.post(f"/api/cases/{case_id}/negotiation-outcomes", json={"status": "CONTRAPROPOSTA", "counter_value": contra}).status_code == 201
    fase = _fase(advogado, case_id)
    assert fase["codigo"] == "CONTRAPROPOSTA" and fase["negociacao"]["counter_value"] == contra
    aceito = advogado.post(f"/api/cases/{case_id}/negotiation-outcomes", json={"status": "ACEITO", "closed_value": contra})
    assert aceito.status_code == 201, aceito.text
    detalhe = advogado.get(f"/api/cases/{case_id}").json()
    assert detalhe["fase"]["codigo"] == "ENCERRADO" and detalhe["stage"] == "ENCERRADO"


def test_aceitar_acima_do_maximo_exige_motivo(ambiente):
    app, _, advogado, lawyer_id = ambiente
    case_id = _caso(app, lawyer_id)
    analysis = _avaliar(advogado, case_id)
    advogado.post(f"/api/cases/{case_id}/lawyer-decisions?analysis_id={analysis['id']}",
                  json={"action": "ACORDO", "proposed_value": analysis["pricing"]["opening_value"]})
    acima = analysis["pricing"]["walk_away_value"] + 500
    rota = f"/api/cases/{case_id}/negotiation-outcomes"
    assert advogado.post(rota, json={"status": "ACEITO", "closed_value": acima}).status_code == 422
    assert advogado.post(rota, json={"status": "ACEITO", "closed_value": acima, "divergence_reason": "SINAL_DO_AUTOR"}).status_code == 201


def test_acordo_recusado_vira_defesa_e_sentenca_encerra(ambiente):
    app, empresa, advogado, lawyer_id = ambiente
    case_id = _caso(app, lawyer_id)
    analysis = _avaliar(advogado, case_id)
    advogado.post(f"/api/cases/{case_id}/lawyer-decisions?analysis_id={analysis['id']}",
                  json={"action": "ACORDO", "proposed_value": analysis["pricing"]["opening_value"]})
    assert advogado.post(f"/api/cases/{case_id}/negotiation-outcomes", json={"status": "RECUSADO"}).status_code == 201
    assert _fase(advogado, case_id)["codigo"] == "EM_DEFESA"
    assert advogado.post(f"/api/cases/{case_id}/negotiation-outcomes", json={"status": "ACEITO", "closed_value": 1}).status_code == 409
    rota = f"/api/cases/{case_id}/judicial-outcomes"
    assert advogado.post(rota, json={"result": "NAO_EXITO"}).status_code == 422
    assert advogado.post(rota, json={"result": "NAO_EXITO", "condemnation_value": 9000}).status_code == 201
    assert _fase(advogado, case_id)["codigo"] == "ENCERRADO"
    assert empresa.get("/api/cases").json()[0]["condemnation_value"] == 9000


def test_divergir_exige_motivo_e_pedir_documento_cria_pedido(ambiente):
    app, empresa, advogado, lawyer_id = ambiente
    case_id = _caso(app, lawyer_id)
    analysis = _avaliar(advogado, case_id)
    rota = f"/api/cases/{case_id}/lawyer-decisions?analysis_id={analysis['id']}"
    assert advogado.post(rota, json={"action": "DEFESA"}).status_code == 422
    assert advogado.post(rota, json={"action": "DEFESA", "divergence_reason": "OUTRO"}).status_code == 422
    pedido = advogado.post(rota, json={"action": "RECUPERAR", "divergence_reason": "FATO_NOVO", "requested_document": "CONTRATO"})
    assert pedido.status_code == 201, pedido.text
    detalhe = advogado.get(f"/api/cases/{case_id}").json()
    assert detalhe["fase"]["codigo"] == "AGUARDANDO_DOCUMENTO"
    assert [(r["document_type"], r["status"]) for r in detalhe["document_requests"]] == [("CONTRATO", "REQUESTED")]
    assert advogado.post(rota, json={"action": "ACORDO", "proposed_value": 1000}).status_code == 409

    request_id = detalhe["document_requests"][0]["id"]
    assert empresa.post(f"/api/document-requests/{request_id}/response", json={
        "status": "DECLARED_UNAVAILABLE", "reason": "Não localizado.", "unavailability_reason": "NAO_LOCALIZADO"}).status_code == 200
    assert _fase(advogado, case_id)["codigo"] == "REAVALIAR"
    assert advogado.post(rota, json={"action": "ACORDO", "proposed_value": 1000}).status_code == 409
    nova = _avaliar(advogado, case_id)
    assert _fase(advogado, case_id)["codigo"] == "PRONTO_PARA_DECIDIR"
    assert advogado.post(rota, json={"action": "ACORDO", "proposed_value": 1000}).status_code == 409, "avaliação antiga"
    defesa = advogado.post(f"/api/cases/{case_id}/lawyer-decisions?analysis_id={nova['id']}",
                           json={"action": "DEFESA", "divergence_reason": "PROVA_MAIS_FORTE"})
    assert defesa.status_code == 201
    assert _fase(advogado, case_id)["codigo"] == "EM_DEFESA"


def test_documento_novo_depois_da_avaliacao_pede_reavaliacao(ambiente):
    app, empresa, advogado, lawyer_id = ambiente
    case_id = _caso(app, lawyer_id)
    analysis = _avaliar(advogado, case_id)
    enviado = empresa.post(f"/api/cases/{case_id}/documents", data={"declared_type": "CONTRATO", "source_party": "BANCO"},
                           files={"file": ("contrato.txt", b"Contrato de emprestimo assinado", "text/plain")})
    assert enviado.status_code == 201
    assert _fase(advogado, case_id)["codigo"] == "REAVALIAR"
    assert advogado.post(f"/api/cases/{case_id}/lawyer-decisions?analysis_id={analysis['id']}",
                         json={"action": "ACORDO", "proposed_value": 1000}).status_code == 409


def test_pdf_abre_na_pagina_e_mensagem_de_proposta_sem_ia(ambiente):
    app, empresa, advogado, lawyer_id = ambiente
    case_id = _caso(app, lawyer_id)
    pdf = empresa.post(f"/api/cases/{case_id}/documents", data={"declared_type": "AUTOS", "source_party": "BANCO"},
                       files={"file": ("autos.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")}).json()
    na_pagina = advogado.get(f"/api/documents/{pdf['id']}/file", params={"inline": 1})
    assert na_pagina.status_code == 200 and na_pagina.headers["content-disposition"].startswith("inline")
    assert advogado.get(f"/api/documents/{pdf['id']}/file").headers["content-disposition"].startswith("attachment")

    assert advogado.post(f"/api/cases/{case_id}/mensagem-proposta", json={}).status_code == 409
    analysis = _avaliar(advogado, case_id)
    mensagem = advogado.post(f"/api/cases/{case_id}/mensagem-proposta", json={}).json()
    numero = advogado.get(f"/api/cases/{case_id}").json()["case"]["case_number"]
    assert mensagem["fonte"] == "MODELO" and numero in mensagem["mensagem"]
    assert mensagem["valor"] == analysis["pricing"]["opening_value"]
