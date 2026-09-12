"""
Painel do banco: o que a política entregou, onde o banco perde dinheiro e quem executa bem.

Toda métrica de pessoa ou escritório é relativa ao que a política esperava para AQUELES casos
(índice = economia realizada ÷ economia esperada). Taxa de vitória crua não entra: ela mede a
carteira que o escritório recebeu, não o trabalho dele.
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
from src.policy.learning import PosteriorAceitacao

ARTEFATO_BASE = Path(__file__).resolve().parents[3] / "artefatos" / "insights_base_historica.json"

MIN_DECISOES_RANKING = 20       # abaixo disso o advogado aparece com "amostra insuficiente"
MIN_OUTROS_CLIENTES = 2         # benchmark anônimo: o escritório precisa atender outros 2 clientes...
MIN_DECISOES_MERCADO = 50       # ...e somar 50 decisões fora deste banco
LIMIAR_DIVERGENCIA = 1000.0     # divergência com custo esperado acima disso vira exceção
FEATURE_DOC = {"CONTRATO": ("Contrato", "contrato"), "EXTRATO": ("Extrato", "extrato"),
               "COMPROVANTE_CREDITO": ("Comprovante de crédito", "comprovante")}
DOC_NOMES = {"CONTRATO": "Contrato", "EXTRATO": "Extrato", "COMPROVANTE_CREDITO": "Comprovante de crédito",
             "DOSSIE": "Dossiê", "DEMONSTRATIVO_DIVIDA": "Demonstrativo da dívida",
             "LAUDO_REFERENCIADO": "Laudo referenciado", "AUTOS": "Autos", "OUTRO": "Outro"}
MOTIVOS = {
    "NAO_LOCALIZADO": "Não localizado",
    "CONTRATO_FISICO_NAO_DIGITALIZADO": "Contrato físico não digitalizado",
    "CORRESPONDENTE_NAO_ENVIOU": "Correspondente não enviou",
    "FORA_DO_PRAZO_DE_GUARDA": "Fora do prazo de guarda",
    "SISTEMA_SEM_EXPORTACAO": "Sistema sem exportação",
    "OPERACAO_INEXISTENTE": "Operação não existe (golpe)",
    "OUTRO": "Outro",
}
# Motivo -> (área responsável, ação, indicador de sucesso). Ajustes por documento em CATALOGO_DOC.
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
        "Criar um índice único de documentos por operação (número, CPF, data) ligando originação, core bancário e jurídico.",
        "Tempo médio para localizar um documento"),
    "FORA_DO_PRAZO_DE_GUARDA": (
        "Jurídico + Compliance",
        "Revisar a tabela de temporalidade: guardar contrato e extrato enquanto couber ação judicial, não só pelo prazo regulatório mínimo.",
        "Pedidos negados por prazo de guarda"),
    "SISTEMA_SEM_EXPORTACAO": (
        "TI do core bancário",
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


def _mediana(valores: list[float]) -> float | None:
    return round(statistics.median(valores), 2) if valores else None


def valor_em_jogo(flags: dict[str, bool], documento: str, sub_assunto: str, uf: str, causa: float) -> float:
    """Ganho esperado ao recuperar um documento crítico que falta (mesma conta do artefato da base)."""
    if flags.get(documento, True):
        return 0.0
    com = {**flags, documento: True}
    delta = (table.p_perda(flags["contrato"], flags["extrato"], flags["comprovante"], sub_assunto, uf)
             - table.p_perda(com["contrato"], com["extrato"], com["comprovante"], sub_assunto, uf))
    return max(0.0, delta) * RATIO_CONDENACAO.valor * causa * P4.valor


def _flags(feature_vector: dict) -> dict[str, bool]:
    return {"contrato": bool(feature_vector.get("Contrato")), "extrato": bool(feature_vector.get("Extrato")),
            "comprovante": bool(feature_vector.get("Comprovante de crédito"))}


# ─────────────────────────────────────────────────────────────────────────────
# Carga: uma linha por processo com a última decisão, desfechos e engajamento.
# ─────────────────────────────────────────────────────────────────────────────

def _carregar_decisoes(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute("""
        SELECT d.id AS decision_id, d.case_id, d.action, d.proposed_value, d.created_at AS decided_at,
               COALESCE(d.lawyer_id, c.assigned_lawyer_id) AS lawyer_id,
               a.recommendation, a.policy_output, a.limitations, a.feature_vector,
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
        ultima[row["case_id"]] = dict(row)  # ordenado por data: a última sobrescreve

    negociacoes: dict[str, dict] = {}
    for row in connection.execute("SELECT * FROM negotiation_outcomes ORDER BY created_at"):
        negociacoes[row["decision_id"]] = dict(row)
    judiciais: dict[str, dict] = {}
    for row in connection.execute("SELECT * FROM judicial_outcomes ORDER BY created_at"):
        judiciais[row["case_id"]] = dict(row)
    engajamento: dict[str, dict] = defaultdict(lambda: {"segundos": 0, "documentos": set(), "aberto_em": None})
    for row in connection.execute(
            "SELECT case_id, event_type, document_id, active_seconds, created_at FROM engagement_events"):
        e = engajamento[row["case_id"]]
        if row["event_type"] == "ACTIVE_TIME":
            e["segundos"] += int(row["active_seconds"] or 0)
        elif row["event_type"] == "DOCUMENT_OPENED" and row["document_id"]:
            e["documentos"].add(row["document_id"])
        elif row["event_type"] == "CASE_OPENED":
            aberto = _parse_date(row["created_at"])
            if e["aberto_em"] is None or aberto < e["aberto_em"]:
                e["aberto_em"] = aberto

    return [_avaliar(d, negociacoes.get(d["decision_id"]), judiciais.get(d["case_id"]),
                     engajamento.get(d["case_id"])) for d in ultima.values()]


