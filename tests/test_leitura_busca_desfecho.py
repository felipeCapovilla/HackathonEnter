"""Leitura por IA ao enviar documento, busca por contrato e valor perdido na sentença desfavorável."""
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from src.interface.backend.auth import hash_password
from src.interface.backend.config import Settings
from src.interface.backend.main import create_app
from src.interface.backend.schemas import CaseCreate
from src.tools.leitor_documentos import LeituraDocumento, LeituraIndisponivel

SENHA = "senha-segura-com-15"
CONTRATO = "CONTRATO DE EMPRESTIMO CONSIGNADO numero 502348719. Contratante Maria da Silva. Valor liberado R$ 5.000,00. Assinatura."


def _app(tmp_path: Path):
    runtime = tmp_path / "runtime"
    return create_app(Settings(runtime, runtime / "app.db", runtime / "documents", Path("artefatos"), 1024 * 1024, auth_required=True))


def _login(app, client, role, email):
    user = app.state.repository.create_user({"id": str(uuid4()), "name": email, "email": email, "password_hash": hash_password(SENHA),
                                             "role": role, "bank_id": "banco-unicamp", "is_active": True,
                                             "created_at": "2026-09-12T00:00:00+00:00"})
    assert client.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return user


def _upload(client, case_id, texto, tipo, nome):
    response = client.post(f"/api/cases/{case_id}/documents", data={"declared_type": tipo, "source_party": "BANCO"},
                           files={"file": (nome, texto.encode(), "text/plain")})
    assert response.status_code == 201, response.text
    return response.json()


def test_leitura_por_ia_ao_enviar_e_busca_por_contrato(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "teste")
    app = _app(tmp_path)
    with TestClient(app) as empresa, TestClient(app) as advogado:
        _login(app, empresa, "BANCO", "empresa@t.br")
        _login(app, advogado, "ADVOGADO_EXTERNO", "adv@t.br")
        lidos = []

        def leitor_falso(caminho, texto, tipo):
            lidos.append(tipo)
            return LeituraDocumento(tipo_documento="CONTRATO", resumo="Contrato de empréstimo consignado de R$ 5.000.",
                                    numero_contrato="502348719", valor_principal=5000.0, nome_parte_autora="Maria da Silva")

        app.state.leitor = leitor_falso
        case_id = empresa.post("/api/cases", json={"case_number": "busca-001", "uf": "MA", "value_of_claim": 20000}).json()["id"]
        _upload(empresa, case_id, CONTRATO, "CONTRATO", "contrato.txt")

        leituras = empresa.get(f"/api/cases/{case_id}").json()["document_readings"]
        assert lidos == ["CONTRATO"]
        assert leituras[0]["status"] == "COMPLETED" and leituras[0]["result"]["numero_contrato"] == "502348719"

        achados = empresa.get("/api/bank/search", params={"q": "502348719"}).json()
        assert [a["case_id"] for a in achados] == [case_id]
        assert any("Contrato nº 502348719" == m["onde"] for m in achados[0]["matches"])
        assert any(m["pagina"] == 1 and "502348719" in m["trecho"] for m in achados[0]["matches"])
        assert empresa.get("/api/bank/search", params={"q": "busca-0"}).json()[0]["matches"][0]["onde"] == "Número do processo"
        assert empresa.get("/api/bank/search", params={"q": "xy"}).status_code == 422
        assert advogado.get("/api/bank/search", params={"q": "502348719"}).status_code == 403


def test_sem_chave_o_envio_segue_e_a_leitura_manual_avisa(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = _app(tmp_path)
    with TestClient(app) as empresa:
        _login(app, empresa, "BANCO", "empresa@t.br")
        case_id = empresa.post("/api/cases", json={"case_number": "sem-chave", "uf": "SP", "value_of_claim": 1000}).json()["id"]
        documento = _upload(empresa, case_id, CONTRATO, "CONTRATO", "contrato.txt")
        assert empresa.get(f"/api/cases/{case_id}").json()["document_readings"] == []
        assert empresa.post(f"/api/documents/{documento['id']}/leitura").status_code == 503


def test_falha_do_provedor_fica_registrada_sem_quebrar_o_envio(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "teste")
    app = _app(tmp_path)
    with TestClient(app) as empresa:
        _login(app, empresa, "BANCO", "empresa@t.br")

        def leitor_quebrado(*_):
            raise LeituraIndisponivel("provedor fora do ar")

        app.state.leitor = leitor_quebrado
        case_id = empresa.post("/api/cases", json={"case_number": "falha", "uf": "SP", "value_of_claim": 1000}).json()["id"]
        _upload(empresa, case_id, CONTRATO, "CONTRATO", "contrato.txt")
        leitura = empresa.get(f"/api/cases/{case_id}").json()["document_readings"][0]
        assert leitura["status"] == "FAILED" and leitura["error"] == "provedor fora do ar"


def test_sentenca_desfavoravel_guarda_quanto_a_empresa_perdeu(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = _app(tmp_path)
    with TestClient(app) as empresa, TestClient(app) as advogado:
        _login(app, empresa, "BANCO", "empresa@t.br")
        lawyer = _login(app, advogado, "ADVOGADO_EXTERNO", "adv@t.br")
        case = app.state.repository.create_case(CaseCreate(case_number="perda-1", uf="MA", value_of_claim=15000,
                                                           sub_subject="Golpe", assigned_lawyer_id=lawyer["id"]))
        analysis = advogado.post(f"/api/cases/{case['id']}/analyses").json()
        decision = advogado.post(f"/api/cases/{case['id']}/lawyer-decisions?analysis_id={analysis['id']}",
                                 json={"action": "DEFESA", "divergence_reason": "PROVA_MAIS_FORTE"}).json()
        registrado = advogado.post(f"/api/cases/{case['id']}/lawyer-decisions/{decision['id']}/outcome",
                                   json={"outcome": "SENTENCA_DESFAVORAVEL", "value": 12000})
        assert registrado.status_code == 201, registrado.text
        assert empresa.get("/api/cases").json()[0]["condemnation_value"] == 12000
        assert empresa.get(f"/api/cases/{case['id']}").json()["judicial_outcomes"][0]["condemnation_value"] == 12000
        assert empresa.get("/api/bank/insights").json()["efetividade"]["defendidos"]["condenacoes"] == 12000
