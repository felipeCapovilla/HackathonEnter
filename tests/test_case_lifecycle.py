"""
Ciclo de vida do processo: exclusão de documento, desfecho e painel do advogado.

Três coisas que o produto passou a precisar e que o banco de dados não registrava:
quem apagou qual documento, como o processo terminou de verdade, e a diferença
entre o advogado ter seguido a política e ter dado certo.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from src.interface.backend.auth import hash_password
from src.interface.backend.config import Settings
from src.interface.backend.main import create_app

SENHA = "senha-segura-com-15"


def settings(tmp_path):
    runtime = tmp_path / "runtime"
    return Settings(runtime, runtime / "app.db", runtime / "documents", Path("artefatos"), 1024 * 1024, auth_required=True)


def add_user(app, role, email, bank_id="banco-unicamp"):
    return app.state.repository.create_user({
        "id": role + email, "name": role.title(), "email": email,
        "password_hash": hash_password(SENHA), "role": role,
        "bank_id": None if role == "ADMIN_GLOBAL" else bank_id, "is_active": True,
        "created_at": "2026-09-12T00:00:00+00:00",
    })


def login(client, email):
    assert client.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200


def upload(client, case_id, name="contrato.txt", declared_type="CONTRATO"):
    response = client.post(
        f"/api/cases/{case_id}/documents",
        files={"file": (name, b"conteudo do documento para o teste", "text/plain")},
        data={"declared_type": declared_type, "source_party": "BANCO"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_case(bank_client, lawyer_id, numero="ciclo-001"):
    response = bank_client.post("/api/cases", json={
        "case_number": numero, "uf": "SP", "value_of_claim": 15026.0,
        "assigned_lawyer_id": lawyer_id,
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ── Exclusão lógica de documento ─────────────────────────────────────────────

def test_banco_exclui_documento_e_ele_some_da_listagem(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        case_id = make_case(bank, lawyer["id"])
        document = upload(bank, case_id)

        assert bank.delete(f"/api/cases/{case_id}/documents/{document['id']}").status_code == 204

        detail = bank.get(f"/api/cases/{case_id}").json()
        assert detail["documents"] == [], "documento excluído não pode voltar na listagem"


def test_exclusao_apaga_o_arquivo_mas_preserva_a_linha(tmp_path):
    """A trilha de auditoria é o motivo de a exclusão ser lógica."""
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        case_id = make_case(bank, lawyer["id"])
        document = upload(bank, case_id)
        caminho = Path(app.state.repository.get_document_internal(document["id"])["file_path"])
        assert caminho.exists()

        bank.delete(f"/api/cases/{case_id}/documents/{document['id']}")

        assert not caminho.exists(), "o conteúdo deve sumir do disco"
        registro = app.state.repository.get_document_internal(document["id"])
        assert registro is not None, "a linha fica: feature_provenance aponta para este id"
        assert registro["deleted_at"]
        assert registro["deleted_by_user_id"]


def test_documento_excluido_nao_alimenta_mais_a_politica(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        case_id = make_case(bank, lawyer["id"])
        document = upload(bank, case_id)
        bank.delete(f"/api/cases/{case_id}/documents/{document['id']}")

        assert app.state.repository.list_documents(case_id) == []


def test_advogado_nao_exclui_documento_do_banco(tmp_path):
    """Deixar a outra parte remover prova seria conflito de interesse."""
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank, TestClient(app) as lawyer_client:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        login(lawyer_client, "adv@unicamp.br")
        case_id = make_case(bank, lawyer["id"])
        document = upload(bank, case_id)

        assert lawyer_client.delete(f"/api/cases/{case_id}/documents/{document['id']}").status_code == 403


def test_excluir_duas_vezes_devolve_404(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        case_id = make_case(bank, lawyer["id"])
        document = upload(bank, case_id)
        rota = f"/api/cases/{case_id}/documents/{document['id']}"

        assert bank.delete(rota).status_code == 204
        assert bank.delete(rota).status_code == 404
        assert bank.get(f"/api/documents/{document['id']}/file").status_code == 404


# ── Desfecho e ativo/inativo ─────────────────────────────────────────────────

def decidir_e_obter_decisao(lawyer_client, case_id):
    analysis = lawyer_client.post(f"/api/cases/{case_id}/analyses")
    assert analysis.status_code == 201, analysis.text
    decision = lawyer_client.post(
        f"/api/cases/{case_id}/lawyer-decisions?analysis_id={analysis.json()['id']}",
        json={"action": analysis.json()["recommendation"], "proposed_value": 4000.0, "reason": None},
    )
    assert decision.status_code == 201, decision.text
    return decision.json()["id"]


def test_processo_so_fica_inativo_com_desfecho_registrado(tmp_path):
    """Decisão registrada não encerra: a negociação ainda está correndo."""
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank, TestClient(app) as lawyer_client:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        login(lawyer_client, "adv@unicamp.br")
        case_id = make_case(bank, lawyer["id"])

        assert lawyer_client.get("/api/cases").json()[0]["active"] is True

        decision_id = decidir_e_obter_decisao(lawyer_client, case_id)
        caso = lawyer_client.get("/api/cases").json()[0]
        assert caso["active"] is True, "decidido mas sem desfecho continua ativo"
        assert caso["decided"] is True

        assert lawyer_client.post(
            f"/api/cases/{case_id}/lawyer-decisions/{decision_id}/outcome",
            json={"outcome": "ACORDO_ACEITO"},
        ).status_code == 201

        caso = lawyer_client.get("/api/cases").json()[0]
        assert caso["active"] is False
        assert caso["outcome"] == "ACORDO_ACEITO"


def test_desfecho_nao_se_reescreve(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank, TestClient(app) as lawyer_client:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        login(lawyer_client, "adv@unicamp.br")
        case_id = make_case(bank, lawyer["id"])
        decision_id = decidir_e_obter_decisao(lawyer_client, case_id)
        rota = f"/api/cases/{case_id}/lawyer-decisions/{decision_id}/outcome"

        assert lawyer_client.post(rota, json={"outcome": "ACORDO_ACEITO"}).status_code == 201
        assert lawyer_client.post(rota, json={"outcome": "SENTENCA_FAVORAVEL"}).status_code == 409


def test_banco_nao_registra_desfecho(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank, TestClient(app) as lawyer_client:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        login(lawyer_client, "adv@unicamp.br")
        case_id = make_case(bank, lawyer["id"])
        decision_id = decidir_e_obter_decisao(lawyer_client, case_id)

        assert bank.post(
            f"/api/cases/{case_id}/lawyer-decisions/{decision_id}/outcome",
            json={"outcome": "ACORDO_ACEITO"},
        ).status_code == 403


def test_processos_vem_do_mais_novo_para_o_mais_antigo(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        for numero in ("data-001", "data-002", "data-003"):
            make_case(bank, lawyer["id"], numero)

        datas = [item["created_at"] for item in bank.get("/api/cases").json()]
        assert datas == sorted(datas, reverse=True)


# ── Painel do advogado ───────────────────────────────────────────────────────

def test_painel_separa_exito_de_aderencia(tmp_path):
    """
    São medidas diferentes e o painel não pode confundi-las: o advogado abaixo
    acata a política em 100% das vezes e tem 50% de êxito.
    """
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank, TestClient(app) as lawyer_client:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        login(lawyer_client, "adv@unicamp.br")

        for numero, desfecho in (("perf-001", "ACORDO_ACEITO"), ("perf-002", "SENTENCA_DESFAVORAVEL")):
            case_id = make_case(bank, lawyer["id"], numero)
            decision_id = decidir_e_obter_decisao(lawyer_client, case_id)
            lawyer_client.post(
                f"/api/cases/{case_id}/lawyer-decisions/{decision_id}/outcome",
                json={"outcome": desfecho},
            )

        painel = lawyer_client.get("/api/lawyer/performance").json()
        assert painel["success_rate"] == 0.5
        assert painel["adherence_rate"] == 1.0
        assert painel["closed_cases"] == 2
        assert painel["active_cases"] == 0
        assert painel["outcomes"] == {"ACORDO_ACEITO": 1, "SENTENCA_DESFAVORAVEL": 1}


def test_painel_sem_desfecho_nao_inventa_taxa(tmp_path):
    """Zero desfecho registrado é None, nunca 0% — a tela precisa saber a diferença."""
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank, TestClient(app) as lawyer_client:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        login(lawyer_client, "adv@unicamp.br")
        make_case(bank, lawyer["id"])

        painel = lawyer_client.get("/api/lawyer/performance").json()
        assert painel["success_rate"] is None
        assert painel["adherence_rate"] is None
        assert painel["total_cases"] == 1
        assert painel["active_cases"] == 1


def test_painel_conta_pendencia_de_desfecho(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank, TestClient(app) as lawyer_client:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        login(bank, "banco@unicamp.br")
        login(lawyer_client, "adv@unicamp.br")
        case_id = make_case(bank, lawyer["id"])
        decidir_e_obter_decisao(lawyer_client, case_id)

        painel = lawyer_client.get("/api/lawyer/performance").json()
        assert painel["decisions"] == 1
        assert painel["pending_outcome"] == 1
        assert painel["outcomes_recorded"] == 0


def test_painel_e_do_proprio_advogado(tmp_path):
    """Um advogado não enxerga o desempenho do outro."""
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank, TestClient(app) as outro:
        add_user(app, "BANCO", "banco@unicamp.br")
        lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
        add_user(app, "ADVOGADO_EXTERNO", "outro@unicamp.br")
        login(bank, "banco@unicamp.br")
        login(outro, "outro@unicamp.br")
        make_case(bank, lawyer["id"])

        assert outro.get("/api/lawyer/performance").json()["total_cases"] == 0


def test_banco_nao_acessa_painel_do_advogado(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as bank:
        add_user(app, "BANCO", "banco@unicamp.br")
        login(bank, "banco@unicamp.br")

        assert bank.get("/api/lawyer/performance").status_code == 403


# ── Guardas de processo encerrado ────────────────────────────────────────────
#
# Todos valem na API, não só na tela: a tela esconde o botão, mas o endpoint
# continua chamável direto. Depois do desfecho o caso é histórico — mexer na
# prova reescreveria o alicerce de uma recomendação já emitida.

def caso_encerrado(app, bank, lawyer_client, lawyer_id, numero="fim-001"):
    case_id = make_case(bank, lawyer_id, numero)
    document = upload(bank, case_id)
    decision_id = decidir_e_obter_decisao(lawyer_client, case_id)
    lawyer_client.post(
        f"/api/cases/{case_id}/lawyer-decisions/{decision_id}/outcome",
        json={"outcome": "ACORDO_ACEITO"},
    )
    return case_id, document, decision_id


def cenario(tmp_path):
    app = create_app(settings(tmp_path))
    bank, lawyer_client = TestClient(app), TestClient(app)
    bank.__enter__(), lawyer_client.__enter__()
    add_user(app, "BANCO", "banco@unicamp.br")
    lawyer = add_user(app, "ADVOGADO_EXTERNO", "adv@unicamp.br")
    login(bank, "banco@unicamp.br")
    login(lawyer_client, "adv@unicamp.br")
    return app, bank, lawyer_client, lawyer["id"]


def test_encerrado_bloqueia_exclusao_de_documento(tmp_path):
    app, bank, lawyer_client, lawyer_id = cenario(tmp_path)
    case_id, document, _ = caso_encerrado(app, bank, lawyer_client, lawyer_id)

    resposta = bank.delete(f"/api/cases/{case_id}/documents/{document['id']}")
    assert resposta.status_code == 409
    assert "encerrado" in resposta.json()["detail"].lower()


def test_encerrado_bloqueia_novo_upload(tmp_path):
    app, bank, lawyer_client, lawyer_id = cenario(tmp_path)
    case_id, _, _ = caso_encerrado(app, bank, lawyer_client, lawyer_id)

    resposta = bank.post(
        f"/api/cases/{case_id}/documents",
        files={"file": ("novo.txt", b"conteudo novo do documento", "text/plain")},
        data={"declared_type": "EXTRATO", "source_party": "BANCO"},
    )
    assert resposta.status_code == 409


def test_encerrado_bloqueia_troca_de_advogado(tmp_path):
    app, bank, lawyer_client, lawyer_id = cenario(tmp_path)
    case_id, _, _ = caso_encerrado(app, bank, lawyer_client, lawyer_id)

    resposta = bank.patch(f"/api/cases/{case_id}/assignment", json={"assigned_lawyer_id": None})
    assert resposta.status_code == 409


def test_encerrado_bloqueia_nova_avaliacao(tmp_path):
    app, bank, lawyer_client, lawyer_id = cenario(tmp_path)
    case_id, _, _ = caso_encerrado(app, bank, lawyer_client, lawyer_id)

    assert lawyer_client.post(f"/api/cases/{case_id}/analyses").status_code == 409


def test_encerrado_bloqueia_nova_decisao(tmp_path):
    app, bank, lawyer_client, lawyer_id = cenario(tmp_path)
    case_id, _, _ = caso_encerrado(app, bank, lawyer_client, lawyer_id)
    analysis_id = bank.get(f"/api/cases/{case_id}").json()["analyses"][0]["id"]

    resposta = lawyer_client.post(
        f"/api/cases/{case_id}/lawyer-decisions?analysis_id={analysis_id}",
        json={"action": "DEFESA", "proposed_value": None, "reason": None},
    )
    assert resposta.status_code == 409


def test_decisao_e_unica_por_processo(tmp_path):
    """A segunda decisão não seria revisão: competiria com a primeira na aderência."""
    app, bank, lawyer_client, lawyer_id = cenario(tmp_path)
    case_id = make_case(bank, lawyer_id)
    decidir_e_obter_decisao(lawyer_client, case_id)
    analysis_id = bank.get(f"/api/cases/{case_id}").json()["analyses"][0]["id"]

    resposta = lawyer_client.post(
        f"/api/cases/{case_id}/lawyer-decisions?analysis_id={analysis_id}",
        json={"action": "DEFESA", "proposed_value": None, "reason": None},
    )
    assert resposta.status_code == 409
    assert "já tem decisão" in resposta.json()["detail"]


def test_decidido_ainda_aceita_documento_e_avaliacao(tmp_path):
    """
    Decidido não é encerrado. Enquanto a negociação corre, o banco ainda pode
    juntar o documento que faltava — é a terceira via da política.
    """
    app, bank, lawyer_client, lawyer_id = cenario(tmp_path)
    case_id = make_case(bank, lawyer_id)
    decidir_e_obter_decisao(lawyer_client, case_id)

    assert bank.get(f"/api/cases/{case_id}").json()["stage"] == "DECIDIDO"
    assert bank.post(
        f"/api/cases/{case_id}/documents",
        files={"file": ("extrato.txt", b"extrato recuperado do arquivo", "text/plain")},
        data={"declared_type": "EXTRATO", "source_party": "BANCO"},
    ).status_code == 201
    assert lawyer_client.post(f"/api/cases/{case_id}/analyses").status_code == 201


def test_estagio_acompanha_o_ciclo(tmp_path):
    app, bank, lawyer_client, lawyer_id = cenario(tmp_path)
    case_id = make_case(bank, lawyer_id)
    estagio = lambda: bank.get(f"/api/cases/{case_id}").json()["stage"]

    assert estagio() == "ABERTO"
    decision_id = decidir_e_obter_decisao(lawyer_client, case_id)
    assert estagio() == "DECIDIDO"
    lawyer_client.post(
        f"/api/cases/{case_id}/lawyer-decisions/{decision_id}/outcome",
        json={"outcome": "SENTENCA_FAVORAVEL"},
    )
    assert estagio() == "ENCERRADO"
