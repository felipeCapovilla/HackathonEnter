"""
MOTOR DE VALOR DE ACORDO — política de 13/09, com a correção do mesmo dia.

Recebe a probabilidade que o modelo produziu e devolve o veredito econômico:
abertura, custo de defesa, walk-away, e — quando é acordo — o intervalo em que
o acordo é bom para o banco.

A REGRA DE OURO: a decisão sai do preço, não o contrário. Não há classificador
de acordo/defesa aqui. Calcula-se o preço; a decisão cai fora dele.

    custo_defesa = P x 0,74 x C + custas          # sem fator de sucumbência
    abertura     = 0,29 x C                       # onde abre
    alvo         = custo_defesa x (1 - MARGEM)    # onde quer fechar
    walk_away    = custo_defesa                   # onde levanta da mesa

    se walk_away < abertura -> DEFESA
    senão                   -> ACORDO, faixa [abertura, walk_away]

POR QUE A MARGEM NÃO ENTRA NA VIABILIDADE (correção de 13/09)

A versão anterior fazia `teto = custo_defesa x (1 - margem)` e deixava o teto
governar a decisão. Com isso a margem deslocava o limiar:

    margem  0%  ->  P* = 34,1%
    margem  5%  ->  P* = 35,9%
    margem 10%  ->  P* = 37,9%
    margem 20%  ->  P* = 42,6%

A 20% de margem o bucket de 4 subsídios (P = 35,9%, 15.719 processos — 26,2%
da carteira) voltava a ser DEFESA, que é exatamente o ganho principal da
política. A margem virou meta de negociação; a viabilidade pergunta apenas
"existe preço melhor que litigar?", não "capturo excedente suficiente?".

Efeito: agressividade de negociação e escopo da política viram alavancas
independentes, e o P* fica estável.

DUAS REGRAS DERIVADAS

1. Contraproposta acima do walk-away não é discricionariedade do advogado.
   É defesa. A aderência mede ofertar dentro da faixa, não se acorda.
2. Amplitude mínima: faixa estreita demais para negociar não vira faixa —
   vira um valor único, o walk-away, com `faixa.negociavel = False`. A decisão
   continua sendo ACORDO: o caso é viável, só não há o que negociar.
"""

from __future__ import annotations

from contracts.schema import FaixaNegociacao, VereditoAcordo

from .constants import (
    AMPLITUDE_MIN_REL,
    MARGEM,
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
) -> float:
    """
    P(derrota) x E[condenação] + custas + custo incremental.

    Sem fator de sucumbência: não há honorário na base, e o 0,15 do art. 85 §2º
    do CPC era premissa sobre o meio de uma faixa de 10%-20%. Retirado em 13/09.

    `custo_incremental` é o custo adicional de DEFENDER (audiência, recurso) e
    fica em 0,0 de propósito: é o P7 que constants.py se recusa a assumir. Só
    custo diferencial importa — o que ocorre nos dois ramos se cancela.
    """
    e_condenacao = RATIO_CONDENACAO.valor * valor_causa
    return p_nao_exito * e_condenacao + custas_uf + custo_incremental


def p_estrela(
    valor_causa: float,
    *,
    custas_uf: float = 0.0,
    custo_incremental: float = 0.0,
) -> float:
    """
    Limiar de indiferença DESTE caso: o P em que abrir custa o mesmo que litigar.

    DERIVADO das premissas, nunca literal. Sem custas o valor da causa se
    cancela e sobra o limiar puro de 39,2%; com custas o limiar cai, porque
    parte do custo de litigar independe de ganhar ou perder.

    Reproduz a tabela do §5.2 do documento:
        sem custas nem sucumbência ......... 39,2%   <- adotado
        com sucumbência .................... 34,1%
        com sucumbência + custas ........... ~30%
    """
    if valor_causa <= 0:
        raise ValueError(f"valor_causa deve ser > 0, recebido {valor_causa!r}")

    abertura = RATIO_ABERTURA.valor * valor_causa
    denominador = RATIO_CONDENACAO.valor * valor_causa
    bruto = (abertura - custas_uf - custo_incremental) / denominador
    return min(1.0, max(0.0, bruto))


