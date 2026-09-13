"""Painel do banco: contrato do gestor por escritório, desfechos, engajamento, motivo estruturado e insights."""
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.interface.backend.auth import hash_password, verify_password
from src.interface.backend.bank_insights import build_bank_insights
from src.interface.backend.config import Settings
from src.interface.backend.database import connection_for
from src.interface.backend.main import create_app
from src.interface.backend.repository import Repository
from src.interface.backend.schemas import CaseCreate, DocumentType, DocumentTypeStatus, SourceParty
from src.utils.motivo_indisponibilidade import classificar_motivo, por_regra

ROOT = Path(__file__).resolve().parents[1]
BANCO = "banco-unicamp"
SENHA = "senha-segura-com-15"
JUSTIFICATIVA = "Aditivo assinado em setembro de 2026."


def _settings(tmp_path: Path) -> Settings:
    runtime = tmp_path / "runtime"
    return Settings(runtime_dir=runtime, database_path=runtime / "app.db", document_dir=runtime / "documents",
                    artifact_dir=ROOT / "artefatos", max_upload_bytes=1024 * 1024, auth_required=True)


def _user(app, role: str, email: str, **extra) -> dict:
    return app.state.repository.create_user({
        "id": str(uuid4()), "name": email.split("@")[0].title(), "email": email, "password_hash": hash_password(SENHA),
        "role": role, "bank_id": None if role == "ADMIN_GLOBAL" else BANCO, "is_active": True,
        "created_at": "2026-09-12T00:00:00+00:00", **extra})


def _login(client: TestClient, email: str) -> None:
    assert client.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200


def _document(app, case_id: str, declared_type: DocumentType) -> str:
    repository = app.state.repository
    document = repository.create_document(
        case_id=case_id, original_filename=f"{declared_type.value}.txt", file_path=Path("unused.txt"),
        declared_type=declared_type, source_party=SourceParty.BANCO, sha256=str(uuid4()), request_id=None)
    repository.append_document_pages(document["id"], [{
        "page_number": 1, "text_content": "conteúdo", "extraction_method": "TEXT", "quality_flags": []}])
    repository.update_document_extraction(
        document["id"], status="COMPLETED", page_count=1, pages_extracted=1, quality_flags=[],
        detected_type=declared_type, type_status=DocumentTypeStatus.CONFIRMED)
    return document["id"]


def _case(app, lawyer_id: str) -> dict:
    case = app.state.repository.create_case(CaseCreate(
        case_number=str(uuid4()), uf="MA", value_of_claim=15000, sub_subject="Golpe", assigned_lawyer_id=lawyer_id))
    _document(app, case["id"], DocumentType.EXTRATO)
    _document(app, case["id"], DocumentType.COMPROVANTE_CREDITO)
    return case


