"""
Operação simulada para o painel do banco: 3 bancos, 5 escritórios, 13 advogados, ~1.160 processos.

O que é real e o que é inventado:
  - REAL: cada processo é sorteado da base de 60 mil sentenças (UF, valor da causa, subsídios) e,
    quando defendido, recebe o desfecho judicial e a condenação verdadeiros daquele processo.
  - REAL: a recomendação sai do motor de produção (`decidir`), com o contrato vigente.
  - INVENTADO: o comportamento dos advogados (perfis abaixo), a resposta da parte autora ao acordo
    (a base não tem nenhuma recusa registrada), os motivos de documento indisponível e o tempo de tela.

Bancos e escritórios são fictícios. Nenhum login é criado para os advogados simulados.
Uso: python -m scripts.seed_operacao_simulada --confirm-demo [--reset]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from contracts.schema import AnaliseDossie, CaseFeatures, Honorario, ParametrosContrato
from scripts.seed_demo import DEMO_DATABASE_PATH, seed_demo
from src.interface.backend.database import connection_for, initialize_database
from src.policy.referencia import chance_aceite
from src.interface.backend.repository import Repository
from src.policy.engine import decidir
from src.policy.service import ACAO_PARA_API, FEATURE_LABELS, PolicyService

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOMINIO = "sim.enteros.local"
SEMENTE = 2026

BANCOS = (
    ("banco-unicamp", "Banco Unicamp", 520),
    ("banco-horizonte-sim", "Banco Horizonte (simulado)", 320),
    ("banco-cerrado-sim", "Banco Cerrado (simulado)", 320),
)
ESCRITORIOS = (
    ("esc-almeida-rocha", "Almeida & Rocha Advogados"),
    ("esc-costa-lima", "Costa Lima Advocacia"),
    ("esc-nogueira-prado", "Nogueira Prado Advogados"),
    ("esc-vieira-sampaio", "Vieira & Sampaio Advocacia"),
    ("esc-barros-mendes", "Barros Mendes Advogados"),
)
# segue: chance de seguir a recomendação | desvio: o que escolhe quando não segue
# markup: quanto do espaço alvo→walk-away cede na oferta | abre_docs: chance de abrir cada documento
# minutos: tempo ativo típico por caso | carimbo: chance de decidir sem abrir nada
PERFIS = {
    "exemplar":    dict(segue=0.95, desvio="DEFESA", markup=0.00, abre_docs=0.95, minutos=7.0, carimbo=0.02),
    "consistente": dict(segue=0.88, desvio="DEFESA", markup=0.05, abre_docs=0.85, minutos=9.0, carimbo=0.05),
    "defensor":    dict(segue=0.66, desvio="DEFESA", markup=0.05, abre_docs=0.80, minutos=12.0, carimbo=0.04),
    "generoso":    dict(segue=0.90, desvio="ACORDO", markup=0.25, abre_docs=0.60, minutos=5.0, carimbo=0.15),
    "apressado":   dict(segue=0.84, desvio="ACORDO", markup=0.15, abre_docs=0.30, minutos=3.0, carimbo=0.45),
}
ADVOGADOS = (
    ("banco-unicamp", "esc-almeida-rocha", "Rafaela Menezes", "exemplar"),
    ("banco-unicamp", "esc-almeida-rocha", "Tiago Albuquerque", "consistente"),
    ("banco-unicamp", "esc-costa-lima", "Juliana Farias", "generoso"),
    ("banco-unicamp", "esc-costa-lima", "Marcos Teixeira", "apressado"),
    ("banco-unicamp", "esc-nogueira-prado", "Paulo Siqueira", "defensor"),
    ("banco-unicamp", "esc-nogueira-prado", "Lívia Campos", "consistente"),
    ("banco-horizonte-sim", "esc-almeida-rocha", "Bruna Fontes", "exemplar"),
    ("banco-horizonte-sim", "esc-costa-lima", "Diego Moura", "consistente"),
    ("banco-horizonte-sim", "esc-vieira-sampaio", "Carla Rezende", "defensor"),
    ("banco-cerrado-sim", "esc-almeida-rocha", "Henrique Dias", "consistente"),
    ("banco-cerrado-sim", "esc-costa-lima", "Sofia Pires", "exemplar"),
    ("banco-cerrado-sim", "esc-nogueira-prado", "Otávio Lins", "consistente"),
    ("banco-cerrado-sim", "esc-barros-mendes", "Renata Guedes", "generoso"),
)
MOTIVOS_POR_DOCUMENTO = {
    "CONTRATO": (("CONTRATO_FISICO_NAO_DIGITALIZADO", 0.35), ("CORRESPONDENTE_NAO_ENVIOU", 0.25),
                 ("NAO_LOCALIZADO", 0.15), ("OPERACAO_INEXISTENTE", 0.15), ("FORA_DO_PRAZO_DE_GUARDA", 0.10)),
    "EXTRATO": (("SISTEMA_SEM_EXPORTACAO", 0.45), ("NAO_LOCALIZADO", 0.25), ("FORA_DO_PRAZO_DE_GUARDA", 0.20), ("OUTRO", 0.10)),
    "COMPROVANTE_CREDITO": (("SISTEMA_SEM_EXPORTACAO", 0.50), ("NAO_LOCALIZADO", 0.30), ("OUTRO", 0.20)),
}
TEXTO_MOTIVO = {
    "CONTRATO_FISICO_NAO_DIGITALIZADO": "Contrato em papel no arquivo da agência, ainda não digitalizado.",
    "CORRESPONDENTE_NAO_ENVIOU": "Operação feita por correspondente, que não enviou a via assinada.",
    "NAO_LOCALIZADO": "Documento não localizado nos sistemas consultados.",
    "OPERACAO_INEXISTENTE": "Não há registro de contratação para o CPF: indício de fraude.",
    "FORA_DO_PRAZO_DE_GUARDA": "Documento descartado conforme a tabela de temporalidade.",
    "SISTEMA_SEM_EXPORTACAO": "Sistema legado não permite exportar o documento por operação.",
    "OUTRO": "Área responsável não retornou dentro do prazo.",
}
# O contrato padrão vira uma versão registrada, com os mesmos parâmetros do padrão: a aba Contrato
# mostra histórico e justificativa, e nenhuma recomendação muda.
JUSTIFICATIVA_PADRAO = ("Contrato padrão 2026: mensalidade e valor fixo por processo novo são pagos em qualquer "
                        "desfecho e não mudam a decisão; honorários por desfecho ficam em cada escritório.")
MOTIVOS_DE_DIVERGENCIA = ("FATO_NOVO", "ENTENDIMENTO_LOCAL", "PROVA_MAIS_FRACA", "PROVA_MAIS_FORTE", "SINAL_DO_AUTOR")
DOCUMENTO_DO_PLANO = {"contrato": "CONTRATO", "extrato": "EXTRATO", "comprovante_credito": "COMPROVANTE_CREDITO"}
TIPOS_DOCUMENTO = {"contrato": "CONTRATO", "extrato": "EXTRATO", "comprovante_credito": "COMPROVANTE_CREDITO",
                   "dossie": "DOSSIE", "demonstrativo": "DEMONSTRATIVO_DIVIDA", "laudo": "LAUDO_REFERENCIADO"}


def _base() -> list[dict]:
    try:
        with open(DATA / "subsidios.csv", encoding="utf-8") as arquivo:
            subsidios = {r["Número do processos"]: r for r in csv.DictReader(arquivo)}
        with open(DATA / "resultados.csv", encoding="utf-8") as arquivo:
            resultados = list(csv.DictReader(arquivo))
    except FileNotFoundError as exc:
        raise SystemExit("Base histórica ausente em data/. Rode: python -m scripts.exportar_base_csv --xlsx <planilha>") from exc
    linhas = []
    for r in resultados:
        s = subsidios[r["Número do processo"]]
        flag = lambda coluna: bool(int(float(s[coluna])))
        linhas.append({
            "numero": r["Número do processo"], "uf": r["UF"], "sub_assunto": r["Sub-assunto"],
            "causa": float(r["Valor da causa"]), "exito": r["Resultado macro"] == "Êxito",
            "condenacao": float(r["Valor da condenação/indenização"] or 0),
            "contrato": flag("Contrato"), "extrato": flag("Extrato"), "comprovante_credito": flag("Comprovante de crédito"),
            "dossie": flag("Dossiê"), "demonstrativo": flag("Demonstrativo de evolução da dívida"),
            "laudo": flag("Laudo referenciado"),
        })
    return linhas


def _escolha(rng: random.Random, pesos: tuple[tuple[str, float], ...]) -> str:
    return rng.choices([m for m, _ in pesos], weights=[p for _, p in pesos])[0]


def _iso(momento: datetime) -> str:
    return momento.isoformat()


def limpar(connection) -> None:
    casos = "SELECT id FROM cases WHERE is_simulated = 1"
    for tabela in ("divergence_balances", "engagement_events", "negotiation_outcomes", "judicial_outcomes",
                   "document_requests", "lawyer_decisions", "analyses"):
        connection.execute(f"DELETE FROM {tabela} WHERE case_id IN ({casos})")
    connection.execute("DELETE FROM cases WHERE is_simulated = 1")
    ids_escritorios = tuple(e[0] for e in ESCRITORIOS)
    marcadores = ",".join("?" * len(ids_escritorios))
    connection.execute(f"DELETE FROM bank_contracts WHERE law_firm_id IN ({marcadores})", ids_escritorios)
    connection.execute("DELETE FROM bank_contracts WHERE bank_id = 'banco-unicamp' AND law_firm_id IS NULL AND justification = ?",
                       (JUSTIFICATIVA_PADRAO,))
    connection.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE email LIKE ?)", (f"%@{DOMINIO}",))
    connection.execute("DELETE FROM users WHERE email LIKE ?", (f"%@{DOMINIO}",))
    connection.execute(f"UPDATE users SET law_firm_id = NULL WHERE law_firm_id IN ({marcadores})", ids_escritorios)
    connection.execute(f"DELETE FROM law_firms WHERE id IN ({marcadores})", ids_escritorios)
    connection.execute("DELETE FROM banks WHERE id IN (?, ?)", (BANCOS[1][0], BANCOS[2][0]))


def simular(database_path: Path, *, reset: bool = False, agora: datetime | None = None) -> dict:
    seed_demo(database_path)
    initialize_database(database_path)
    rng = random.Random(SEMENTE)
    agora = agora or datetime.now(UTC)
    base = _base()
    contagem = {"casos": 0, "decisoes": 0, "negociacoes": 0, "desfechos": 0, "pedidos": 0, "eventos": 0}

    with connection_for(database_path) as connection:
        ja_existe = connection.execute("SELECT COUNT(*) FROM cases WHERE is_simulated = 1").fetchone()[0]
        if ja_existe and not reset:
            raise ValueError(f"Já existem {ja_existe} processos simulados. Use --reset para recriar.")
        limpar(connection)

        criado = _iso(agora)
        for bank_id, nome, _ in BANCOS:
            connection.execute("INSERT OR IGNORE INTO banks (id, name, created_at) VALUES (?, ?, ?)", (bank_id, nome, criado))
        for firm_id, nome in ESCRITORIOS:
            connection.execute("INSERT INTO law_firms (id, name, created_at) VALUES (?, ?, ?)", (firm_id, nome, criado))

        # Contas demo: o usuário do banco é o gestor; a advogada demo passa a ter escritório.
        connection.execute("UPDATE users SET is_manager = 1 WHERE email = 'banco@demo.local'")
        connection.execute("UPDATE users SET law_firm_id = ? WHERE email = 'advogada@demo.local'", (ESCRITORIOS[0][0],))
        gestor = connection.execute("SELECT id FROM users WHERE email = 'banco@demo.local'").fetchone()

        advogados: dict[str, list[dict]] = {}
        for bank_id, firm_id, nome, perfil in ADVOGADOS:
            user_id = f"sim-{uuid4().hex[:12]}"
            email = f"{nome.split()[0].lower()}.{bank_id.split('-')[1]}@{DOMINIO}".replace("í", "i").replace("á", "a")
            connection.execute(
                """INSERT INTO users (id, name, email, password_hash, role, bank_id, is_active, created_at, law_firm_id, is_manager)
                VALUES (?, ?, ?, '!sem-login', 'ADVOGADO_EXTERNO', ?, 1, ?, ?, 0)""",
                (user_id, nome, email, bank_id, criado, firm_id))
            advogados.setdefault(bank_id, []).append({"id": user_id, "firm": firm_id, "perfil": PERFIS[perfil]})
        # A advogada demo também atua na operação, com perfil exemplar: a fila dela tem processos em
        # todas as fases e ela aparece no ranking com histórico, como os demais advogados.
        demo = connection.execute("SELECT id FROM users WHERE email = 'advogada@demo.local'").fetchone()
        if demo:
            advogados["banco-unicamp"].append({"id": demo["id"], "firm": ESCRITORIOS[0][0], "perfil": PERFIS["exemplar"]})

        connection.execute(
            """INSERT INTO bank_contracts (id, bank_id, version, parameters, created_by_user_id, created_at, law_firm_id, justification)
            VALUES (?, 'banco-unicamp', (SELECT COALESCE(MAX(version), 0) + 1 FROM bank_contracts WHERE bank_id = 'banco-unicamp'),
            ?, ?, ?, NULL, ?)""",
            (str(uuid4()), json.dumps(ParametrosContrato().model_dump(exclude={"versao"})), gestor["id"] if gestor else None,
             _iso(agora - timedelta(days=150)), JUSTIFICATIVA_PADRAO))

        # Contrato próprio de um escritório: defesa perdida mais cara muda a fronteira acordo x defesa.
        contrato_nogueira = ParametrosContrato(
            honorario_defesa_perdida=Honorario(tipo="percentual_valor_causa", valor=0.10))
        connection.execute(
            """INSERT INTO bank_contracts (id, bank_id, version, parameters, created_by_user_id, created_at, law_firm_id, justification)
            VALUES (?, 'banco-unicamp', (SELECT COALESCE(MAX(version), 0) + 1 FROM bank_contracts WHERE bank_id = 'banco-unicamp'),
            ?, ?, ?, ?, ?)""",
            (str(uuid4()), json.dumps(contrato_nogueira.model_dump(exclude={"versao"})), gestor["id"] if gestor else None,
             _iso(agora - timedelta(days=130)), "esc-nogueira-prado",
             "Aditivo de 2026: honorário de 10% da causa quando a defesa perde."))
        versao_nogueira = connection.execute(
            "SELECT version FROM bank_contracts WHERE law_firm_id = 'esc-nogueira-prado' ORDER BY version DESC LIMIT 1").fetchone()[0]
        contrato_nogueira = contrato_nogueira.model_copy(update={"versao": f"banco-unicamp-v{versao_nogueira}"})

        amostra = rng.sample(base, sum(n for *_, n in BANCOS))
        cursor = 0
        for bank_id, _, quantidade in BANCOS:
            for linha in amostra[cursor:cursor + quantidade]:
                _simular_caso(connection, rng, agora, bank_id, linha, advogados[bank_id],
                              contrato_nogueira, contagem)
            cursor += quantidade
    repositorio = Repository(database_path)
    with connection_for(database_path) as connection:
        simulados = [row[0] for row in connection.execute("SELECT id FROM cases WHERE is_simulated = 1")]
    contagem["saldos_de_divergencia"] = sum(repositorio.refresh_divergence_balance(case_id) is not None for case_id in simulados)
    return contagem


def _simular_caso(connection, rng, agora, bank_id, linha, advogados, contrato_nogueira, contagem) -> None:
    advogado = rng.choice(advogados)
    perfil = advogado["perfil"]
    case_id = str(uuid4())
    aberto = agora - timedelta(days=rng.uniform(2, 120), hours=rng.uniform(0, 23))
    connection.execute(
        """INSERT INTO cases (id, case_number, uf, value_of_claim, sub_subject, dossie_status, created_at, bank_id,
        assigned_lawyer_id, created_by_user_id, is_simulated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)""",
        (case_id, linha["numero"], linha["uf"], linha["causa"], linha["sub_assunto"],
         "PRESENTE" if linha["dossie"] else "AUSENTE", _iso(aberto), bank_id, advogado["id"]))
    contagem["casos"] += 1
    if (agora - aberto).days < 4 and rng.random() < 0.6:
        return  # recém-chegado: ainda sem análise

    # Dossiê: 65% já analisado pela IA (periciou a assinatura), 5% não conforme, 30% ainda sem análise.
    analise, sorteio = None, rng.random()
    if linha["dossie"] and sorteio < 0.65:
        analise = AnaliseDossie(veredito="conforme", analisou_assinatura_contrato=True)
    elif linha["dossie"] and sorteio < 0.70:
        analise = AnaliseDossie(veredito="nao_conforme", analisou_assinatura_contrato=False)
    features = CaseFeatures(
        numero_processo=linha["numero"], uf=linha["uf"],
        sub_assunto="Golpe" if linha["sub_assunto"] == "Golpe" else "Generico", valor_causa=linha["causa"],
        analise_dossie=analise, **{k: linha[k] for k in TIPOS_DOCUMENTO})
    contrato = contrato_nogueira if advogado["firm"] == "esc-nogueira-prado" and bank_id == "banco-unicamp" else ParametrosContrato()
    r = decidir(features, contrato)
    recomendacao = ACAO_PARA_API[r.acao]
    limitacoes = list(r.alertas)
    if linha["dossie"] and analise is None:
        limitacoes.append("Dossiê presente sem análise concluída: a recomendação não usa o conteúdo dele.")

    analisado = aberto + timedelta(hours=rng.uniform(4, 96))
    connection.execute(
        """INSERT INTO analyses (id, case_id, recommendation, decision_code, policy_source, agreement_probability,
        documentary_status, reasons, feature_vector, feature_provenance, pricing, limitations, policy_output,
        policy_version, contract_version, created_at) VALUES (?, ?, ?, ?, 'TABELA_SEGMENTOS', NULL, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?)""",
        (analysis_id := str(uuid4()), case_id, recomendacao, PolicyService._decision_code(r),
         "SUSTENTADA_COM_RESSALVAS" if limitacoes else "SUSTENTADA_DOCUMENTALMENTE",
         json.dumps(r.justificativa, ensure_ascii=False),
         json.dumps({**{FEATURE_LABELS[k]: int(linha[k if k != "comprovante_credito" else "comprovante_credito"]) for k in FEATURE_LABELS},
                     "is_golpe": int(features.sub_assunto == "Golpe")}, ensure_ascii=False),
         json.dumps(PolicyService._pricing(r)) if r.acordo else None,
         json.dumps(limitacoes, ensure_ascii=False), json.dumps(r.model_dump(mode="json"), ensure_ascii=False),
         r.versao_politica, r.versao_contrato, _iso(analisado)))

    # Engajamento: abrir o caso, conferir documentos, tempo de tela.
    user = advogado["id"]
    eventos = [("CASE_OPENED", None, 0, analisado - timedelta(minutes=rng.uniform(2, 20))),
               ("ANALYSIS_RUN", None, 0, analisado)]
    carimbo = rng.random() < perfil["carimbo"]
    presentes = [t for k, t in TIPOS_DOCUMENTO.items() if linha[k]]
    if not carimbo:
        for tipo in presentes:
            if rng.random() < perfil["abre_docs"]:
                eventos.append(("DOCUMENT_OPENED", f"sim-{case_id[:8]}-{tipo}", 0, analisado + timedelta(minutes=rng.uniform(1, 15))))
    decidido = min(agora - timedelta(minutes=5), analisado + timedelta(hours=rng.uniform(0.2, 60)))

    # Decisão do advogado conforme o perfil.
    if rng.random() < perfil["segue"]:
        acao = recomendacao
    else:
        acao = perfil["desvio"] if perfil["desvio"] != recomendacao else ("DEFESA" if recomendacao == "ACORDO" else "ACORDO")
    faixa = r.acordo
    proposto = None
    if acao == "ACORDO":
        if faixa:
            base_oferta = r.valor_recomendado or faixa.alvo
            proposto = base_oferta + perfil["markup"] * max(0.0, faixa.walk_away - base_oferta) * rng.uniform(0.6, 1.5)
        else:
            proposto = 0.29 * linha["causa"] * (1 + perfil["markup"])
        proposto = round(proposto, 2)
    decision_id = str(uuid4())
    connection.execute(
        """INSERT INTO lawyer_decisions (id, case_id, analysis_id, action, reason, proposed_value, created_at, lawyer_id,
        divergence_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (decision_id, case_id, analysis_id, acao,
         None if acao == recomendacao else "Divergência registrada pelo advogado.", proposto, _iso(decidido), user,
         None if acao == recomendacao else rng.choice(MOTIVOS_DE_DIVERGENCIA)))
    eventos.append(("DECISION_REGISTERED", None, 0, decidido))
    contagem["decisoes"] += 1

    idade_decisao = (agora - decidido).days
    negociacao_falhou = False
    if acao == "ACORDO" and (idade_decisao >= 5 or rng.random() < 0.5):
        abertura = faixa.abertura if faixa else 0.29 * linha["causa"]
        # A curva dos acordos da base, um pouco abaixo: a operação simulada aceita menos que o histórico.
        p_aceita = chance_aceite(proposto, linha["causa"], fator=0.8)
        momento = decidido + timedelta(days=rng.uniform(1, 10))
        momento = min(momento, agora - timedelta(minutes=1))
        if rng.random() < p_aceita:
            _negociacao(connection, case_id, decision_id, user, "ACEITO", proposto, None, proposto, momento)
            _encerrar(connection, decision_id, "ACORDO_ACEITO", momento)
        else:
            sorteio = rng.random()
            if sorteio < 0.25:
                contra = round(proposto * rng.uniform(1.2, 1.6), 2)
                _negociacao(connection, case_id, decision_id, user, "CONTRAPROPOSTA", proposto, contra, None, momento)
                momento = min(momento + timedelta(days=rng.uniform(1, 5)), agora - timedelta(seconds=30))
                if perfil["markup"] >= 0.35:
                    _negociacao(connection, case_id, decision_id, user, "ACEITO", proposto, contra, contra, momento)
                    _encerrar(connection, decision_id, "ACORDO_ACEITO", momento)
                else:
                    _negociacao(connection, case_id, decision_id, user, "RECUSADO", proposto, contra, None, momento)
                    negociacao_falhou = True
            else:
                status = "RECUSADO" if sorteio < 0.85 else "SEM_RESPOSTA"
                _negociacao(connection, case_id, decision_id, user, status, proposto, None, None, momento)
                negociacao_falhou = True
        eventos.append(("OUTCOME_REGISTERED", None, 0, momento))
        contagem["negociacoes"] += 1

    if (acao == "DEFESA" or negociacao_falhou) and idade_decisao > 40 and rng.random() < 0.6:
        momento = min(decidido + timedelta(days=rng.uniform(30, idade_decisao)), agora - timedelta(seconds=10))
        connection.execute(
            """INSERT INTO judicial_outcomes (id, case_id, lawyer_id, result, condemnation_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid4()), case_id, user, "EXITO" if linha["exito"] else "NAO_EXITO",
             0.0 if linha["exito"] else linha["condenacao"], _iso(momento)))
        _encerrar(connection, decision_id, "SENTENCA_FAVORAVEL" if linha["exito"] else "SENTENCA_DESFAVORAVEL", momento)
        eventos.append(("OUTCOME_REGISTERED", None, 0, momento))
        contagem["desfechos"] += 1

    if acao == "RECUPERAR" and r.recuperacao is not None:
        tipo = DOCUMENTO_DO_PLANO[r.recuperacao.documento]
        status, motivo, fonte, respondido = "REQUESTED", None, None, None
        if idade_decisao >= 3 and rng.random() < 0.75:
            respondido = min(decidido + timedelta(days=rng.uniform(1, 14)), agora - timedelta(seconds=5))
            if rng.random() < 0.4:
                status = "SUBMITTED"
            else:
                status = "DECLARED_UNAVAILABLE"
                motivo = _escolha(rng, MOTIVOS_POR_DOCUMENTO[tipo])
                fonte = "IA" if rng.random() < 0.2 else "INFORMADO"
        connection.execute(
            """INSERT INTO document_requests (id, case_id, document_type, hypothesis_key, reason, due_date, status,
            created_at, responded_at, response_reason, unavailability_reason, unavailability_reason_source)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)""",
            (str(uuid4()), case_id, tipo, f"politica:{r.recuperacao.documento}", r.recuperacao.fundamento[:1000], status,
             _iso(decidido), _iso(respondido) if respondido else None,
             TEXTO_MOTIVO[motivo] if motivo else None, motivo, fonte))
        contagem["pedidos"] += 1

    for tipo, documento, segundos_evento, momento in eventos:
        connection.execute(
            """INSERT INTO engagement_events (id, case_id, user_id, event_type, document_id, active_seconds, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid4()), case_id, user, tipo, documento, segundos_evento, _iso(min(momento, agora))))
        contagem["eventos"] += 1