def avaliar_acordo(
    valor_causa: float,
    p_nao_exito: float,
    *,
    p_nao_exito_inf: float | None = None,
    custas_uf: float = 0.0,
    custo_incremental: float = 0.0,
    margem: float = MARGEM.valor,
    amplitude_min_rel: float = AMPLITUDE_MIN_REL.valor,
) -> VereditoAcordo:
    """
    Veredito econômico do caso.

    Args:
        valor_causa: valor da causa em reais.
        p_nao_exito: P(o banco perde), saída do modelo. Se o modelo entrega
            P(êxito), converta antes com `p_nao_exito_de_exito`.
        p_nao_exito_inf: limite inferior do IC da probabilidade. Aperta apenas
            o ALVO, nunca o walk-away — ver nota sobre o IC abaixo.
        custas_uf: custas processuais. Default 0,0 — não há custas na base.
            Passe o valor real por UF quando o banco fornecer.
        custo_incremental: custo adicional de defender. Ver P7.
        margem: meta de negociação. Não afeta a decisão, por construção.
        amplitude_min_rel: abaixo deste piso a faixa vira um valor único
            (o walk-away). Não afeta a decisão.

    Returns:
        VereditoAcordo com `faixa` preenchida quando a decisão é ACORDO.

    SOBRE O INTERVALO DE CONFIANÇA

    O CLAUDE.md manda usar o limite superior do IC, mas justifica dizendo que
    isso gera "tetos mais apertados" — que é o efeito do limite INFERIOR.
    A contradição se resolve pela lógica da própria correção: a viabilidade usa
    o P honesto (senão o P* deixa de ser 34,1% e o bucket de 4 se perde de
    novo), e o conservadorismo por erro do modelo vira meta de negociação,
    junto com a margem. Casos com pouca evidência geram alvo mais apertado,
    não escopo de política diferente.
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
    if custas_uf < 0 or custo_incremental < 0:
        raise ValueError("custas_uf e custo_incremental não podem ser negativos")
    if not 0.0 <= margem < 1.0:
        raise ValueError(f"margem deve estar em [0, 1), recebido {margem!r}")
    if amplitude_min_rel < 0:
        raise ValueError("amplitude_min_rel não pode ser negativa")

    e_condenacao = RATIO_CONDENACAO.valor * valor_causa
    custo_defesa = custo_esperado_defesa(
        valor_causa, p_nao_exito,
        custas_uf=custas_uf, custo_incremental=custo_incremental,
    )

    abertura = RATIO_ABERTURA.valor * valor_causa
    walk_away = custo_defesa
    amplitude = walk_away - abertura
    amplitude_exigida = abertura * amplitude_min_rel

    limiar = p_estrela(
        valor_causa, custas_uf=custas_uf, custo_incremental=custo_incremental)

    premissas = [RATIO_CONDENACAO.id, RATIO_ABERTURA.id]

    # Os cinco campos comuns aos três retornos são repetidos de propósito, em vez
    # de expandidos de um dict: `**base` derrota o type checker (o dict infere
    # como dict[str, object]) e deixa erro de digitação em nome de campo passar
    # até o runtime.

    # Os dois ramos de DEFESA ficam separados apesar de o segundo cobrir o
    # primeiro (walk_away < abertura implica amplitude negativa). Para o
    # advogado e para o dashboard de aderência são coisas diferentes:
    # "litigar é mais barato" não é "a faixa é curta demais".
    if walk_away < abertura:
        return VereditoAcordo(
            decisao="DEFESA",
            motivo=(
                f"Litigar custa menos que a própria oferta de abertura: "
                f"R$ {custo_defesa:,.2f} contra R$ {abertura:,.2f}. "
                f"P(derrota) de {p_nao_exito:.1%} está abaixo do limiar de "
                f"indiferença de {limiar:.1%} deste caso."
            ),
            faixa=None,
            economia_no_alvo=0.0,
            premissas_usadas=premissas,
            p_nao_exito=round(p_nao_exito, 4),
            p_estrela=round(limiar, 4),
            e_condenacao=_round_money(e_condenacao),
            custo_defesa=_round_money(custo_defesa),
            policy_version=POLICY_VERSION,
        )

    # Meta de negociação. Usa o limite inferior do IC quando disponível, e é
    # limitada à faixa: não se mira abaixo da própria oferta de abertura nem
    # acima do ponto em que levantar da mesa é melhor.
    p_alvo = p_nao_exito if p_nao_exito_inf is None else p_nao_exito_inf
    custo_alvo = custo_esperado_defesa(
        valor_causa, p_alvo, custas_uf=custas_uf, custo_incremental=custo_incremental)
    alvo = min(max(custo_alvo * (1 - margem), abertura), walk_away)

    # Faixa curta demais para negociar não vira DEFESA: vira UM número. Abrir em
    # R$ X para fechar em R$ X + 50 não é negociação, é ruído — e obriga o
    # advogado a duas rodadas de conversa por nada. Nesses casos o motor entrega
    # o walk-away direto. O excedente abandonado é pequeno por construção: a
    # faixa inteira cabe em `amplitude_min_rel` da abertura.
    negociavel = amplitude >= amplitude_exigida
    if not negociavel:
        alvo = walk_away

    premissas_acordo = [*premissas, MARGEM.id, AMPLITUDE_MIN_REL.id]
    if p_nao_exito_inf is not None:
        premissas_acordo.append("IC")

    if negociavel:
        motivo = (
            f"Acordo entre R$ {abertura:,.2f} e R$ {walk_away:,.2f}, mirando "
            f"R$ {alvo:,.2f}. Defender custa R$ {custo_defesa:,.2f} esperados; "
            f"fechar no alvo economiza R$ {custo_defesa - alvo:,.2f}. "
            f"P(derrota) de {p_nao_exito:.1%} supera o limiar de indiferença de "
            f"{limiar:.1%} deste caso. "
            f"Acima de R$ {walk_away:,.2f} não é negociação: é defesa."
        )
    else:
        motivo = (
            f"Acordo em R$ {walk_away:,.2f} — valor único, não há faixa. "
            f"O espaço entre a abertura de R$ {abertura:,.2f} e o walk-away é de "
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
        economia_no_alvo=_round_money(custo_defesa - alvo),
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
