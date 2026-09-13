"""
Ponto único de decisão da política de acordos: decidir(CaseFeatures).

    gate (a defesa é possível?) -> probabilidade (tabela ou fonte externa)
      -> preço (valor_acordo.avaliar_acordo) -> recuperar o documento compensa?

API, grafo do dossiê, backtest e prévia de contrato chamam esta função.
"""
from __future__ import annotations

from contracts.schema import CaseFeatures, ParametrosContrato, PlanoRecuperacao, Recomendacao, VereditoAcordo

from . import table
from .constants import CUSTO_MENSAL_TEMPO, DURACAO_MESES, P4, P5, POLICY_VERSION, RATIO_CONDENACAO
from .gate import avaliar_gate, contrato_efetivo
from .linguagem import descrever_caso, frequencia, nivel_de_risco
from .referencia import acordos as referencia_acordos, custo_parecidos, faixa_mercado, valor_recomendado
from .valor_acordo import avaliar_acordo, brl


def _p_tabela(c: CaseFeatures, *, com_contrato: bool | None = None,
              com_extrato: bool | None = None) -> float:
    return table.p_perda(
        contrato=contrato_efetivo(c) if com_contrato is None else com_contrato,
        extrato=c.extrato if com_extrato is None else com_extrato,
        comprovante=c.comprovante_credito,
        sub_assunto=c.sub_assunto,
        uf=c.uf,
    )


def _avaliar(valor_causa: float, p: float, contrato: ParametrosContrato) -> VereditoAcordo:
    condenacao = RATIO_CONDENACAO.valor * valor_causa
    return avaliar_acordo(
        valor_causa, p,
        fator_tempo=contrato.fator_tempo,
        honorario_perda=contrato.honorario_defesa_perdida.em_reais(valor_causa, condenacao),
        honorario_ganho=contrato.honorario_defesa_ganha.em_reais(valor_causa, condenacao),
        honorario_acordo=contrato.honorario_acordo.em_reais(valor_causa, condenacao),
        teto_alcada=contrato.teto_alcada_fator * valor_causa if contrato.teto_alcada_fator else None,
        concessao=contrato.concessao,
    )


def _custo_do_melhor_caminho(v: VereditoAcordo, valor_causa: float, contrato: ParametrosContrato) -> float:
    """Custo esperado da melhor opção disponível: defender, ou acordar na abertura."""
    if v.faixa is None:
        return v.custo_defesa
    condenacao = RATIO_CONDENACAO.valor * valor_causa
    return v.faixa.abertura + contrato.honorario_acordo.em_reais(valor_causa, condenacao)


def _plano_recuperacao(c: CaseFeatures, valor_causa: float, contrato: ParametrosContrato,
                       custo_atual: float) -> PlanoRecuperacao | None:
    """
    A TERCEIRA VIA — só quando o documento muda a melhor opção.

    Dossiê que periciou assinatura em contrato => o contrato existiu.
    Laudo que descreve liberação de crédito    => o extrato daquela conta existiu.

    O ganho compara a melhor opção HOJE com a melhor opção se o documento vier.
    Recuperar só o contrato num caso também sem extrato raramente compensa:
    a defesa continua mais cara que acordar, e o banco acordaria de qualquer jeito.
    """
    if not c.contrato and c.dossie:
        forte = bool(c.analise_dossie and c.analise_dossie.analisou_assinatura_contrato)
        doc, conf = "contrato", ("alta" if forte else "media")
        fund = ("O dossiê conferiu a assinatura do contrato: o contrato existe, só não foi enviado." if forte else
                "Há dossiê, mas não está claro se ele conferiu a assinatura do contrato.")
        p_novo = _p_tabela(c, com_contrato=True)
    elif not c.extrato and c.laudo:
        doc, conf = "extrato", "media"
        fund = "O laudo mostra o dinheiro caindo na conta do autor: o extrato dessa conta existe."
        p_novo = _p_tabela(c, com_extrato=True)
    elif not c.extrato:
        doc, conf, fund = "extrato", "baixa", "Falta o extrato, e nada indica que ele exista."
        p_novo = _p_tabela(c, com_extrato=True)
    elif not c.contrato:
        doc, conf, fund = "contrato", "baixa", "Falta o contrato, e nada indica que ele exista."
        p_novo = _p_tabela(c, com_contrato=True)
    else:
        return None

    custo_novo = _custo_do_melhor_caminho(_avaliar(valor_causa, p_novo, contrato), valor_causa, contrato)
    prob = P4.valor if conf == "alta" else P5.valor
    ganho = prob * (custo_atual - custo_novo)
    if ganho <= 0:
        return None
    return PlanoRecuperacao(documento=doc, confianca=conf, fundamento=fund,
                            ganho_estimado=round(ganho, 2), p_perda_se_recuperado=round(p_novo, 4))