def _encerrar(connection, decision_id, desfecho, momento) -> None:
    """Desfecho final também no ciclo de vida da decisão (processo ENCERRADO)."""
    connection.execute("UPDATE lawyer_decisions SET outcome = ?, outcome_at = ? WHERE id = ? AND outcome IS NULL",
                       (desfecho, _iso(momento), decision_id))


def _negociacao(connection, case_id, decision_id, user, status, oferta, contra, fechado, momento) -> None:
    connection.execute(
        """INSERT INTO negotiation_outcomes (id, case_id, decision_id, lawyer_id, status, offered_value, counter_value,
        closed_value, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid4()), case_id, decision_id, user, status, oferta, contra, fechado, _iso(momento)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Popula .runtime/demo com uma operação simulada para o painel do banco.")
    parser.add_argument("--confirm-demo", action="store_true", help="Confirma uso local; nunca use em produção.")
    parser.add_argument("--reset", action="store_true", help="Apaga a operação simulada anterior e recria.")
    parser.add_argument("--database", type=Path, default=DEMO_DATABASE_PATH)
    arguments = parser.parse_args()
    if not arguments.confirm_demo:
        parser.error("Informe --confirm-demo para criar a operação simulada local.")
    try:
        contagem = simular(arguments.database, reset=arguments.reset)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Operação simulada criada em {arguments.database}: " + ", ".join(f"{k} {v}" for k, v in contagem.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