def _economia_com_valor(po: dict, valor: float) -> float:
    """Economia de fechar em `valor`: custo esperado da defesa − valor − honorário de acordo.

    O motor devolve economia_no_alvo = custo_defesa − (alvo + honorário), então
    economia(valor) = economia_no_alvo + alvo − valor, sem precisar do honorário explícito.
    """
    acordo = po.get("acordo")
    if acordo:
        return float(po.get("economia_no_alvo") or 0.0) + float(acordo["alvo"]) - valor
    return float(po.get("custo_esperado_defesa") or 0.0) - valor


def _esperado(po: dict, acao: str, valor_causa: float, proposto: float | None) -> float:
    """Economia esperada ex-ante de uma ação, frente a defender (linha de base = 0)."""
    if acao == "ACORDO":
        acordo = po.get("acordo") or {}
        valor = proposto if proposto is not None else acordo.get("alvo", valor_causa * 0.29)
        return P3.valor * _economia_com_valor(po, float(valor))
    if acao == "RECUPERAR":
        return float((po.get("recuperacao") or {}).get("ganho_estimado") or 0.0)
    return 0.0


def _avaliar(d: dict, negociacao: dict | None, judicial: dict | None, engajamento: dict | None) -> dict:
    po = json.loads(d["policy_output"]) if d["policy_output"] else {}
    limitations = json.loads(d["limitations"]) if d["limitations"] else []
    acordo = po.get("acordo") or {}
    causa = float(d["value_of_claim"] or 0.0)
    rec, acao = d["recommendation"], d["action"]
    esperado_rec = _esperado(po, rec, causa, None)
    esperado_acao = _esperado(po, acao, causa, d["proposed_value"])

    maturada, realizada, fechado = False, 0.0, None
    if acao == "DEFESA":
        maturada = True
    elif acao == "ACORDO" and negociacao and negociacao["status"] in {"ACEITO", "RECUSADO", "SEM_RESPOSTA"}:
        maturada = True
        if negociacao["status"] == "ACEITO":
            fechado = float(negociacao["closed_value"])
            realizada = _economia_com_valor(po, fechado)
    comparavel = maturada and rec in {"ACORDO", "DEFESA"} and acao in {"ACORDO", "DEFESA"}

    decidido = _parse_date(d["decided_at"])
    eng = engajamento or {"segundos": 0, "documentos": set(), "aberto_em": None}
    return {
        **{k: d[k] for k in ("case_id", "case_number", "bank_id", "lawyer_id", "lawyer_name", "law_firm_id",
                             "law_firm_name", "uf")},
        "recomendacao": rec, "acao": acao, "aderente": rec == acao, "decidido_em": decidido,
        "segmento": po.get("segmento") or "—", "valor_causa": causa,
        "p_perda": float(po.get("p_perda") or 0.0),
        "custo_defesa": float(po.get("custo_esperado_defesa") or 0.0),
        "alvo": acordo.get("alvo"), "walk_away": acordo.get("walk_away"), "proposto": d["proposed_value"],
        # Só divergência conta aqui; seguir a política pagando acima do alvo aparece em "acima_do_alvo".
        "custo_divergencia": 0.0 if rec == acao else max(0.0, esperado_rec - esperado_acao),
        "comparavel": comparavel, "esperada": esperado_rec if comparavel else 0.0,
        "realizada": realizada if comparavel else 0.0,
        "negociacao": negociacao["status"] if negociacao else None, "fechado": fechado,
        "acima_do_alvo": max(0.0, fechado - float(acordo["alvo"])) if fechado is not None and acordo else 0.0,
        "acima_walk_away": bool(fechado is not None and acordo and fechado > float(acordo["walk_away"]) + 0.01),
        "judicial": judicial,
        "com_ressalva": bool(limitations),
        "segundos_ativos": eng["segundos"], "documentos_abertos": len(eng["documentos"]),
        "horas_ate_decisao": ((decidido - eng["aberto_em"]).total_seconds() / 3600
                              if eng["aberto_em"] and decidido and decidido >= eng["aberto_em"] else None),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Agregações
# ─────────────────────────────────────────────────────────────────────────────

def _resumo(itens: list[dict]) -> dict:
    """Métricas ajustadas ao risco de um grupo de decisões (banco, escritório ou advogado)."""
    propostos = [x for x in itens if x["acao"] == "ACORDO"]
    respondidos = [x for x in propostos if x["negociacao"] in {"ACEITO", "RECUSADO", "SEM_RESPOSTA"}]
    aceitos = [x for x in respondidos if x["negociacao"] == "ACEITO"]
    posterior = PosteriorAceitacao(aceitos=len(aceitos), recusados=len(respondidos) - len(aceitos))
    esperada = sum(x["esperada"] for x in itens)
    realizada = sum(x["realizada"] for x in itens)
    ativos = [x["segundos_ativos"] / 60 for x in itens if x["segundos_ativos"]]
    return {
        "decisoes": len(itens),
        "aderencia": _ratio(sum(x["aderente"] for x in itens), len(itens)),
        "economia_esperada": round(esperada, 2),
        "economia_realizada": round(realizada, 2),
        "indice": _ratio(realizada, esperada) if esperada > 0 else None,
        "custo_divergencias": round(sum(x["custo_divergencia"] for x in itens), 2),
        "acordos_propostos": len(propostos),
        "acordos_fechados": len(aceitos),
        "negociacoes_pendentes": len(propostos) - len(respondidos),
        "aceitacao": _ratio(len(aceitos), len(respondidos)),
        "aceitacao_posterior": round(posterior.media, 4),
        "aceitacao_intervalo": [round(v, 4) for v in posterior.intervalo()],
        "pago_acima_do_alvo": round(sum(x["acima_do_alvo"] for x in itens), 2),
        "fechados_acima_walk_away": sum(x["acima_walk_away"] for x in itens),
        "tempo_ativo_mediano_min": _mediana(ativos),
        "decisoes_sem_abrir_documento": _ratio(sum(x["documentos_abertos"] == 0 for x in itens), len(itens)),
    }


def _efetividade(itens: list[dict]) -> dict:
    resumo = _resumo(itens)
    defendidos = [x for x in itens if x["judicial"]]
    condenacao_real = sum(float(x["judicial"]["condemnation_value"]) for x in defendidos)
    condenacao_esperada = sum(x["p_perda"] * RATIO_CONDENACAO.valor * x["valor_causa"] for x in defendidos)
    fechados = [x for x in itens if x["fechado"] is not None]
    semanas: dict[str, dict] = defaultdict(lambda: {"decisoes": 0, "aderentes": 0, "realizada": 0.0, "esperada": 0.0})
    for x in itens:
        if x["decidido_em"] is None:
            continue
        ano, semana, _ = x["decidido_em"].isocalendar()
        s = semanas[f"{ano}-S{semana:02d}"]
        s["decisoes"] += 1
        s["aderentes"] += x["aderente"]
        s["realizada"] += x["realizada"]
        s["esperada"] += x["esperada"]
    return {
        **resumo,
        "aceitacao_premissa": P3.valor,
        "valor_fechado_sobre_causa": _ratio(sum(x["fechado"] for x in fechados),
                                            sum(x["valor_causa"] for x in fechados)),
        "desfechos_judiciais": {
            "casos": len(defendidos),
            "exito": _ratio(sum(x["judicial"]["result"] == "EXITO" for x in defendidos), len(defendidos)),
            "condenacao_realizada": round(condenacao_real, 2),
            "condenacao_esperada": round(condenacao_esperada, 2),
            "aguardando_desfecho": sum(1 for x in itens if x["acao"] == "DEFESA" and not x["judicial"]),
        },
        "serie_semanal": [
            {"semana": chave, "decisoes": s["decisoes"], "aderencia": _ratio(s["aderentes"], s["decisoes"]),
             "economia_realizada": round(s["realizada"], 2), "economia_esperada": round(s["esperada"], 2)}
            for chave, s in sorted(semanas.items())][-16:],
    }


def _advogados(itens: list[dict]) -> list[dict]:
    grupos: dict[str, list[dict]] = defaultdict(list)
    for x in itens:
        if x["lawyer_id"]:
            grupos[x["lawyer_id"]].append(x)
    linhas = []
    for grupo in grupos.values():
        resumo = _resumo(grupo)
        linhas.append({"id": grupo[0]["lawyer_id"], "nome": grupo[0]["lawyer_name"] or "—",
                       "escritorio": grupo[0]["law_firm_name"], **resumo,
                       "amostra_suficiente": resumo["decisoes"] >= MIN_DECISOES_RANKING})
    return sorted(linhas, key=lambda r: (not r["amostra_suficiente"], -(r["indice"] if r["indice"] is not None else -9)))


def _escritorios(itens_banco: list[dict], todos: list[dict], bank_id: str) -> list[dict]:
    grupos: dict[str, list[dict]] = defaultdict(list)
    for x in itens_banco:
        if x["law_firm_id"]:
            grupos[x["law_firm_id"]].append(x)
    linhas = []
    for firm_id, grupo in grupos.items():
        resumo = _resumo(grupo)
        fora = [x for x in todos if x["law_firm_id"] == firm_id and x["bank_id"] != bank_id]
        outros_clientes = len({x["bank_id"] for x in fora})
        mercado, leitura = None, None
        if outros_clientes >= MIN_OUTROS_CLIENTES and len(fora) >= MIN_DECISOES_MERCADO:
            m = _resumo(fora)
            mercado = {k: m[k] for k in ("indice", "aderencia", "aceitacao", "decisoes")}
            if resumo["indice"] is not None and m["indice"] is not None:
                gap = resumo["indice"] - m["indice"]
                leitura = ("Entrega menos com você do que no mercado: revise os documentos que você envia e o contrato com este escritório."
                           if gap < -0.1 else "Entrega mais com você do que no mercado." if gap > 0.1
                           else "Entrega com você o mesmo que no mercado.")
        linhas.append({
            "id": firm_id, "nome": grupo[0]["law_firm_name"],
            "advogados": len({x["lawyer_id"] for x in grupo}), **resumo,
            "mercado": mercado, "leitura": leitura,
            "motivo_sem_mercado": None if mercado else
            f"Benchmark anônimo exige ao menos {MIN_OUTROS_CLIENTES} outros clientes e {MIN_DECISOES_MERCADO} decisões fora deste banco.",
        })
    return sorted(linhas, key=lambda r: -(r["indice"] if r["indice"] is not None else -9))


def _engajamento(itens: list[dict]) -> dict:
    por_segmento: dict[str, list[dict]] = defaultdict(list)
    for x in itens:
        por_segmento[x["segmento"]].append(x)
    segmentos = []
    for segmento, grupo in por_segmento.items():
        ativos = [x["segundos_ativos"] / 60 for x in grupo if x["segundos_ativos"]]
        segmentos.append({"segmento": segmento, "casos": len(grupo), "tempo_ativo_mediano_min": _mediana(ativos),
                          "com_ressalva": _ratio(sum(x["com_ressalva"] for x in grupo), len(grupo)),
                          "aderencia": _ratio(sum(x["aderente"] for x in grupo), len(grupo))})
    segmentos.sort(key=lambda s: -(s["tempo_ativo_mediano_min"] or 0))
    tempo = lambda grupo: _mediana([x["segundos_ativos"] / 60 for x in grupo if x["segundos_ativos"]])
    return {
        "casos": len(itens),
        "tempo_ativo_mediano_min": tempo(itens),
        "tempo_com_ressalva_min": tempo([x for x in itens if x["com_ressalva"]]),
        "tempo_sem_ressalva_min": tempo([x for x in itens if not x["com_ressalva"]]),
        "documentos_abertos_medio": round(statistics.mean([x["documentos_abertos"] for x in itens]), 2) if itens else None,
        "horas_ate_decisao_mediana": _mediana([x["horas_ate_decisao"] for x in itens if x["horas_ate_decisao"] is not None]),
        "decisoes_sem_abrir_documento": _ratio(sum(x["documentos_abertos"] == 0 for x in itens), len(itens)),
        "por_segmento": segmentos[:12],
    }


def _excecoes(itens: list[dict]) -> dict:
    lista = []
    for x in itens:
        base = {"case_id": x["case_id"], "case_number": x["case_number"], "advogado": x["lawyer_name"],
                "escritorio": x["law_firm_name"], "data": x["decidido_em"].isoformat() if x["decidido_em"] else None}
        if x["acima_walk_away"]:
            lista.append({**base, "tipo": "ACORDO_ACIMA_WALK_AWAY", "impacto": round(x["fechado"] - float(x["walk_away"]), 2),
                          "detalhe": f"Fechou em R$ {x['fechado']:,.2f}; walk-away era R$ {float(x['walk_away']):,.2f}."})
        if x["custo_divergencia"] >= LIMIAR_DIVERGENCIA:
            lista.append({**base, "tipo": "DIVERGENCIA_CARA", "impacto": round(x["custo_divergencia"], 2),
                          "detalhe": f"Política recomendou {x['recomendacao']}; advogado escolheu {x['acao']}."})
        if x["com_ressalva"] and x["documentos_abertos"] == 0:
            lista.append({**base, "tipo": "DECISAO_SEM_CONFERENCIA", "impacto": round(x["custo_defesa"], 2),
                          "detalhe": "O motor pediu conferência e a decisão foi registrada sem abrir nenhum documento."})
    lista.sort(key=lambda e: -(e["impacto"] or 0))
    contagem: dict[str, int] = defaultdict(int)
    for e in lista:
        contagem[e["tipo"]] += 1
    return {"total": len(lista), "por_tipo": dict(contagem), "itens": lista[:60],
            "limiar_divergencia": LIMIAR_DIVERGENCIA}


def _documentos(connection: sqlite3.Connection, bank_id: str) -> tuple[dict, list[dict]]:
    agora = datetime.now(UTC)
    ultimas = connection.execute("""
        SELECT c.id, c.case_number, c.uf, c.value_of_claim, c.sub_subject, a.feature_vector
        FROM cases c JOIN analyses a ON a.id = (
            SELECT id FROM analyses WHERE case_id = c.id ORDER BY created_at DESC LIMIT 1)
        WHERE c.bank_id = ?""", (bank_id,)).fetchall()
    casos = {}
    carteira = {tipo: {"tipo": tipo, "nome": nome, "casos_sem": 0, "valor_em_jogo": 0.0}
                for tipo, (nome, _) in FEATURE_DOC.items()}
    for row in ultimas:
        flags = _flags(json.loads(row["feature_vector"]))
        sub = "Golpe" if "golpe" in (row["sub_subject"] or "").lower() else "Generico"
        causa = float(row["value_of_claim"] or 0.0)
        casos[row["id"]] = (flags, sub, row["uf"], causa)
        for tipo, (_, chave) in FEATURE_DOC.items():
            if not flags[chave]:
                carteira[tipo]["casos_sem"] += 1
                carteira[tipo]["valor_em_jogo"] += valor_em_jogo(flags, chave, sub, row["uf"], causa)

    def jogo(case_id: str, tipo: str) -> float:
        if case_id not in casos or tipo not in FEATURE_DOC:
            return 0.0
        flags, sub, uf, causa = casos[case_id]
        return valor_em_jogo(flags, FEATURE_DOC[tipo][1], sub, uf, causa)

    pedidos = [dict(r) for r in connection.execute("""
        SELECT r.*, c.case_number, u.name AS lawyer_name FROM document_requests r
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
                     "valor_em_jogo": round(jogo(p["case_id"], p["document_type"]), 2), "motivo_pedido": p["reason"]})
    fila.sort(key=lambda f: -f["valor_em_jogo"])

    respondidos = [p for p in pedidos if p["responded_at"]]
    dias_resposta = [(_parse_date(p["responded_at"]) - _parse_date(p["created_at"])).total_seconds() / 86400
                     for p in respondidos]
    motivos: dict[tuple[str, str], dict] = {}
    for p in pedidos:
        if p["status"] != "DECLARED_UNAVAILABLE":
            continue
        chave = (p["document_type"], p["unavailability_reason"] or "OUTRO")
        m = motivos.setdefault(chave, {"documento": chave[0], "motivo": chave[1], "casos": 0, "valor_em_jogo": 0.0,
                                       "classificados_por_ia": 0})
        m["casos"] += 1
        m["valor_em_jogo"] += jogo(p["case_id"], p["document_type"])
        m["classificados_por_ia"] += p["unavailability_reason_source"] == "IA"

    status = defaultdict(int)
    for p in pedidos:
        status[p["status"]] += 1
    documentos = {
        "base_historica": base_historica(),
        "carteira": {"casos_analisados": len(casos),
                     "por_documento": [{**v, "valor_em_jogo": round(v["valor_em_jogo"], 2)} for v in carteira.values()],
                     "valor_em_jogo_total": round(sum(v["valor_em_jogo"] for v in carteira.values()), 2)},
        "fila_recuperacao": fila[:50],
        "fila_total": len(fila),
        "fila_valor_em_jogo": round(sum(f["valor_em_jogo"] for f in fila), 2),
        "pedidos": {"total": len(pedidos), "por_status": dict(status),
                    "dias_para_responder_mediana": _mediana(dias_resposta),
                    "entregues": _ratio(status["SUBMITTED"], len(respondidos))},
        "motivos": sorted(({**m, "motivo_nome": MOTIVOS.get(m["motivo"], m["motivo"]),
                            "documento_nome": DOC_NOMES.get(m["documento"], m["documento"]),
                            "valor_em_jogo": round(m["valor_em_jogo"], 2)} for m in motivos.values()),
                          key=lambda m: -m["valor_em_jogo"]),
        "premissas": (f"Valor em jogo por caso = (P(derrota) sem o documento − com ele) × condenação média "
                      f"({RATIO_CONDENACAO.valor:.2%} da causa) × chance de recuperar ({P4.valor:.0%})."),
    }
    return documentos, list(motivos.values())


def _recomendacoes(motivos: list[dict]) -> list[dict]:
    """Uma recomendação por (documento, motivo), com área responsável e valor em jogo. Mais a leitura da base."""
    cards = []
    for m in motivos:
        area, acao, kpi = CATALOGO_DOC.get((m["documento"], m["motivo"])) or CATALOGO.get(m["motivo"], CATALOGO["OUTRO"])
        cards.append({
            "origem": "operacao", "documento": DOC_NOMES.get(m["documento"], m["documento"]),
            "motivo": MOTIVOS.get(m["motivo"], m["motivo"]), "area": area, "acao": acao, "indicador": kpi,
            "casos": m["casos"], "valor_em_jogo": round(m["valor_em_jogo"], 2),
            "titulo": (f"{DOC_NOMES.get(m['documento'], m['documento'])} sem entrega: sinal de golpe"
                       if m["motivo"] == "OPERACAO_INEXISTENTE" else
                       f"{DOC_NOMES.get(m['documento'], m['documento'])}: {MOTIVOS.get(m['motivo'], m['motivo']).lower()}"),
            "evidencia": f"{m['casos']} pedido(s) declarados indisponíveis por este motivo.",
        })
    base = base_historica()
    if base:
        for d in base["documentos"]:
            if d["valor_em_jogo"]:
                cards.append({
                    "origem": "base_historica", "documento": d["nome"], "motivo": None,
                    "area": "Jurídico interno + TI", "casos": d["casos_sem"], "valor_em_jogo": d["valor_em_jogo"],
                    "titulo": f"{d['nome']} falta em {d['ausente_pct']:.1%} dos processos",
                    "acao": "Registrar o motivo de cada ausência no painel para descobrir a causa e a área dona do problema.",
                    "indicador": f"% de processos sem {d['nome'].lower()}",
                    "evidencia": (f"Na base de {base['casos']:,} sentenças, a derrota vai de {d['derrota_com']:.1%} com o documento "
                                  f"para {d['derrota_sem']:.1%} sem ele.").replace(",", "."),
                })
            elif not d["muda_resultado"] and d["tipo"] == "DOSSIE":
                cards.append({
                    "origem": "base_historica", "documento": d["nome"], "motivo": None,
                    "area": "Suprimentos / gestão de fornecedores", "casos": d["casos_sem"], "valor_em_jogo": 0.0,
                    "titulo": "Dossiê de terceiro não muda o resultado do processo",
                    "acao": "Renegociar o escopo com a empresa terceira: pedir o dossiê focado na assinatura quando falta o contrato, que é quando ele decide entre recuperar e fazer acordo.",
                    "indicador": "Custo de dossiê por processo decidido",
                    "evidencia": f"Derrota de {d['derrota_com']:.1%} com dossiê e {d['derrota_sem']:.1%} sem.",
                })
    cards.sort(key=lambda c: (c["origem"] != "operacao", -c["valor_em_jogo"]))
    for i, card in enumerate(cards):
        if card["origem"] == "base_historica":
            card["prioridade"] = "Estrutural" if card["valor_em_jogo"] else "Oportunidade"
        else:
            card["prioridade"] = "Alta" if i < 3 else "Média"
    return cards


def build_bank_insights(connection: sqlite3.Connection, bank_id: str) -> dict:
    todos = _carregar_decisoes(connection)
    itens = [x for x in todos if x["bank_id"] == bank_id]
    documentos, motivos = _documentos(connection, bank_id)
    simulados = connection.execute(
        "SELECT COUNT(*) FROM cases WHERE bank_id = ? AND is_simulated = 1", (bank_id,)).fetchone()[0]
    total = connection.execute("SELECT COUNT(*) FROM cases WHERE bank_id = ?", (bank_id,)).fetchone()[0]
    return {
        "gerado_em": datetime.now(UTC).isoformat(),
        "casos": total,
        "casos_simulados": simulados,
        "efetividade": _efetividade(itens),
        "documentos": documentos,
        "recomendacoes": _recomendacoes(motivos),
        "escritorios": _escritorios(itens, todos, bank_id),
        "advogados": _advogados(itens),
        "engajamento": _engajamento(itens),
        "excecoes": _excecoes(itens),
        "regras": {"min_decisoes_ranking": MIN_DECISOES_RANKING, "min_outros_clientes": MIN_OUTROS_CLIENTES,
                   "min_decisoes_mercado": MIN_DECISOES_MERCADO},
    }
