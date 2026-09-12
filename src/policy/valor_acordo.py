"""
MOTOR DE VALOR DE ACORDO — preço primeiro, decisão depois.

Recebe a probabilidade de derrota e devolve o veredito econômico: abertura,
custo de defesa, walk-away e, quando é acordo, o intervalo em que o acordo é
bom para o banco.

A REGRA DE OURO: a decisão sai do preço, não o contrário. Não há classificador
de acordo/defesa aqui. Calcula-se o preço; a decisão cai fora dele.

    E[condenação] = 0,7108 x C                          # média medida (P1)
    custo_defesa  = P x (E[condenação] x fator_tempo + honorário se perder)
                  + (1 - P) x honorário se ganhar + custas + custo incremental
    abertura      = 0,29 x C                            # mediana dos acordos (P2)
    walk_away     = custo_defesa - honorário do acordo  # limitado pela alçada
    alvo          = abertura + CONCESSAO x (walk_away - abertura)

    se walk_away < abertura -> DEFESA
    senão                   -> ACORDO, faixa [abertura, walk_away]

POR QUE A CONCESSÃO NÃO ENTRA NA VIABILIDADE

Se a concessão governasse o teto, a agressividade de negociação mudaria o
escopo da política. A viabilidade pergunta apenas "existe preço melhor que
litigar?"; a concessão define onde se mira dentro dessa resposta.

POR QUE O ALVO FICA NA ABERTURA

O walk-away (o custo esperado da defesa) é o TETO da negociação, não o alvo.
Nos 280 acordos reais o valor fechado não sobe com o risco do caso: fecha em
~29% da causa tanto a 10% quanto a 95% de probabilidade de derrota. Mirar em
80% do walk-away significava aceitar ~54% da causa na mediana e zerava a
economia no backtest.

DUAS REGRAS DERIVADAS

1. Contraproposta acima do walk-away não é discricionariedade do advogado.
   É defesa. A aderência mede ofertar dentro da faixa, não se acorda.
2. Amplitude mínima: faixa estreita demais para negociar não vira faixa —
   vira um valor único, o walk-away, com `faixa.negociavel = False`. A decisão
   continua sendo ACORDO: o caso é viável, só não há o que negociar.

Honorários e alçada vêm do contrato vigente banco–escritório
(contracts.schema.ParametrosContrato); com todos em zero e fator de tempo 1
o motor é o original.
"""

from __future__ import annotations

from contracts.schema import FaixaNegociacao, VereditoAcordo

from .constants import (
    AMPLITUDE_MIN_REL,
    CONCESSAO,
    POLICY_VERSION,
    P_ESTRELA_SEM_CUSTAS,
    RATIO_ABERTURA,
    RATIO_CONDENACAO,
)


def _round_money(valor: float) -> float:
    return round(valor, 2)


def p_nao_exito_de_exito(p_exito: float) -> float:
    """
    Adaptador explícito de direção da probabilidade.

    A política precisa de P(Não Êxito) = P(o banco perde). O modelo pode
    entregar qualquer um dos dois lados, e trocá-los inverte toda a decisão
    sem levantar erro nenhum. Converter aqui, na fronteira, deixa a direção
    visível no código de quem chama.
    """
    if not 0.0 <= p_exito <= 1.0:
        raise ValueError(f"p_exito deve estar em [0, 1], recebido {p_exito!r}")
    return 1.0 - p_exito


def custo_esperado_defesa(
    valor_causa: float,
    p_nao_exito: float,
    *,
    custas_uf: float = 0.0,
    custo_incremental: float = 0.0,
    fator_tempo: float = 1.0,
    honorario_perda: float = 0.0,
    honorario_ganho: float = 0.0,
) -> float:
    """
    P(derrota) x (E[condenação] x fator de tempo + honorário se perder)
    + (1 - P(derrota)) x honorário se ganhar + custas + custo incremental.

    Só custo diferencial importa: o que ocorre nos dois ramos (mensalidade do
    escritório, valor fixo por caso novo) se cancela e não entra.
    """
    e_condenacao = RATIO_CONDENACAO.valor * valor_causa
    return (p_nao_exito * (e_condenacao * fator_tempo + honorario_perda)
            + (1.0 - p_nao_exito) * honorario_ganho + custas_uf + custo_incremental)