def test_manager_saves_firm_contract_with_justification_and_analysis_uses_it(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as admin, TestClient(app) as gestor, TestClient(app) as operador, \
            TestClient(app) as advogado, TestClient(app) as outro:
        _user(app, "ADMIN_GLOBAL", "admin@t.br")
        _login(admin, "admin@t.br")
        firm = admin.post("/api/admin/law-firms", json={"name": "Escritório Teste"}).json()
        assert admin.post("/api/admin/law-firms", json={"name": "Escritório Teste"}).status_code == 409
        _user(app, "BANCO", "gestor@t.br", is_manager=True)
        _user(app, "BANCO", "operador@t.br")
        lawyer = _user(app, "ADVOGADO_EXTERNO", "adv@t.br", law_firm_id=firm["id"])
        other = _user(app, "ADVOGADO_EXTERNO", "outro@t.br")
        for client, email in ((gestor, "gestor@t.br"), (operador, "operador@t.br"), (advogado, "adv@t.br"), (outro, "outro@t.br")):
            _login(client, email)
        assert gestor.get("/api/auth/me").json()["is_manager"] is True
        assert advogado.get("/api/auth/me").json()["law_firm_name"] == "Escritório Teste"
        assert [f["id"] for f in gestor.get("/api/bank/law-firms").json()] == [firm["id"]]

        honorario = {"honorario_acordo": {"tipo": "percentual_valor_causa", "valor": 0.15}}
        url = f"/api/bank/contract?law_firm_id={firm['id']}"
        assert operador.post(url, json={"parametros": honorario, "justificativa": JUSTIFICATIVA}).status_code == 403
        assert operador.post(f"/api/bank/contract/preview?law_firm_id={firm['id']}", json=honorario).status_code == 403
        assert gestor.post(url, json={"parametros": honorario, "justificativa": "curta"}).status_code == 422
        assert gestor.post("/api/bank/contract?law_firm_id=outro", json={"parametros": honorario,
                                                                          "justificativa": JUSTIFICATIVA}).status_code == 404
        herdado = gestor.get(url).json()
        assert herdado["inherited_from_bank"] is True and herdado["version"] == 0
        salvo = gestor.post(url, json={"parametros": honorario, "justificativa": JUSTIFICATIVA})
        assert salvo.status_code == 201
        assert (salvo.json()["version"], salvo.json()["law_firm_id"], salvo.json()["justification"]) == (1, firm["id"], JUSTIFICATIVA)
        assert gestor.get("/api/bank/contract").json()["version"] == 0

        com_contrato = advogado.post(f"/api/cases/{_case(app, lawyer['id'])['id']}/analyses").json()
        padrao = outro.post(f"/api/cases/{_case(app, other['id'])['id']}/analyses").json()
        assert (com_contrato["contract_version"], com_contrato["recommendation"]) == (f"{BANCO}-v1", "DEFESA")
        assert (padrao["contract_version"], padrao["recommendation"]) == ("padrao", "ACORDO")


def test_outcomes_and_engagement_feed_bank_insights(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as banco, TestClient(app) as advogado:
        _user(app, "BANCO", "banco@t.br")
        lawyer = _user(app, "ADVOGADO_EXTERNO", "adv@t.br")
        _login(banco, "banco@t.br")
        _login(advogado, "adv@t.br")
        case_id = _case(app, lawyer["id"])["id"]
        document_id = app.state.repository.list_documents(case_id)[0]["id"]

        assert advogado.post(f"/api/cases/{case_id}/negotiation-outcomes", json={"status": "RECUSADO"}).status_code == 409
        assert advogado.get(f"/api/cases/{case_id}").status_code == 200
        assert advogado.get(f"/api/documents/{document_id}/pages/1").status_code == 200
        aberto = {"event_type": "DOCUMENT_OPENED", "document_id": document_id}
        assert advogado.post(f"/api/cases/{case_id}/engagement", json=aberto).status_code == 204
        assert advogado.post(f"/api/cases/{case_id}/engagement", json={"event_type": "ACTIVE_TIME", "active_seconds": 60}).status_code == 422
        assert banco.post(f"/api/cases/{case_id}/engagement", json=aberto).status_code == 403

        analysis = advogado.post(f"/api/cases/{case_id}/analyses").json()
        alvo = analysis["pricing"]["target_value"]
        decision = advogado.post(f"/api/cases/{case_id}/lawyer-decisions?analysis_id={analysis['id']}",
                                 json={"action": "ACORDO", "proposed_value": alvo})
        assert decision.status_code == 201
        assert advogado.post(f"/api/cases/{case_id}/negotiation-outcomes", json={"status": "ACEITO"}).status_code == 422
        fechado = advogado.post(f"/api/cases/{case_id}/negotiation-outcomes",
                                json={"status": "ACEITO", "offered_value": alvo, "closed_value": alvo})
        assert fechado.status_code == 201 and fechado.json()["lawyer_id"] == lawyer["id"]
        assert advogado.post(f"/api/cases/{case_id}/judicial-outcomes",
                             json={"result": "EXITO", "condemnation_value": 10}).status_code == 422
        detalhe = advogado.get(f"/api/cases/{case_id}").json()
        assert detalhe["negotiation_outcomes"][0]["status"] == "ACEITO"
        assert detalhe["stage"] == "ENCERRADO"  # acordo aceito encerra o processo no ciclo de vida
        assert advogado.post(f"/api/cases/{case_id}/negotiation-outcomes", json={"status": "RECUSADO"}).status_code == 409

        insights = banco.get("/api/bank/insights").json()
        efetividade = insights["efetividade"]
        assert (efetividade["aderencia"]["taxa"], efetividade["acordos"]["fechados"], efetividade["aceitacao"]["taxa"]) == (1.0, 1, 1.0)
        assert efetividade["economia"]["total"] == pytest.approx(analysis["pricing"]["similar_cases_cost"] - alvo, abs=0.01)
        assert (efetividade["pior_caso"], efetividade["gasto_real"]) == (15000, pytest.approx(alvo))
        assert efetividade["ticket"]["ticket_medio"] == pytest.approx(alvo)
        score = insights["advogados"][0]["score"]
        assert score["amostra_suficiente"] is False and score["componentes"]["aderencia"] == 100
        assert "engajamento" not in insights
        assert advogado.get("/api/bank/insights").status_code == 403


def test_unavailable_document_gets_structured_reason_and_infra_recommendation(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = create_app(_settings(tmp_path))
    with TestClient(app) as banco, TestClient(app) as advogado:
        _user(app, "BANCO", "banco@t.br")
        lawyer = _user(app, "ADVOGADO_EXTERNO", "adv@t.br")
        _login(banco, "banco@t.br")
        _login(advogado, "adv@t.br")
        case_id = _case(app, lawyer["id"])["id"]
        pedidos = [advogado.post(f"/api/cases/{case_id}/document-requests", json={
            "document_type": "CONTRATO", "hypothesis_key": "CONTRATO_ASSINADO", "reason": "Recuperar o contrato."}).json()["id"]
            for _ in range(2)]
        informado = banco.post(f"/api/document-requests/{pedidos[0]}/response", json={
            "status": "DECLARED_UNAVAILABLE", "reason": "Não veio do parceiro.", "unavailability_reason": "CORRESPONDENTE_NAO_ENVIOU"}).json()
        assert (informado["unavailability_reason"], informado["unavailability_reason_source"]) == ("CORRESPONDENTE_NAO_ENVIOU", "INFORMADO")
        regra = banco.post(f"/api/document-requests/{pedidos[1]}/response", json={
            "status": "DECLARED_UNAVAILABLE", "reason": "Contrato em papel, ainda não digitalizado."}).json()
        assert (regra["unavailability_reason"], regra["unavailability_reason_source"]) == ("CONTRATO_FISICO_NAO_DIGITALIZADO", "REGRA")

        cards = [c for c in banco.get("/api/bank/insights").json()["recomendacoes"] if c["origem"] == "operacao"]
        assert {c["area"] for c in cards} == {"Canais e correspondentes bancários", "Operações de crédito + TI"}


def test_decision_outcome_without_values_still_feeds_the_panel(tmp_path):
    """Desfecho registrado só no ciclo de vida (sem valor detalhado) conta como acordo fechado no valor proposto."""
    app = create_app(_settings(tmp_path))
    with TestClient(app) as banco, TestClient(app) as advogado:
        _user(app, "BANCO", "banco@t.br")
        lawyer = _user(app, "ADVOGADO_EXTERNO", "adv@t.br")
        _login(banco, "banco@t.br")
        _login(advogado, "adv@t.br")
        case_id = _case(app, lawyer["id"])["id"]
        analysis = advogado.post(f"/api/cases/{case_id}/analyses").json()
        alvo = analysis["pricing"]["target_value"]
        decision = advogado.post(f"/api/cases/{case_id}/lawyer-decisions?analysis_id={analysis['id']}",
                                 json={"action": "ACORDO", "proposed_value": alvo}).json()
        assert advogado.post(f"/api/cases/{case_id}/lawyer-decisions/{decision['id']}/outcome",
                             json={"outcome": "ACORDO_ACEITO"}).status_code == 201
        efetividade = banco.get("/api/bank/insights").json()["efetividade"]
        assert efetividade["acordos"]["fechados"] == 1
        assert efetividade["economia"]["total"] == pytest.approx(analysis["pricing"]["similar_cases_cost"] - alvo, abs=0.01)


@pytest.mark.parametrize(("texto", "motivo"), [
    ("Documento não localizado nos sistemas consultados.", "NAO_LOCALIZADO"),
    ("Sistema legado não permite exportar o extrato.", "SISTEMA_SEM_EXPORTACAO"),
    ("Não há registro de contratação: indício de fraude.", "OPERACAO_INEXISTENTE"),
    ("Descartado pela tabela de temporalidade.", "FORA_DO_PRAZO_DE_GUARDA"),
    ("A área responsável não retornou.", "OUTRO"),
])
def test_rule_classifier(texto, motivo):
    assert por_regra(texto) == motivo


def test_classifier_without_key_uses_rule(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert classificar_motivo("Contrato físico no arquivo da agência.", "CONTRATO") == ("CONTRATO_FISICO_NAO_DIGITALIZADO", "REGRA")


def test_simulated_operation_populates_every_panel_section(tmp_path):
    if not (ROOT / "data" / "resultados.csv").is_file():
        pytest.skip("base histórica não está em data/ (gitignored)")
    from scripts import seed_operacao_simulada as simulacao

    database = tmp_path / "demo.db"
    assert simulacao.simular(database)["casos"] == 1160
    with pytest.raises(ValueError, match="--reset"):
        simulacao.simular(database)
    assert simulacao.simular(database, reset=True)["casos"] == 1160

    gestor = Repository(database).get_user_by_email("banco@demo.local")
    assert gestor["is_manager"] and verify_password("teste123", gestor["password_hash"])
    with connection_for(database) as connection:
        painel = build_bank_insights(connection, BANCO)
    assert painel["casos_simulados"] == 520
    assert painel["efetividade"]["encerrados"] > 100 and painel["efetividade"]["economia"]["processos"] > 100
    assert painel["efetividade"]["gasto_real"] < painel["efetividade"]["pior_caso"]
    assert all(linha["score"]["nota"] is not None for linha in painel["advogados"])
    escritorios = {f["nome"]: f for f in painel["escritorios"]}
    assert escritorios["Costa Lima Advocacia"]["mercado"] is not None
    assert escritorios["Nogueira Prado Advogados"]["mercado"] is None  # só um outro cliente: sem benchmark
    assert painel["documentos"]["fila_total"] > 0
    assert any(card["origem"] == "operacao" for card in painel["recomendacoes"])
    assert painel["excecoes"]["por_tipo"].get("DECISAO_SEM_CONFERENCIA")
