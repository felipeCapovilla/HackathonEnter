"""
Testes do motor de valor de acordo.

O teste que mais importa aqui é `test_margem_nao_move_a_decisao`. Ele existe
para impedir que a margem volte a governar a viabilidade — o bug que a correção
de 13/09 consertou e que custava 15.719 processos decididos errado.
"""

import pytest

from src.policy.constants import (
    AMPLITUDE_MIN_REL,
    MARGEM,
    POLICY_VERSION,
    P_ESTRELA_SEM_CUSTAS,
    RATIO_ABERTURA,
    RATIO_CONDENACAO,
)
from contracts.schema import FaixaNegociacao, VereditoAcordo
from src.policy.valor_acordo import (
    avaliar_acordo,
    custo_esperado_defesa,
    p_estrela,
    p_nao_exito_de_exito,
)

def faixa_de(v: VereditoAcordo) -> FaixaNegociacao:
    """
    Estreita `Optional[FaixaNegociacao]` e falha com mensagem útil se o veredito
    vier sem faixa. Acessar `v.faixa.abertura` direto funciona em runtime, mas o
    type checker não tem como saber que aquele caso sempre acorda.
    """
    assert v.faixa is not None, f"esperava ACORDO com faixa, veio {v.decisao}: {v.motivo}"
    return v.faixa


C = 15026.0  # valor da causa mediano da base

# P(Não Êxito) por quantidade de subsídios presentes — tabela do §3 dos documentos
BUCKETS = {0: 1.000, 1: 0.970, 2: 0.871, 3: 0.662, 4: 0.359, 5: 0.129, 6: 0.038}


# ── A correção de 13/09 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("p", list(BUCKETS.values()))
def test_margem_nao_move_a_decisao(p):
    """
    REGRESSÃO DA CORREÇÃO. A margem é meta de negociação, não restrição de
    viabilidade. Se este teste quebrar, alguém devolveu a margem para dentro
    do walk-away e o P* voltou a derivar com ela.
    """
    decisoes = {avaliar_acordo(C, p, margem=m).decisao
                for m in (0.0, 0.05, 0.10, 0.20, 0.35, 0.50)}
    assert len(decisoes) == 1, f"margem mudou a decisão em p={p}: {decisoes}"


def test_margem_move_o_alvo_mas_nunca_o_walk_away():
    """A margem tem que fazer alguma coisa — só não a viabilidade."""
    frouxa = avaliar_acordo(C, 0.662, margem=0.05)
    apertada = avaliar_acordo(C, 0.662, margem=0.35)

    assert faixa_de(frouxa).walk_away == faixa_de(apertada).walk_away
    assert faixa_de(frouxa).abertura == faixa_de(apertada).abertura
    assert faixa_de(apertada).alvo < faixa_de(frouxa).alvo


# ── P* derivado ──────────────────────────────────────────────────────────────

def test_p_estrela_sem_custas_bate_com_o_documento():
    """Sem sucumbência, o limiar puro é a linha de 39,2% da tabela do §5.2."""
    assert P_ESTRELA_SEM_CUSTAS == pytest.approx(0.392, abs=5e-4)
    esperado = RATIO_ABERTURA.valor / RATIO_CONDENACAO.valor
    assert P_ESTRELA_SEM_CUSTAS == pytest.approx(esperado)


def test_sucumbencia_nao_entra_no_custo():
    """Retirada em 13/09: não há honorário na base, o 0,15 era praxe do CPC."""
    p = 0.5
    assert custo_esperado_defesa(C, p, custas_uf=0.0) == pytest.approx(
        p * RATIO_CONDENACAO.valor * C)


@pytest.mark.parametrize("valor_causa", [5000.0, 15026.0, 40000.0, 250000.0])
def test_p_estrela_sem_custas_independe_do_valor_da_causa(valor_causa):
    """Igualando abertura e custo de defesa, C se cancela. É o ponto do §5.2."""
    assert p_estrela(valor_causa, custas_uf=0.0) == pytest.approx(P_ESTRELA_SEM_CUSTAS)


def test_p_estrela_nunca_e_meio():
    """Armadilha nº 1 do projeto: o limiar é econômico, não `if p > 0.5`."""
    assert p_estrela(C, custas_uf=0.0) < 0.5
    assert p_estrela(C) < 0.5


def test_custas_derrubam_o_limiar():
    """
    Custas independem de ganhar ou perder, então parte do custo de litigar é
    fixa e acordar fica relativamente melhor. Não há custas na base: o default
    é 0,0 e o valor real entra por parâmetro quando o banco fornecer.
    """
    assert p_estrela(C, custas_uf=600.0) < p_estrela(C)
    assert p_estrela(C) == pytest.approx(0.392, abs=1e-3)
    assert p_estrela(C, custas_uf=600.0) == pytest.approx(0.338, abs=1e-3)


# ── Tabela dos 7 buckets (§5.3) ──────────────────────────────────────────────