def p_estrela(
    valor_causa: float,
    *,
    custas_uf: float = 0.0,
    custo_incremental: float = 0.0,
    fator_tempo: float = 1.0,
    honorario_perda: float = 0.0,
    honorario_ganho: float = 0.0,
    honorario_acordo: float = 0.0,
) -> float:
    """
    Limiar de indiferença DESTE caso: o P em que acordar na abertura custa o
    mesmo que litigar. Derivado das premissas, nunca literal.

    Sem custas, honorários nem tempo, o valor da causa se cancela e sobra o
    limiar puro P2 / P1. Custas e honorário na vitória baixam o limiar (parte
    do custo de litigar não depende de perder); tempo e honorário na derrota
    também baixam; honorário de acordo sobe.
    """
    if valor_causa <= 0:
        raise ValueError(f"valor_causa deve ser > 0, recebido {valor_causa!r}")

    abertura = RATIO_ABERTURA.valor * valor_causa
    denominador = RATIO_CONDENACAO.valor * valor_causa * fator_tempo + honorario_perda - honorario_ganho
    if denominador <= 0:
        return 1.0
    bruto = (abertura + honorario_acordo - honorario_ganho - custas_uf - custo_incremental) / denominador
    return min(1.0, max(0.0, bruto))


def avaliar_acordo(
    valor_causa: float,
    p_nao_exito: float,
    *,
    p_nao_exito_inf: float | None = None,
    custas_uf: float = 0.0,
    custo_incremental: float = 0.0,
    fator_tempo: float = 1.0,
    honorario_perda: float = 0.0,
    honorario_ganho: float = 0.0,
    honorario_acordo: float = 0.0,
    teto_alcada: float | None = None,
    concessao: float = CONCESSAO.valor,
    amplitude_min_rel: float = AMPLITUDE_MIN_REL.valor,
) -> VereditoAcordo:
    """
    Veredito econômico do caso.

    Args:
        valor_causa: valor da causa em reais.
        p_nao_exito: P(o banco perde). Se a fonte entrega P(êxito), converta
            antes com `p_nao_exito_de_exito`.
        p_nao_exito_inf: limite inferior do IC da probabilidade. Aperta apenas
            o ALVO, nunca o walk-away.
        custas_uf: custas processuais. Default 0,0 — não há custas na base.
        custo_incremental: custo adicional de defender.
        fator_tempo: multiplica a condenação esperada (juros e capital parado
            enquanto o processo dura). 1,0 = sem custo de tempo.
        honorario_perda, honorario_ganho, honorario_acordo: honorários do
            contrato, em reais, que dependem do desfecho.
        teto_alcada: maior oferta autorizada pelo banco, em reais.
        concessao: fração do excedente cedida no alvo. Não afeta a decisão.
        amplitude_min_rel: abaixo deste piso a faixa vira um valor único
            (o walk-away). Não afeta a decisão.

    SOBRE O INTERVALO DE CONFIANÇA

    A viabilidade usa o P honesto; o conservadorismo por erro de estimativa
    vira meta de negociação, junto com a concessão. Casos com pouca evidência
    geram alvo mais apertado, não escopo de política diferente.
    """
    if valor_causa <= 0:
        raise ValueError(f"valor_causa deve ser > 0, recebido {valor_causa!r}")
    if not 0.0 <= p_nao_exito <= 1.0:
        raise ValueError(f"p_nao_exito deve estar em [0, 1], recebido {p_nao_exito!r}")
    if p_nao_exito_inf is not None:
        if not 0.0 <= p_nao_exito_inf <= 1.0:
            raise ValueError(
                f"p_nao_exito_inf deve estar em [0, 1], recebido {p_nao_exito_inf!r}")
        if p_nao_exito_inf > p_nao_exito:
            raise ValueError(
                f"p_nao_exito_inf ({p_nao_exito_inf}) não pode ser maior que "
                f"p_nao_exito ({p_nao_exito}): não é limite inferior de IC")
    if min(custas_uf, custo_incremental, honorario_perda, honorario_ganho, honorario_acordo) < 0:
        raise ValueError("custas, custo incremental e honorários não podem ser negativos")
    if fator_tempo <= 0:
        raise ValueError(f"fator_tempo deve ser > 0, recebido {fator_tempo!r}")
    if teto_alcada is not None and teto_alcada <= 0:
        raise ValueError(f"teto_alcada deve ser > 0, recebido {teto_alcada!r}")
    if not 0.0 <= concessao <= 1.0:
        raise ValueError(f"concessao deve estar em [0, 1], recebido {concessao!r}")
    if amplitude_min_rel < 0:
        raise ValueError("amplitude_min_rel não pode ser negativa")

    custos = dict(custas_uf=custas_uf, custo_incremental=custo_incremental, fator_tempo=fator_tempo,
                  honorario_perda=honorario_perda, honorario_ganho=honorario_ganho)
    e_condenacao = RATIO_CONDENACAO.valor * valor_causa
    custo_defesa = custo_esperado_defesa(valor_causa, p_nao_exito, **custos)

    abertura = RATIO_ABERTURA.valor * valor_causa
    walk_away_economico = custo_defesa - honorario_acordo
    limitado_pela_alcada = teto_alcada is not None and teto_alcada < walk_away_economico
    walk_away = teto_alcada if limitado_pela_alcada else walk_away_economico
    amplitude = walk_away - abertura
    amplitude_exigida = abertura * amplitude_min_rel

    limiar = p_estrela(valor_causa, honorario_acordo=honorario_acordo, **custos)
    premissas = [RATIO_CONDENACAO.id, RATIO_ABERTURA.id]

    if walk_away < abertura:
        if limitado_pela_alcada and walk_away_economico >= abertura:
            motivo = (
                f"Acordar seria mais barato que litigar (R$ {custo_defesa:,.2f} esperados), "
                f"mas a alçada do banco limita a oferta a R$ {walk_away:,.2f}, abaixo da "
                f"abertura de R$ {abertura:,.2f}. Sem autorização para ofertar, a recomendação é defesa."
            )
        else:
            motivo = (
                f"Litigar custa menos que a própria oferta de abertura: "
                f"R$ {custo_defesa:,.2f} contra R$ {abertura + honorario_acordo:,.2f}. "
                f"P(derrota) de {p_nao_exito:.1%} está abaixo do limiar de "
                f"indiferença de {limiar:.1%} deste caso."
            )
        return VereditoAcordo(
            decisao="DEFESA",
            motivo=motivo,
            faixa=None,
            economia_no_alvo=0.0,
            premissas_usadas=premissas,
            p_nao_exito=round(p_nao_exito, 4),
            p_estrela=round(limiar, 4),
            e_condenacao=_round_money(e_condenacao),
            custo_defesa=_round_money(custo_defesa),
            policy_version=POLICY_VERSION,
        )

    # Meta de negociação: limite inferior do IC quando disponível, sempre dentro
    # da faixa — nunca abaixo da abertura nem acima do walk-away.
    p_alvo = p_nao_exito if p_nao_exito_inf is None else p_nao_exito_inf
    walk_away_alvo = min(custo_esperado_defesa(valor_causa, p_alvo, **custos) - honorario_acordo, walk_away)
    alvo = min(max(abertura + concessao * (walk_away_alvo - abertura), abertura), walk_away)

    # Faixa curta demais para negociar vira UM número, não DEFESA.
    negociavel = amplitude >= amplitude_exigida
    if not negociavel:
        alvo = walk_away

    premissas_acordo = [*premissas, CONCESSAO.id, AMPLITUDE_MIN_REL.id]
    if p_nao_exito_inf is not None:
        premissas_acordo.append("IC")

    economia = custo_defesa - (alvo + honorario_acordo)
    limite = "limite de alçada" if limitado_pela_alcada else "walk-away"
    if negociavel:
        motivo = (
            f"Acordo entre R$ {abertura:,.2f} e R$ {walk_away:,.2f}, mirando "
            f"R$ {alvo:,.2f}. Defender custa R$ {custo_defesa:,.2f} esperados; "
            f"fechar no alvo economiza R$ {economia:,.2f}. "
            f"P(derrota) de {p_nao_exito:.1%} supera o limiar de indiferença de "
            f"{limiar:.1%} deste caso. "
            f"Acima de R$ {walk_away:,.2f} ({limite}) não é negociação: é defesa."
        )
    else:
        motivo = (
            f"Acordo em R$ {walk_away:,.2f} — valor único, não há faixa. "
            f"O espaço entre a abertura de R$ {abertura:,.2f} e o {limite} é de "
            f"R$ {amplitude:,.2f}, pequeno demais para negociar. "
            f"P(derrota) de {p_nao_exito:.1%} está logo acima do limiar de "
            f"{limiar:.1%}: litigar custa quase o mesmo. "
            f"Acima de R$ {walk_away:,.2f} não é negociação: é defesa."
        )

    return VereditoAcordo(
        decisao="ACORDO",
        motivo=motivo,
        faixa=FaixaNegociacao(
            abertura=_round_money(abertura),
            alvo=_round_money(alvo),
            walk_away=_round_money(walk_away),
            amplitude=_round_money(amplitude),
            negociavel=negociavel,
        ),
        economia_no_alvo=_round_money(economia),
        premissas_usadas=premissas_acordo,
        p_nao_exito=round(p_nao_exito, 4),
        p_estrela=round(limiar, 4),
        e_condenacao=_round_money(e_condenacao),
        custo_defesa=_round_money(custo_defesa),
        policy_version=POLICY_VERSION,
    )


__all__ = [
    "P_ESTRELA_SEM_CUSTAS",
    "avaliar_acordo",
    "custo_esperado_defesa",
    "p_estrela",
    "p_nao_exito_de_exito",
]
