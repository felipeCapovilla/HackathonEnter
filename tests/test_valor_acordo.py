"""
Testes do motor de valor de acordo.

O teste que mais importa aqui é `test_concessao_nao_move_a_decisao`. Ele existe
para impedir que a meta de negociação volte a governar a viabilidade: se ela
entrar no walk-away, a agressividade de negociação passa a mudar o escopo.
"""

import pytest

from src.policy.constants import (
    AMPLITUDE_MIN_REL,
    CONCESSAO,
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

# Pontos de probabilidade usados como amostra nos testes. São médias por QUANTIDADE
# de subsídios e não servem para decidir: a decisão depende de QUAIS documentos.
BUCKETS = {0: 1.000, 1: 0.970, 2: 0.871, 3: 0.662, 4: 0.359, 5: 0.129, 6: 0.038}


# ── A correção de 13/09 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("p", list(BUCKETS.values()))
def test_concessao_nao_move_a_decisao(p):
    """
    REGRESSÃO. A concessão é meta de negociação, não restrição de viabilidade.
    Se este teste quebrar, alguém devolveu a meta para dentro do walk-away.
    """
    decisoes = {avaliar_acordo(C, p, concessao=k).decisao
                for k in (0.0, 0.05, 0.10, 0.20, 0.35, 0.50, 1.0)}
    assert len(decisoes) == 1, f"concessão mudou a decisão em p={p}: {decisoes}"


def test_concessao_move_o_alvo_mas_nunca_o_walk_away():
    """A concessão tem que fazer alguma coisa — só não a viabilidade."""
    firme = avaliar_acordo(C, 0.662, concessao=0.0)
    cedente = avaliar_acordo(C, 0.662, concessao=0.35)

    assert faixa_de(firme).walk_away == faixa_de(cedente).walk_away
    assert faixa_de(firme).abertura == faixa_de(cedente).abertura
    assert faixa_de(firme).alvo < faixa_de(cedente).alvo


def test_alvo_padrao_e_o_preco_de_mercado():
    """Os acordos reais fecham na abertura qualquer que seja o risco; o alvo padrão fica nela."""
    assert CONCESSAO.valor == 0.0
    for p in (0.45, 0.662, 0.871, 1.0):
        f = faixa_de(avaliar_acordo(C, p))
        assert f.alvo == pytest.approx(f.abertura, abs=0.01)


# ── P* derivado ──────────────────────────────────────────────────────────────

def test_p_estrela_sem_custas_e_derivado_das_premissas_medidas():
    """Sem custas nem tempo, o limiar puro é abertura / condenação média (0,29 / 0,7108)."""
    esperado = RATIO_ABERTURA.valor / RATIO_CONDENACAO.valor
    assert P_ESTRELA_SEM_CUSTAS == pytest.approx(esperado)
    assert P_ESTRELA_SEM_CUSTAS == pytest.approx(0.408, abs=1e-3)


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
    assert p_estrela(C) == pytest.approx(0.408, abs=1e-3)
    assert p_estrela(C, custas_uf=600.0) == pytest.approx(0.352, abs=1e-3)


# ── Invariantes da faixa ─────────────────────────────────────────────────────

@pytest.mark.parametrize("p", [0.45, 0.5, 0.662, 0.871, 1.0])
def test_faixa_e_ordenada(p):
    f = faixa_de(avaliar_acordo(C, p))
    assert f.abertura <= f.alvo <= f.walk_away
    assert f.amplitude == pytest.approx(f.walk_away - f.abertura, abs=0.01)


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
    v = avaliar_acordo(C, 0.42)

    assert v.decisao == "ACORDO", "faixa curta NÃO é motivo para defender"
    f = faixa_de(v)
    assert f.negociavel is False
    assert f.alvo == f.walk_away
    assert f.amplitude < f.abertura * AMPLITUDE_MIN_REL.valor
    assert "sem margem para negociar" in v.motivo


def test_amplitude_minima_nao_move_a_decisao():
    """
    REGRESSÃO. A amplitude mínima é regra de APRESENTAÇÃO, não de viabilidade.
    Mexer nela muda como o valor é mostrado, nunca se o caso entra na política.
    """
    for p in (0.415, 0.42, 0.45, 0.662):
        decisoes = {avaliar_acordo(C, p, amplitude_min_rel=a).decisao
                    for a in (0.0, 0.05, 0.15, 0.50)}
        assert decisoes == {"ACORDO"}, f"amplitude mudou a decisão em p={p}"


def test_economia_no_alvo_e_zero_no_valor_unico():
    """Pagar o walk-away é pagar o máximo: não sobra economia sobre litigar."""
    v = avaliar_acordo(C, 0.42)
    assert v.economia_no_alvo == pytest.approx(0.0, abs=0.01)






# ── Intervalo de confiança ───────────────────────────────────────────────────

def test_ic_aperta_o_alvo():
    sem_ic = avaliar_acordo(C, 0.662, concessao=0.5)
    com_ic = avaliar_acordo(C, 0.662, concessao=0.5, p_nao_exito_inf=0.55)
    assert faixa_de(com_ic).alvo < faixa_de(sem_ic).alvo


def test_ic_nao_move_a_decisao_nem_o_walk_away():
    """
    Viabilidade usa o P honesto. Se o IC mexesse no walk-away, a incerteza da
    estimativa passaria a mudar quais casos entram na política.
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
    assert CONCESSAO.id in v.premissas_usadas




def test_motivo_fala_em_reais():
    """O advogado lê reais, não probabilidade crua."""
    v = avaliar_acordo(C, BUCKETS[3])
    assert "R$" in v.motivo
    assert "defender sai mais barato" in v.motivo


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


def test_concessao_invalida_rejeitada():
    with pytest.raises(ValueError, match="concessao"):
        avaliar_acordo(C, 0.5, concessao=1.5)


def test_p_exito_fora_do_intervalo():
    with pytest.raises(ValueError, match="p_exito"):
        p_nao_exito_de_exito(1.5)


def test_extremos_de_probabilidade_nao_quebram():
    assert avaliar_acordo(C, 0.0).decisao == "DEFESA"
    assert avaliar_acordo(C, 1.0).decisao == "ACORDO"