@pytest.mark.parametrize("n_subsidios,esperado", [
    (0, "ACORDO"), (1, "ACORDO"), (2, "ACORDO"), (3, "ACORDO"),
    (4, "DEFESA"),            # 15.719 processos — ver o teste abaixo
    (5, "DEFESA"), (6, "DEFESA"),
])
def test_tabela_de_buckets(n_subsidios, esperado):
    v = avaliar_acordo(C, BUCKETS[n_subsidios])
    assert v.decisao == esperado, f"{n_subsidios} subsídios: {v.motivo}"


def test_bucket_de_quatro_ficou_fora_da_politica():
    """
    ATENÇÃO — ESTE TESTE DOCUMENTA UMA PERDA, NÃO UM ACERTO.

    O bucket de 4 subsídios são 15.719 processos (26,2% da carteira) e era o
    ganho principal da política: o limiar econômico os colocava em ACORDO onde
    um classificador cortando em 50% os mandaria defender.

    Com a retirada da sucumbência e das custas (13/09) o custo de litigar
    encolheu, o limiar subiu para 39,2% e P = 35,9% passou a ficar ABAIXO dele.
    Não é mais questão de faixa estreita: litigar custa menos que a própria
    oferta de abertura.

    Passar custas reais por UF traz parte destes casos de volta.
    """
    v = avaliar_acordo(C, BUCKETS[4])

    assert v.decisao == "DEFESA"
    assert v.p_nao_exito < v.p_estrela, "agora a viabilidade é que barra"
    assert "Litigar custa menos" in v.motivo


def test_bucket_de_quatro_volta_com_custas_reais():
    """Não é um caso perdido: é um caso que depende de um dado que não temos."""
    assert avaliar_acordo(C, BUCKETS[4], custas_uf=400.0).decisao == "ACORDO"




# ── Invariantes da faixa ─────────────────────────────────────────────────────

@pytest.mark.parametrize("p", [0.45, 0.5, 0.662, 0.871, 1.0])
def test_faixa_e_ordenada(p):
    f = faixa_de(avaliar_acordo(C, p))
    assert f.abertura <= f.alvo <= f.walk_away
    assert f.amplitude == pytest.approx(f.walk_away - f.abertura, abs=0.01)


def test_alvo_colapsa_na_abertura_quando_a_faixa_e_minima():
    """
    Com amplitude perto do mínimo, walk_away x (1 - 0,20) cai abaixo da
    abertura. O clamp segura: não se mira abaixo da própria oferta de abertura.
    """
    f = faixa_de(avaliar_acordo(C, 0.45))      # faixa curta, mas ainda negociável
    assert f.negociavel
    assert f.alvo == pytest.approx(f.abertura, abs=0.01)


def test_defesa_nao_devolve_faixa():
    """Devolver faixa em DEFESA convida a oferta que a política acabou de rejeitar."""
    v = avaliar_acordo(C, BUCKETS[6])
    assert v.faixa is None
    assert v.economia_no_alvo == 0.0


def test_abertura_e_sempre_a_ancora_historica():
    for p in BUCKETS.values():
        v = avaliar_acordo(C, p)
        if v.faixa is not None:
            assert v.faixa.abertura == pytest.approx(RATIO_ABERTURA.valor * C, abs=0.01)


def test_economia_no_alvo_e_coerente():
    v = avaliar_acordo(C, 0.662)
    assert v.economia_no_alvo == pytest.approx(v.custo_defesa - faixa_de(v).alvo, abs=0.01)


# ── Amplitude mínima ─────────────────────────────────────────────────────────

def test_faixa_negociavel_tem_amplitude_suficiente():
    for p in (0.45, 0.5, 0.662, 0.871, 1.0):
        f = faixa_de(avaliar_acordo(C, p))
        assert f.negociavel
        assert f.amplitude >= f.abertura * AMPLITUDE_MIN_REL.valor - 0.01


def test_faixa_curta_vira_valor_unico():
    """
    Abrir em R$ X para fechar em R$ X + 90 não é negociação, é ruído. O motor
    entrega um número só — o walk-away — e a tela não mostra intervalo.
    """
    v = avaliar_acordo(C, 0.40)

    assert v.decisao == "ACORDO", "faixa curta NÃO é motivo para defender"
    f = faixa_de(v)
    assert f.negociavel is False
    assert f.alvo == f.walk_away
    assert f.amplitude < f.abertura * AMPLITUDE_MIN_REL.valor
    assert "valor único" in v.motivo


def test_amplitude_minima_nao_move_a_decisao():
    """
    REGRESSÃO. A amplitude mínima é regra de APRESENTAÇÃO, não de viabilidade.
    Mexer nela muda como o valor é mostrado, nunca se o caso entra na política.
    """
    for p in (0.395, 0.40, 0.45, 0.662):
        decisoes = {avaliar_acordo(C, p, amplitude_min_rel=a).decisao
                    for a in (0.0, 0.05, 0.15, 0.50)}
        assert decisoes == {"ACORDO"}, f"amplitude mudou a decisão em p={p}"


def test_economia_no_alvo_e_zero_no_valor_unico():
    """Pagar o walk-away é pagar o máximo: não sobra economia sobre litigar."""
    v = avaliar_acordo(C, 0.40)
    assert v.economia_no_alvo == pytest.approx(0.0, abs=0.01)






