"""
Composição das 3 camadas. ESTE é o único ponto de decisão do sistema.

    gate (elegibilidade) -> probabilidade (tabela) -> valor esperado

Nenhum outro módulo decide nada. Se aparecer uma segunda implementação da
política em qualquer lugar do repositório, é bug.
"""
from __future__ import annotations

from contracts.schema import CaseFeatures, PlanoRecuperacao, Recomendacao
from src.policy import table
from src.policy.constants import P1, P3, P4, P5, P6
from src.policy.gate import avaliar_gate, contrato_efetivo
from src.policy.pricing import calcular_faixa


def custo_esperado_defesa(valor_causa: float, p_perda: float) -> float:
    """P(derrota) x quanto se paga ao perder (P1) x valor da causa, + sucumbência (P6)."""
    return p_perda * P1.valor * valor_causa * (1 + P6.valor)


def _p_perda(c: CaseFeatures, *, com_contrato: bool | None = None,
             com_extrato: bool | None = None) -> float:
    return table.p_perda(
        contrato=contrato_efetivo(c) if com_contrato is None else com_contrato,
        extrato=c.extrato if com_extrato is None else com_extrato,
        comprovante=c.comprovante_credito,
        sub_assunto=c.sub_assunto,
        uf=c.uf,
    )


def _plano_recuperacao(c: CaseFeatures, p_atual: float) -> PlanoRecuperacao | None:
    """
    A TERCEIRA VIA.

    Dossiê que periciou assinatura em contrato => o contrato existiu.
    Laudo que descreve liberação de crédito    => o extrato daquela conta existiu.
    São 17.194 casos na base (28,7%), concentrando 69,7% da exposição.

    Só o item 'analisou_assinatura_contrato' autoriza confiança alta: um dossiê
    que validou apenas RG e liveness não prova que o contrato existe.
    """
    if not c.contrato and c.dossie:
        forte = bool(c.analise_dossie and c.analise_dossie.analisou_assinatura_contrato)
        doc, conf = "contrato", ("alta" if forte else "media")
        fund = ("O dossiê periciou a assinatura aposta no instrumento contratual: "
                "o contrato existe e não foi juntado." if forte else
                "Dossiê presente; confirmar se periciou assinatura em contrato.")
        novo = _p_perda(c, com_contrato=True)
    elif not c.extrato and c.laudo:
        doc, conf = "extrato", "media"
        fund = "O laudo descreve a liberação do crédito em conta: o extrato daquela conta existe."
        novo = _p_perda(c, com_extrato=True)
    elif not contrato_efetivo(c) or not c.extrato:
        doc = "contrato" if not contrato_efetivo(c) else "extrato"
        conf, fund = "baixa", "Documento ausente, sem sinal interno de que exista."
        novo = _p_perda(c, com_contrato=True) if doc == "contrato" else _p_perda(c, com_extrato=True)
    else:
        return None

    prob = P4.valor if conf == "alta" else P5.valor
    ganho = (custo_esperado_defesa(c.valor_causa, p_atual)
             - custo_esperado_defesa(c.valor_causa, novo)) * prob
    return PlanoRecuperacao(documento=doc, confianca=conf, fundamento=fund,
                            ganho_estimado=round(ganho, 2), p_perda_se_recuperado=round(novo, 4))


def decidir(c: CaseFeatures) -> Recomendacao:
    gate = avaliar_gate(c)
    p = _p_perda(c)
    custo_defesa = custo_esperado_defesa(c.valor_causa, p)

    nao_conforme = bool(c.analise_dossie and c.analise_dossie.veredito == "nao_conforme")
    faixa = calcular_faixa(c.valor_causa, p, c.uf, nao_conforme)
    rec = _plano_recuperacao(c, p)

    # se aceitar, paga o alvo; se recusar, o caso volta para a defesa
    custo_acordo = P3.valor * faixa.alvo + (1 - P3.valor) * custo_defesa

    segmento = table.chave(contrato_efetivo(c), c.extrato, c.comprovante_credito, c.sub_assunto)
    just = [gate.motivo, f"Segmento {segmento}: P(derrota) {p:.1%}."]
    premissas = [P1.id, P6.id, P3.id]
    alertas = [gate.alerta] if gate.alerta else []

    if rec and rec.confianca == "alta" and rec.ganho_estimado > 0:
        acao = "RECUPERAR"
        just.append(f"{rec.fundamento} Ganho esperado R$ {rec.ganho_estimado:,.2f}.")
        premissas.append(P4.id)
    elif custo_acordo < custo_defesa:
        acao = "ACORDAR"
        just.append(f"Custo esperado: acordo R$ {custo_acordo:,.2f} vs defesa R$ {custo_defesa:,.2f}.")
    else:
        acao = "DEFENDER"
        just.append(f"Defesa é o caminho mais barato: R$ {custo_defesa:,.2f} vs acordo R$ {custo_acordo:,.2f}.")
        if not gate.defesa_disponivel:
            alertas.append("Gate fechado: defender aqui exige justificativa registrada.")

    if c.contradicoes:
        just.extend(c.contradicoes)

    return Recomendacao(
        numero_processo=c.numero_processo, acao=acao,
        gate_defesa_disponivel=gate.defesa_disponivel, gate_motivo=gate.motivo,
        segmento=segmento, p_perda=round(p, 4), custo_esperado_defesa=round(custo_defesa, 2),
        acordo=faixa if acao == "ACORDAR" else None,
        recuperacao=rec if acao == "RECUPERAR" else None,
        justificativa=just, alertas=alertas, premissas_usadas=premissas,
    )