def decidir(c: CaseFeatures, contrato: ParametrosContrato | None = None, *,
            p_perda: float | None = None, fator_aceite: float = 1.0) -> Recomendacao:
    """
    Recomendação para um caso.

    `contrato` traz os termos do contrato vigente banco–escritório (honorários
    por desfecho, alçada, custo do tempo); sem ele valem os defaults.
    `p_perda` substitui a tabela de segmentos por uma fonte externa (um modelo),
    mantendo gate, preço e terceira via.
    """
    contrato = contrato or ParametrosContrato()
    gate = avaliar_gate(c)
    externa = p_perda is not None
    p = p_perda if externa else _p_tabela(c)
    alertas = [gate.alerta] if gate.alerta else []

    valor_informado = c.valor_causa > 0
    valor_causa = c.valor_causa if valor_informado else 1.0
    if not valor_informado:
        alertas.append("Sem o valor da causa não dá para sugerir quanto oferecer: a recomendação foi calculada em proporção.")

    veredito = _avaliar(valor_causa, p, contrato)
    rec = _plano_recuperacao(c, valor_causa, contrato, _custo_do_melhor_caminho(veredito, valor_causa, contrato))

    segmento = table.chave(contrato_efetivo(c), c.extrato, c.comprovante_credito, c.sub_assunto)
    caso = descrever_caso(contrato_efetivo(c), c.extrato, c.comprovante_credito, c.sub_assunto)
    fonte = " (estimativa de um modelo externo)" if externa else ""
    just = [gate.motivo,
            f"Em casos parecidos ({caso}), a chance de a empresa perder é {nivel_de_risco(p)}: "
            f"{frequencia(p)}{fonte}. O acordo compensa a partir de {frequencia(veredito.p_estrela)}."]
    premissas = [*veredito.premissas_usadas, CUSTO_MENSAL_TEMPO.id, DURACAO_MESES.id]

    # Valor recomendado, faixa de mercado e argumentos: o que o advogado leva para a mesa.
    parecidos = (custo_parecidos(contrato_efetivo(c), c.extrato, c.comprovante_credito, c.sub_assunto, c.uf, valor_causa)
                 if valor_informado else None)
    oferta = chance = mercado = None
    if veredito.faixa is not None and valor_informado:
        resultado = valor_recomendado(valor_causa, veredito.faixa.walk_away, fator_aceite)
        if resultado:
            oferta, chance = resultado
            mercado = faixa_mercado(valor_causa)
    argumentos = [f"Em casos parecidos, a empresa perde {frequencia(p)}."]
    if oferta is not None:
        base = referencia_acordos()
        argumentos.append(f"Acordos assim fecham entre {round(base['p25'] * 100)}% e {round(base['p75'] * 100)}% da causa "
                          f"(R$ {brl(mercado[0])} a R$ {brl(mercado[1])}).")
        argumentos.append(f"Oferecendo R$ {brl(oferta)}, a chance estimada de aceite é de {round(chance * 100)}%.")
        if parecidos and parecidos["valor"] > oferta:
            argumentos.append(f"Se aceito, economiza R$ {brl(parecidos['valor'] - oferta)} sobre o custo médio de "
                              f"processos parecidos (R$ {brl(parecidos['valor'])}).")
        elif parecidos:
            argumentos.append(f"Processos parecidos custaram em média R$ {brl(parecidos['valor'])}.")
        argumentos.append(f"Acima de R$ {brl(veredito.faixa.walk_away)}, acordo não compensa: defender sai mais barato.")
    elif parecidos:
        argumentos.append(f"Processos parecidos custaram em média R$ {brl(parecidos['valor'])}.")

    if rec and rec.confianca == "alta":
        acao = "RECUPERAR"
        just.append(f"{rec.fundamento} Se ele chegar, a economia esperada é de R$ {brl(rec.ganho_estimado)} "
                    "em relação ao melhor caminho de hoje.")
        just.append(f"Se o documento não vier: {veredito.motivo}")
        premissas.append(P4.id)
    elif veredito.decisao == "ACORDO":
        acao = "ACORDAR"
        just.append(veredito.motivo if oferta is None else
                    f"Ofereça R$ {brl(oferta)} (chance estimada de aceite de {round(chance * 100)}%). "
                    f"Defender custaria R$ {brl(veredito.custo_defesa)}, em média. "
                    f"Acima de R$ {brl(veredito.faixa.walk_away)}, acordo não compensa: defender sai mais barato.")
    else:
        acao = "DEFENDER"
        just.append(veredito.motivo)
        if not gate.defesa_disponivel:
            alertas.append("Defender aqui vai contra a prova disponível: se escolher defesa, registre o motivo.")
    if rec and rec.confianca != "alta":
        premissas.append(P5.id)

    just.extend(c.contradicoes)

    return Recomendacao(
        numero_processo=c.numero_processo, acao=acao,
        gate_defesa_disponivel=gate.defesa_disponivel, gate_motivo=gate.motivo,
        segmento=segmento, p_perda=round(p, 4), fonte_probabilidade="externa" if externa else "tabela",
        p_estrela=veredito.p_estrela, custo_esperado_defesa=veredito.custo_defesa,
        acordo=veredito.faixa if valor_informado else None,
        economia_no_alvo=veredito.economia_no_alvo if valor_informado else 0.0,
        recuperacao=rec,
        valor_recomendado=oferta, chance_aceite=chance, faixa_mercado=list(mercado) if mercado else None,
        custo_parecidos=parecidos["valor"] if parecidos else None, parecidos_n=parecidos["n"] if parecidos else None,
        argumentos=argumentos,
        justificativa=just, alertas=alertas, premissas_usadas=list(dict.fromkeys(premissas)),
        versao_politica=f"{POLICY_VERSION}+{table._ARTEFATO['versao']}",
        versao_contrato=contrato.versao,
    )
