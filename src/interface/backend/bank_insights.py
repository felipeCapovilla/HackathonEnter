"""
Painel da empresa: só números OBSERVADOS.

Economia de um processo encerrado = custo médio REAL de processos parecidos na base (mesmos documentos,
alegação e região) − quanto este processo custou de fato. O painel mostra a soma, nunca um processo
isolado. Estimativas do modelo decidem, mas não medem o próprio resultado: o saldo estimado das
divergências fica guardado por dentro (divergencias.py) e não aparece aqui.

Score de advogado e escritório (0 a 100): cada processo vira notas de 0 a 1 que não dependem do valor
da causa, e o score mistura as médias — resultado 50%, preço do acordo 20%, aderência 20%, aceitação 10%
— puxado para a média da empresa quando há poucos processos encerrados.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from src.policy import table
from src.policy.constants import P3, P4, RATIO_CONDENACAO
from src.policy.referencia import acordos as referencia_acordos, custo_parecidos, posicao_no_mercado

ARTEFATO_BASE = Path(__file__).resolve().parents[3] / "artefatos" / "insights_base_historica.json"

MIN_ENCERRADOS_RANKING = 20
MIN_OUTROS_CLIENTES = 2
MIN_ENCERRADOS_MERCADO = 50
PESO_DA_MEDIA = 10
PESOS = {"resultado": 0.5, "preco": 0.2, "aderencia": 0.2, "aceitacao": 0.1}

DOC_NOMES = {"CONTRATO": "Contrato", "EXTRATO": "Extrato", "COMPROVANTE_CREDITO": "Comprovante de crédito",
             "DOSSIE": "Dossiê", "DEMONSTRATIVO_DIVIDA": "Demonstrativo da dívida",
             "LAUDO_REFERENCIADO": "Laudo referenciado", "AUTOS": "Autos", "OUTRO": "Outro"}
FEATURE_DOC = {"CONTRATO": "Contrato", "EXTRATO": "Extrato", "COMPROVANTE_CREDITO": "Comprovante de crédito"}
MOTIVOS = {
    "NAO_LOCALIZADO": "Não localizado",
    "CONTRATO_FISICO_NAO_DIGITALIZADO": "Contrato físico não digitalizado",
    "CORRESPONDENTE_NAO_ENVIOU": "Correspondente não enviou",
    "FORA_DO_PRAZO_DE_GUARDA": "Fora do prazo de guarda",
    "SISTEMA_SEM_EXPORTACAO": "Sistema sem exportação",
    "OPERACAO_INEXISTENTE": "Operação não existe (golpe)",
    "OUTRO": "Outro",
}
MOTIVOS_DIVERGENCIA = {
    "FATO_NOVO": "Fato ou documento que a recomendação não considerou",
    "ENTENDIMENTO_LOCAL": "O juízo ou a comarca costuma decidir diferente",
    "PROVA_MAIS_FRACA": "A prova da empresa é mais fraca do que parece",
    "PROVA_MAIS_FORTE": "A prova da empresa é mais forte do que parece",
    "SINAL_DO_AUTOR": "O autor sinalizou outro valor",
    "OUTRO": "Outro motivo",
}
ACOES = {"ACORDO": "acordo", "DEFESA": "defesa", "RECUPERAR": "pedir documento"}
CATALOGO = {
    "CONTRATO_FISICO_NAO_DIGITALIZADO": (
        "Operações de crédito + TI",
        "Digitalizar o legado e gravar todo contrato novo num repositório único (object storage, ex.: S3) "
        "indexado pelo número da operação, com assinatura eletrônica já na originação.",
        "Contratos localizados em até 48 h"),
    "CORRESPONDENTE_NAO_ENVIOU": (
        "Canais e correspondentes bancários",
        "Condicionar o pagamento da comissão do correspondente ao envio do contrato e do comprovante no ato da contratação.",
        "% de operações de correspondente com contrato anexado"),
    "NAO_LOCALIZADO": (
        "TI / Arquitetura de dados",
        "Criar um índice único de documentos por operação (número, CPF, data) ligando originação, sistema de crédito e jurídico.",
        "Tempo médio para localizar um documento"),
    "FORA_DO_PRAZO_DE_GUARDA": (
        "Jurídico + Compliance",
        "Revisar a tabela de temporalidade: guardar contrato e extrato enquanto couber ação judicial, não só pelo prazo regulatório mínimo.",
        "Pedidos negados por prazo de guarda"),
    "SISTEMA_SEM_EXPORTACAO": (
        "TI do sistema de crédito",
        "Expor uma API de subsídios por operação e anexar extrato e comprovante automaticamente quando o processo chega à plataforma.",
        "% de processos que chegam com extrato anexado"),
    "OPERACAO_INEXISTENTE": (
        "Prevenção a fraudes",
        "Não há documento a recuperar: é sinal de golpe. Priorizar acordo rápido e revisar a esteira de originação onde esses casos se concentram.",
        "Casos de golpe por canal de originação"),
    "OUTRO": (
        "Jurídico interno",
        "Ler os motivos livres recorrentes e transformá-los em categoria nova do formulário.",
        "% de respostas classificadas como Outro"),
}
CATALOGO_DOC = {
    ("COMPROVANTE_CREDITO", "SISTEMA_SEM_EXPORTACAO"): (
        "Compliance + TI",
        "Automatizar a consulta do registro regulatório da operação e anexar o comprovante ao processo sem pedido manual.",
        "% de processos que chegam com comprovante anexado"),
}


@lru_cache(maxsize=1)
def base_historica() -> dict | None:
    try:
        return json.loads(ARTEFATO_BASE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _ratio(numerador: float, denominador: float) -> float | None:
    return round(numerador / denominador, 4) if denominador else None


def _media(valores: list[float]) -> float | None:
    return statistics.mean(valores) if valores else None


def _pct(valor: float) -> str:
    return f"{valor:.1%}".replace(".", ",")


def _brl(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


# ─────────────────────────────────────────────────────────────────────────────
# Carga: uma linha por processo com a última decisão e o que aconteceu depois.
# ─────────────────────────────────────────────────────────────────────────────

def _carregar_decisoes(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute("""
        SELECT d.id AS decision_id, d.case_id, d.action, d.proposed_value, d.created_at AS decided_at,
               d.outcome AS decision_outcome, d.outcome_at, d.divergence_reason,
               COALESCE(d.lawyer_id, c.assigned_lawyer_id) AS lawyer_id,
               a.recommendation, a.pricing, a.limitations, a.feature_vector,
               c.bank_id, c.case_number, c.uf, c.value_of_claim, c.sub_subject,
               u.name AS lawyer_name, u.law_firm_id, f.name AS law_firm_name
        FROM lawyer_decisions d
        JOIN analyses a ON a.id = d.analysis_id
        JOIN cases c ON c.id = d.case_id
        LEFT JOIN users u ON u.id = COALESCE(d.lawyer_id, c.assigned_lawyer_id)
        LEFT JOIN law_firms f ON f.id = u.law_firm_id
        ORDER BY d.created_at""").fetchall()
    ultima: dict[str, dict] = {}
    for row in rows:
        ultima[row["case_id"]] = dict(row)

    negociacoes: dict[str, list[dict]] = defaultdict(list)
    for row in connection.execute("SELECT * FROM negotiation_outcomes ORDER BY created_at"):
        negociacoes[row["decision_id"]].append(dict(row))
    judiciais: dict[str, dict] = {}
    for row in connection.execute("SELECT * FROM judicial_outcomes ORDER BY created_at"):
        judiciais[row["case_id"]] = dict(row)
    abertos: dict[str, set] = defaultdict(set)
    for row in connection.execute("SELECT case_id, document_id FROM engagement_events WHERE event_type = 'DOCUMENT_OPENED'"):
        if row["document_id"]:
            abertos[row["case_id"]].add(row["document_id"])

    return [_avaliar(d, negociacoes.get(d["decision_id"], []), judiciais.get(d["case_id"]), len(abertos.get(d["case_id"], ())))
            for d in ultima.values()]


def _avaliar(d: dict, negociacoes: list[dict], judicial: dict | None, documentos_abertos: int) -> dict:
    pricing = json.loads(d["pricing"]) if d["pricing"] else {}
    features = json.loads(d["feature_vector"]) if d["feature_vector"] else {}
    limitations = json.loads(d["limitations"]) if d["limitations"] else []
    causa = float(d["value_of_claim"] or 0.0)
    sub = "Golpe" if "golpe" in (d["sub_subject"] or "").lower() else "Generico"
    desfecho = d["decision_outcome"]

    aceite = next((n for n in negociacoes if n["status"] == "ACEITO"), None)
    final = negociacoes[-1]["status"] if negociacoes else None
    fechado = float(aceite["closed_value"]) if aceite else None
    encerrado, gasto, encerrado_em, resultado_judicial = False, None, None, None
    if fechado is not None:
        encerrado, gasto, encerrado_em = True, fechado, aceite["created_at"]
    elif judicial is not None:
        encerrado, encerrado_em = True, judicial["created_at"]
        gasto, resultado_judicial = float(judicial["condemnation_value"] or 0.0), judicial["result"]
    elif desfecho == "ACORDO_ACEITO" and d["proposed_value"]:
        fechado = float(d["proposed_value"])
        encerrado, gasto, encerrado_em = True, fechado, d["outcome_at"]
    elif desfecho == "SENTENCA_FAVORAVEL":
        encerrado, gasto, encerrado_em, resultado_judicial = True, 0.0, d["outcome_at"], "EXITO"
    elif desfecho == "SENTENCA_DESFAVORAVEL":
        encerrado, encerrado_em, resultado_judicial = True, d["outcome_at"], "NAO_EXITO"  # sem valor: fora da economia

    if fechado is not None or desfecho == "ACORDO_ACEITO":
        aceito = True
    elif final in {"RECUSADO", "SEM_RESPOSTA"} or desfecho == "ACORDO_RECUSADO":
        aceito = False
    else:
        aceito = None

    referencia = (custo_parecidos(bool(features.get("Contrato")), bool(features.get("Extrato")),
                                  bool(features.get("Comprovante de crédito")), sub, d["uf"], causa) if causa > 0 else None)
    base = referencia["valor"] if referencia else None
    economia = base - gasto if encerrado and gasto is not None and base is not None else None
    aderente = d["recommendation"] == d["action"]
    return {
        **{k: d[k] for k in ("case_id", "case_number", "bank_id", "lawyer_id", "lawyer_name", "law_firm_id", "law_firm_name")},
        "recomendacao": d["recommendation"], "acao": d["action"], "aderente": aderente,
        "motivo_divergencia": d["divergence_reason"], "valor_causa": causa,
        "decidido_em": _parse_date(d["decided_at"]), "encerrado": encerrado, "encerrado_em": _parse_date(encerrado_em),
        "gasto": gasto, "base_parecidos": base, "economia": economia, "fechado": fechado, "aceito": aceito,
        "proposto": d["action"] == "ACORDO", "resultado_judicial": resultado_judicial,
        "limite": pricing.get("walk_away_value"), "com_ressalva": bool(limitations), "documentos_abertos": documentos_abertos,
        "notas": {
            "resultado": (max(-1.0, min(1.0, economia / base)) + 1) / 2 if economia is not None and base else None,
            "preco": 1 - posicao_no_mercado(fechado, causa) if fechado is not None and causa > 0 else None,
            "aderencia": 1.0 if aderente else 0.5 if d["divergence_reason"] else 0.0,
            "aceitacao": None if aceito is None else float(aceito),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Score e agregações
# ─────────────────────────────────────────────────────────────────────────────

def _score(itens: list[dict], media_de_referencia: float | None) -> dict:
    medias = {chave: _media([x["notas"][chave] for x in itens if x["notas"][chave] is not None]) for chave in PESOS}
    disponiveis = {chave: media for chave, media in medias.items() if media is not None}
    bruta = (sum(PESOS[c] * m for c, m in disponiveis.items()) / sum(PESOS[c] for c in disponiveis)) if disponiveis else None
    encerrados = sum(x["encerrado"] for x in itens)
    if bruta is None:
        nota = media_de_referencia
    elif media_de_referencia is None:
        nota = bruta
    else:
        nota = (encerrados * bruta + PESO_DA_MEDIA * media_de_referencia) / (encerrados + PESO_DA_MEDIA)
    fechados = [x for x in itens if x["fechado"] is not None]
    respondidos = [x for x in itens if x["aceito"] is not None]
    economias = [x["economia"] for x in itens if x["economia"] is not None]
    return {
        "nota": round(nota * 100) if nota is not None else None,
        "nota_bruta": bruta,
        "componentes": {chave: round(media * 100) if media is not None else None for chave, media in medias.items()},
        "encerrados": encerrados, "decisoes": len(itens),
        "aderencia": _ratio(sum(x["aderente"] for x in itens), len(itens)),
        "aceitacao": _ratio(sum(bool(x["aceito"]) for x in respondidos), len(respondidos)),
        "ticket_medio": round(statistics.mean(x["fechado"] for x in fechados), 2) if fechados else None,
        "ticket_sobre_causa": round(statistics.mean(x["fechado"] / x["valor_causa"] for x in fechados if x["valor_causa"]), 4) if fechados else None,
        "economia_total": round(sum(economias), 2),
        "amostra_suficiente": encerrados >= MIN_ENCERRADOS_RANKING,
    }


def _efetividade(itens: list[dict]) -> dict:
    encerrados = [x for x in itens if x["encerrado"]]
    com_valor = [x for x in encerrados if x["gasto"] is not None]
    com_economia = [x for x in encerrados if x["economia"] is not None]
    fechados = [x for x in itens if x["fechado"] is not None]
    respondidos = [x for x in itens if x["aceito"] is not None]
    propostos = [x for x in itens if x["proposto"]]
    defendidos = [x for x in encerrados if x["resultado_judicial"] is not None]
    defendidos_com_valor = [x for x in defendidos if x["gasto"] is not None and x["base_parecidos"] is not None]
    referencia = referencia_acordos()
    semanas: dict[str, dict] = defaultdict(lambda: {"encerrados": 0, "economia": 0.0})
    for x in com_economia:
        if x["encerrado_em"] is None:
            continue
        ano, semana, _ = x["encerrado_em"].isocalendar()
        s = semanas[f"{ano}-S{semana:02d}"]
        s["encerrados"] += 1
        s["economia"] += x["economia"]
    return {
        "encerrados": len(encerrados),
        "pendentes": len(itens) - len(encerrados),
        "economia": {
            "total": round(sum(x["economia"] for x in com_economia), 2), "processos": len(com_economia),
            # Observado dos dois lados: separa o resultado da política do resultado de quem não a seguiu.
            "seguiu": round(sum(x["economia"] for x in com_economia if x["aderente"]), 2),
            "seguiu_processos": sum(x["aderente"] for x in com_economia),
            "divergiu": round(sum(x["economia"] for x in com_economia if not x["aderente"]), 2),
            "divergiu_processos": sum(not x["aderente"] for x in com_economia),
        },
        "pior_caso": round(sum(x["valor_causa"] for x in com_valor), 2),
        "gasto_real": round(sum(x["gasto"] for x in com_valor), 2),
        "ticket": {
            "acordos_fechados": len(fechados),
            "ticket_medio": round(statistics.mean(x["fechado"] for x in fechados), 2) if fechados else None,
            "ticket_mediano": round(statistics.median(x["fechado"] for x in fechados), 2) if fechados else None,
            "sobre_causa_medio": round(statistics.mean(x["fechado"] / x["valor_causa"] for x in fechados if x["valor_causa"]), 4) if fechados else None,
            "referencia": {"ticket_medio": referencia["ticket_medio"], "sobre_causa_medio": referencia["sobre_causa_medio"], "acordos": referencia["n"]},
        },
        "aceitacao": {"respondidos": len(respondidos), "aceitos": sum(bool(x["aceito"]) for x in respondidos),
                      "taxa": _ratio(sum(bool(x["aceito"]) for x in respondidos), len(respondidos)), "premissa": P3.valor},
        "aderencia": {"decisoes": len(itens), "taxa": _ratio(sum(x["aderente"] for x in itens), len(itens))},
        "acordos": {"propostos": len(propostos), "fechados": len(fechados),
                    "em_negociacao": sum(1 for x in propostos if x["aceito"] is None and not x["encerrado"])},
        "defendidos": {
            "sentencas": len(defendidos),
            "exito": _ratio(sum(x["resultado_judicial"] == "EXITO" for x in defendidos), len(defendidos)),
            "condenacoes": round(sum(x["gasto"] or 0.0 for x in defendidos), 2),
            "custo_parecidos": round(sum(x["base_parecidos"] for x in defendidos_com_valor), 2),
            "condenacoes_comparaveis": round(sum(x["gasto"] for x in defendidos_com_valor), 2),
        },
        "serie_semanal": [{"semana": chave, "encerrados": s["encerrados"], "economia": round(s["economia"], 2)}
                          for chave, s in sorted(semanas.items())][-16:],
    }


def _advogados(itens: list[dict], media_banco: float | None) -> list[dict]:
    grupos: dict[str, list[dict]] = defaultdict(list)
    for x in itens:
        if x["lawyer_id"]:
            grupos[x["lawyer_id"]].append(x)
    linhas = [{"id": g[0]["lawyer_id"], "nome": g[0]["lawyer_name"] or "—", "escritorio": g[0]["law_firm_name"],
               "score": _score(g, media_banco)} for g in grupos.values()]
    return sorted(linhas, key=lambda r: (not r["score"]["amostra_suficiente"], -(r["score"]["nota"] or 0)))


def _escritorios(itens_banco: list[dict], todos: list[dict], bank_id: str, media_banco: float | None) -> list[dict]:
    outros = [x for x in todos if x["bank_id"] != bank_id]
    media_mercado = _score(outros, None)["nota_bruta"] if outros else None
    grupos: dict[str, list[dict]] = defaultdict(list)
    for x in itens_banco:
        if x["law_firm_id"]:
            grupos[x["law_firm_id"]].append(x)
    linhas = []
    for firm_id, grupo in grupos.items():
        score = _score(grupo, media_banco)
        fora = [x for x in outros if x["law_firm_id"] == firm_id]
        clientes = len({x["bank_id"] for x in fora})
        mercado, leitura = None, None
        if clientes >= MIN_OUTROS_CLIENTES and sum(x["encerrado"] for x in fora) >= MIN_ENCERRADOS_MERCADO:
            mercado = _score(fora, media_mercado)
            if score["nota"] is not None and mercado["nota"] is not None:
                diferenca = score["nota"] - mercado["nota"]
                leitura = ("Entrega menos com você do que no mercado: revise os documentos que você envia e o contrato com este escritório."
                           if diferenca < -5 else "Entrega mais com você do que no mercado." if diferenca > 5
                           else "Entrega com você o mesmo que no mercado.")
        linhas.append({
            "id": firm_id, "nome": grupo[0]["law_firm_name"], "advogados": len({x["lawyer_id"] for x in grupo}),
            "score": score, "mercado": mercado, "leitura": leitura,
            "motivo_sem_mercado": None if mercado else
            f"O mercado só aparece com ao menos {MIN_OUTROS_CLIENTES} outros clientes e {MIN_ENCERRADOS_MERCADO} processos encerrados fora desta empresa.",
        })
    return sorted(linhas, key=lambda r: -(r["score"]["nota"] or 0))


def _excecoes(itens: list[dict]) -> dict:
    lista = []
    for x in itens:
        base = {"case_id": x["case_id"], "case_number": x["case_number"], "advogado": x["lawyer_name"],
                "escritorio": x["law_firm_name"], "data": x["decidido_em"].isoformat() if x["decidido_em"] else None,
                "valor_causa": x["valor_causa"], "motivo": None}
        if x["fechado"] is not None and x["limite"] is not None and x["fechado"] > x["limite"] + 0.01:
            lista.append({**base, "tipo": "ACORDO_ACIMA_DO_LIMITE",
                          "detalhe": f"Fechou em {_brl(x['fechado'])}; acima de {_brl(x['limite'])} o acordo não compensa."})
        if not x["aderente"]:
            lista.append({**base, "tipo": "DECISAO_DIFERENTE", "motivo": MOTIVOS_DIVERGENCIA.get(x["motivo_divergencia"]),
                          "detalhe": f"Recomendação: {ACOES.get(x['recomendacao'], x['recomendacao'])}. Decisão: {ACOES.get(x['acao'], x['acao'])}."})
        if x["com_ressalva"] and x["documentos_abertos"] == 0:
            lista.append({**base, "tipo": "DECISAO_SEM_CONFERENCIA",
                          "detalhe": "O motor pediu conferência e a decisão foi registrada sem abrir nenhum documento."})
    ordem = {"ACORDO_ACIMA_DO_LIMITE": 0, "DECISAO_DIFERENTE": 1, "DECISAO_SEM_CONFERENCIA": 2}
    lista.sort(key=lambda e: (ordem[e["tipo"]], -e["valor_causa"]))
    contagem: dict[str, int] = defaultdict(int)
    for e in lista:
        contagem[e["tipo"]] += 1
    # Todas as linhas: cortar aqui escondia os tipos do fim da ordenação e o filtro da tela aparecia vazio.
    return {"total": len(lista), "por_tipo": dict(contagem), "itens": lista}


def valor_em_jogo(flags: dict[str, bool], documento: str, sub_assunto: str, uf: str, causa: float) -> float:
    """
    Economia ESTIMADA se o documento que falta chegar: (chance de perder sem ele − com ele) × condenação média
    × chance de a empresa encontrar o documento. É a única estimativa do painel, pedida de propósito: mostra
    quanto vale organizar a entrega de documentos, e aparece rotulada como estimativa.
    """
    if flags.get(documento, True):
        return 0.0
    com = {**flags, documento: True}
    delta = (table.p_perda(flags["contrato"], flags["extrato"], flags["comprovante"], sub_assunto, uf)
             - table.p_perda(com["contrato"], com["extrato"], com["comprovante"], sub_assunto, uf))
    return max(0.0, delta) * RATIO_CONDENACAO.valor * causa * P4.valor


CHAVE_DOC = {"CONTRATO": "contrato", "EXTRATO": "extrato", "COMPROVANTE_CREDITO": "comprovante"}


def _documentos(connection: sqlite3.Connection, bank_id: str) -> tuple[dict, list[dict]]:
    agora = datetime.now(UTC)
    ultimas = connection.execute("""
        SELECT c.id, c.uf, c.value_of_claim, c.sub_subject, a.feature_vector FROM cases c JOIN analyses a ON a.id = (
            SELECT id FROM analyses WHERE case_id = c.id ORDER BY created_at DESC LIMIT 1)
        WHERE c.bank_id = ?""", (bank_id,)).fetchall()
    carteira = {tipo: {"tipo": tipo, "nome": nome, "casos_sem": 0, "valor_em_jogo": 0.0} for tipo, nome in FEATURE_DOC.items()}
    casos: dict[str, tuple] = {}
    for row in ultimas:
        features = json.loads(row["feature_vector"])
        flags = {"contrato": bool(features.get("Contrato")), "extrato": bool(features.get("Extrato")),
                 "comprovante": bool(features.get("Comprovante de crédito"))}
        sub = "Golpe" if "golpe" in (row["sub_subject"] or "").lower() else "Generico"
        causa = float(row["value_of_claim"] or 0.0)
        casos[row["id"]] = (flags, sub, row["uf"], causa)
        for tipo, chave in CHAVE_DOC.items():
            if not flags[chave]:
                carteira[tipo]["casos_sem"] += 1
                carteira[tipo]["valor_em_jogo"] += valor_em_jogo(flags, chave, sub, row["uf"], causa)

    def jogo(case_id: str, tipo: str) -> float:
        if case_id not in casos or tipo not in CHAVE_DOC:
            return 0.0
        flags, sub, uf, causa = casos[case_id]
        return valor_em_jogo(flags, CHAVE_DOC[tipo], sub, uf, causa)

    pedidos = [dict(r) for r in connection.execute("""
        SELECT r.*, c.case_number, c.value_of_claim, u.name AS lawyer_name FROM document_requests r
        JOIN cases c ON c.id = r.case_id LEFT JOIN users u ON u.id = c.assigned_lawyer_id
        WHERE c.bank_id = ?""", (bank_id,))]
    fila = []
    for p in pedidos:
        if p["status"] != "REQUESTED":
            continue
        criado = _parse_date(p["created_at"])
        fila.append({"id": p["id"], "case_id": p["case_id"], "case_number": p["case_number"],
                     "documento": p["document_type"], "documento_nome": DOC_NOMES.get(p["document_type"], p["document_type"]),
                     "advogado": p["lawyer_name"], "dias_em_aberto": (agora - criado).days if criado else None,
                     "valor_causa": p["value_of_claim"], "valor_em_jogo": round(jogo(p["case_id"], p["document_type"]), 2),
                     "motivo_pedido": p["reason"]})
    fila.sort(key=lambda f: (-f["valor_em_jogo"], -(f["dias_em_aberto"] or 0)))

    respondidos = [p for p in pedidos if p["responded_at"]]
    dias_resposta = [(_parse_date(p["responded_at"]) - _parse_date(p["created_at"])).total_seconds() / 86400 for p in respondidos]
    motivos: dict[tuple[str, str], dict] = {}
    for p in pedidos:
        if p["status"] != "DECLARED_UNAVAILABLE":
            continue
        chave = (p["document_type"], p["unavailability_reason"] or "OUTRO")
        m = motivos.setdefault(chave, {"documento": chave[0], "motivo": chave[1], "casos": 0, "classificados_por_ia": 0, "valor_em_jogo": 0.0})
        m["casos"] += 1
        m["classificados_por_ia"] += p["unavailability_reason_source"] == "IA"
        m["valor_em_jogo"] += jogo(p["case_id"], p["document_type"])
    status = defaultdict(int)
    for p in pedidos:
        status[p["status"]] += 1
    documentos = {
        "base_historica": base_historica(),
        "carteira": {"casos_analisados": len(ultimas),
                     "por_documento": [{**v, "valor_em_jogo": round(v["valor_em_jogo"], 2)} for v in carteira.values()],
                     "valor_em_jogo_total": round(sum(v["valor_em_jogo"] for v in carteira.values()), 2)},
        "fila_recuperacao": fila[:50], "fila_total": len(fila),
        "fila_valor_em_jogo": round(sum(f["valor_em_jogo"] for f in fila), 2),
        "pedidos": {"total": len(pedidos), "por_status": dict(status),
                    "dias_para_responder_mediana": round(statistics.median(dias_resposta), 1) if dias_resposta else None,
                    "entregues": _ratio(status["SUBMITTED"], len(respondidos))},
        "motivos": sorted(({**m, "valor_em_jogo": round(m["valor_em_jogo"], 2), "motivo_nome": MOTIVOS.get(m["motivo"], m["motivo"]),
                            "documento_nome": DOC_NOMES.get(m["documento"], m["documento"])} for m in motivos.values()),
                          key=lambda m: -m["valor_em_jogo"]),
        "premissa_valor_em_jogo": (f"Estimativa: (chance de a empresa perder sem o documento − com ele) × condenação média "
                                   f"({_pct(RATIO_CONDENACAO.valor)} da causa) × chance de encontrar o documento ({P4.valor:.0%})."),
    }
    return documentos, list(motivos.values())


def _recomendacoes(motivos: list[dict]) -> list[dict]:
    cards = []
    for m in sorted(motivos, key=lambda item: -item["casos"]):
        area, acao, kpi = CATALOGO_DOC.get((m["documento"], m["motivo"])) or CATALOGO.get(m["motivo"], CATALOGO["OUTRO"])
        documento = DOC_NOMES.get(m["documento"], m["documento"])
        motivo = MOTIVOS.get(m["motivo"], m["motivo"])
        cards.append({
            "origem": "operacao", "documento": documento, "motivo": motivo, "area": area, "acao": acao, "indicador": kpi,
            "casos": m["casos"],
            "titulo": f"{documento} sem entrega: sinal de golpe" if m["motivo"] == "OPERACAO_INEXISTENTE" else f"{documento}: {motivo.lower()}",
            "evidencia": f"{m['casos']} pedido(s) declarados indisponíveis por este motivo.",
        })
    base = base_historica()
    if base:
        for d in base["documentos"]:
            if d["muda_resultado"]:
                cards.append({
                    "origem": "base_historica", "documento": d["nome"], "motivo": None, "area": "Jurídico interno + TI",
                    "casos": d["casos_sem"], "titulo": f"{d['nome']} falta em {_pct(d['ausente_pct'])} dos processos",
                    "acao": "Registrar o motivo de cada ausência no painel para descobrir a causa e a área dona do problema.",
                    "indicador": f"% de processos sem {d['nome'].lower()}",
                    "evidencia": (f"Na base, processos sem {d['nome'].lower()} custaram em média {_brl(d['custo_medio_sem'])}; "
                                  f"com ele, {_brl(d['custo_medio_com'])}. A derrota vai de {_pct(d['derrota_com'])} para {_pct(d['derrota_sem'])}."),
                })
            elif d["tipo"] == "DOSSIE":
                cards.append({
                    "origem": "base_historica", "documento": d["nome"], "motivo": None,
                    "area": "Suprimentos / gestão de fornecedores", "casos": d["casos_sem"],
                    "titulo": "Dossiê de terceiro não muda o resultado do processo",
                    "acao": "Renegociar o escopo com a empresa terceira: pedir o dossiê focado na assinatura quando falta o contrato, que é quando ele decide entre recuperar e fazer acordo.",
                    "indicador": "Custo de dossiê por processo decidido",
                    "evidencia": f"Derrota de {_pct(d['derrota_com'])} com dossiê e {_pct(d['derrota_sem'])} sem.",
                })
    operacao = [c for c in cards if c["origem"] == "operacao"]
    for i, card in enumerate(cards):
        card["prioridade"] = ("Alta" if card in operacao[:3] else "Média") if card["origem"] == "operacao" else \
            ("Estrutural" if "custaram" in card["evidencia"] else "Oportunidade")
    return cards


def build_bank_insights(connection: sqlite3.Connection, bank_id: str) -> dict:
    todos = _carregar_decisoes(connection)
    itens = [x for x in todos if x["bank_id"] == bank_id]
    media_banco = _score(itens, None)["nota_bruta"] if itens else None
    documentos, motivos = _documentos(connection, bank_id)
    simulados = connection.execute("SELECT COUNT(*) FROM cases WHERE bank_id = ? AND is_simulated = 1", (bank_id,)).fetchone()[0]
    total = connection.execute("SELECT COUNT(*) FROM cases WHERE bank_id = ?", (bank_id,)).fetchone()[0]
    return {
        "gerado_em": datetime.now(UTC).isoformat(),
        "casos": total, "casos_simulados": simulados,
        "efetividade": _efetividade(itens),
        "documentos": documentos,
        "recomendacoes": _recomendacoes(motivos),
        "escritorios": _escritorios(itens, todos, bank_id, media_banco),
        "advogados": _advogados(itens, media_banco),
        "excecoes": _excecoes(itens),
        "regras": {"min_encerrados_ranking": MIN_ENCERRADOS_RANKING, "min_outros_clientes": MIN_OUTROS_CLIENTES,
                   "min_encerrados_mercado": MIN_ENCERRADOS_MERCADO, "pesos": PESOS, "peso_da_media": PESO_DA_MEDIA},
    }
