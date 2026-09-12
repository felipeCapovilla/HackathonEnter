"""
Composição das 3 camadas. ESTE é o único ponto de decisão do sistema.

    gate -> probabilidade -> valor esperado

Nenhum outro módulo decide nada. Se aparecer uma segunda implementação da
política em qualquer lugar do repositório, é bug.
"""
from __future__ import annotations

from contracts.schema import CaseFeatures, PlanoRecuperacao, Recomendacao
from src.policy import table
from src.policy.constants import P1, P3, P4, P5, P6
from src.policy.gate import avaliar_gate
from src.policy.pricing import calcular_faixa


def custo_esperado_defesa(c: CaseFeatures, p_perda: float) -> float:
    """P(derrota) x 0,72 x valor da causa, acrescido de sucumbência (P6)."""
    return p_perda * P1.valor * c.valor_causa * (1 + P6.valor)


def _plano_recuperacao(c: CaseFeatures, p_atual: float) -> PlanoRecuperacao | None:
    """
    A TERCEIRA VIA.

    Dossiê presente periciando assinatura em contrato => o contrato existiu.
    Laudo presente descrevendo liberação de crédito  => o extrato existiu.
    São 17.194 casos na base (28,7%), com 69,7% da exposição.
    """
    alvo: tuple[str, str, str] | None = None

    if not c.contrato and c.dossie:
        forte = bool(c.analise_dossie and c.analise_dossie.analisou_assinatura_contrato)
        alvo = ("contrato", "alta" if forte else "media",
                "Dossiê periciou a assinatura aposta no instrumento contratual: o contrato existe."
                if forte else "Dossiê presente; confirmar se periciou assinatura em contrato.")
    elif not c.extrato and c.laudo:
        alvo = ("extrato", "media",
                "Laudo descreve a liberação do crédito em conta: o extrato daquela conta existe.")
    elif not c.contrato or not c.extrato:
        doc = "contrato" if not c.contrato else "extrato"
        alvo = (doc, "baixa", "Documento ausente sem sinal interno de existência.")

    if alvo is None:
        return None

    doc, confianca, fundamento = alvo
    novo = table.p_perda(
        contrato=c.contrato or doc == "contrato",
        extrato=c.extrato or doc == "extrato",
        comprovante=c.comprovante_credito,
        sub_assunto=c.sub_assunto,
        uf=c.uf,
    )
    prob = P4.valor if confianca == "alta" else P5.valor
    ganho = (custo_esperado_defesa(c, p_atual) - custo_esperado_defesa(c, novo)) * prob
    return PlanoRecuperacao(
        documento=doc, confianca=confianca, fundamento=fundamento,
        ganho_estimado=round(ganho, 2), p_perda_se_recuperado=round(novo, 4),
    )


def decidir(c: CaseFeatures) -> Recomendacao:
    gate = avaliar_gate(c)
    p = table.p_perda(c.contrato, c.extrato, c.comprovante_credito, c.sub_assunto, c.uf)
    custo_defesa = custo_esperado_defesa(c, p)

    nao_conforme = bool(c.analise_dossie and c.analise_dossie.veredito == "nao_conforme")
    faixa = calcular_faixa(c.valor_causa, p, c.uf, nao_conforme)
    rec = _plano_recuperacao(c, p)

    just: list[str] = [gate.motivo, f"Segmento {table.chave(c.contrato, c.extrato, c.comprovante_credito, c.sub_assunto)}: P(derrota) {p:.1%}."]
    premissas = [P1.id, P6.id]

    # custo esperado do acordo: aceita -> paga o alvo; recusa -> volta para a defesa
    custo_acordo = P3.valor * faixa.alvo + (1 - P3.valor) * custo_defesa
    premissas.append(P3.id)

    if rec and rec.confianca == "alta" and rec.ganho_estimado > 0:
        acao = "RECUPERAR"
        just.append(f"{rec.fundamento} Ganho esperado R$ {rec.ganho_estimado:,.2f}.")
        premissas.append(P4.id)
    elif nao_conforme or not gate.defesa_disponivel or custo_acordo < custo_defesa:
        acao = "ACORDAR"
        just.append(f"Custo esperado: acordo R$ {custo_acordo:,.2f} vs defesa R$ {custo_defesa:,.2f}.")
    else:
        acao = "DEFENDER"
        just.append(f"Defesa é o caminho mais barato: R$ {custo_defesa:,.2f}.")

    if c.contradicoes:
        just.extend(c.contradicoes)

    return Recomendacao(
        numero_processo=c.numero_processo, acao=acao,
        gate_defesa_disponivel=gate.defesa_disponivel, gate_motivo=gate.motivo,
        segmento=table.chave(c.contrato, c.extrato, c.comprovante_credito, c.sub_assunto),
        p_perda=round(p, 4), custo_esperado_defesa=round(custo_defesa, 2),
        acordo=faixa if acao == "ACORDAR" else None,
        recuperacao=rec if acao == "RECUPERAR" else None,
        justificativa=just, premissas_usadas=premissas,
    )