# ── Intervalo de confiança ───────────────────────────────────────────────────

def test_ic_aperta_o_alvo():
    sem_ic = avaliar_acordo(C, 0.662)
    com_ic = avaliar_acordo(C, 0.662, p_nao_exito_inf=0.55)
    assert faixa_de(com_ic).alvo < faixa_de(sem_ic).alvo


def test_ic_nao_move_a_decisao_nem_o_walk_away():
    """
    Viabilidade usa o P honesto. Se o IC mexesse no walk-away, o P* deixaria
    de ser 34,1% e o bucket de 4 se perderia de novo.
    """
    sem_ic = avaliar_acordo(C, 0.662)
    com_ic = avaliar_acordo(C, 0.662, p_nao_exito_inf=0.20)

    assert com_ic.decisao == sem_ic.decisao
    assert faixa_de(com_ic).walk_away == faixa_de(sem_ic).walk_away
    assert com_ic.p_estrela == sem_ic.p_estrela


def test_ic_nunca_empurra_o_alvo_abaixo_da_abertura():
    f = faixa_de(avaliar_acordo(C, 0.871, p_nao_exito_inf=0.05))
    assert f.alvo == pytest.approx(f.abertura, abs=0.01)


# ── Direção da probabilidade ─────────────────────────────────────────────────

def test_adaptador_de_p_exito():
    assert p_nao_exito_de_exito(0.70) == pytest.approx(0.30)
    assert p_nao_exito_de_exito(0.0) == 1.0


def test_trocar_a_direcao_inverte_a_decisao():
    """
    O erro mais caro possível nesta fronteira. p = 0,871 é acordo; o mesmo
    número lido como P(êxito) vira 0,129 e manda defender.
    """
    assert avaliar_acordo(C, 0.871).decisao == "ACORDO"
    assert avaliar_acordo(C, p_nao_exito_de_exito(0.871)).decisao == "DEFESA"


# ── Composição do custo ──────────────────────────────────────────────────────

def test_custo_de_defesa_segue_a_formula():
    p = 0.662
    esperado = p * RATIO_CONDENACAO.valor * C
    assert custo_esperado_defesa(C, p) == pytest.approx(esperado)


def test_custo_incremental_entra_no_custo_de_defender():
    base = avaliar_acordo(C, 0.662)
    com_custo = avaliar_acordo(C, 0.662, custo_incremental=1000.0)
    assert com_custo.custo_defesa == pytest.approx(base.custo_defesa + 1000.0)
    assert faixa_de(com_custo).walk_away > faixa_de(base).walk_away


def test_e_condenacao_nao_depende_da_probabilidade():
    a = avaliar_acordo(C, 0.10)
    b = avaliar_acordo(C, 0.90)
    assert a.e_condenacao == b.e_condenacao == pytest.approx(RATIO_CONDENACAO.valor * C)


# ── Auditoria ────────────────────────────────────────────────────────────────

def test_policy_version_em_toda_saida():
    """Obrigatório em toda linha persistida: um caso de hoje só tem desfecho em meses."""
    for p in BUCKETS.values():
        assert avaliar_acordo(C, p).policy_version == POLICY_VERSION


def test_premissas_usadas_sao_declaradas():
    v = avaliar_acordo(C, 0.662)
    assert {RATIO_CONDENACAO.id, RATIO_ABERTURA.id} <= set(v.premissas_usadas)
    assert MARGEM.id in v.premissas_usadas




def test_motivo_fala_em_reais():
    """O advogado lê reais, não probabilidade crua."""
    v = avaliar_acordo(C, BUCKETS[3])
    assert "R$" in v.motivo
    assert "não é negociação: é defesa" in v.motivo


# ── Bordas ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor_causa", [0.0, -1.0])
def test_valor_causa_invalido(valor_causa):
    with pytest.raises(ValueError, match="valor_causa"):
        avaliar_acordo(valor_causa, 0.5)


@pytest.mark.parametrize("p", [-0.01, 1.01])
def test_probabilidade_fora_do_intervalo(p):
    with pytest.raises(ValueError, match="p_nao_exito"):
        avaliar_acordo(C, p)


def test_ic_invertido_e_rejeitado():
    with pytest.raises(ValueError, match="limite inferior"):
        avaliar_acordo(C, 0.30, p_nao_exito_inf=0.60)


def test_custos_negativos_rejeitados():
    with pytest.raises(ValueError, match="negativos"):
        avaliar_acordo(C, 0.5, custas_uf=-1.0)


def test_margem_invalida_rejeitada():
    with pytest.raises(ValueError, match="margem"):
        avaliar_acordo(C, 0.5, margem=1.0)


def test_p_exito_fora_do_intervalo():
    with pytest.raises(ValueError, match="p_exito"):
        p_nao_exito_de_exito(1.5)


def test_extremos_de_probabilidade_nao_quebram():
    assert avaliar_acordo(C, 0.0).decisao == "DEFESA"
    assert avaliar_acordo(C, 1.0).decisao == "ACORDO"
