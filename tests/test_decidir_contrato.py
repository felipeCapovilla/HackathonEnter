"""decidir() com os termos do contrato, fonte externa de probabilidade e casos de borda."""
import pytest

from contracts.schema import CaseFeatures, Honorario, ParametrosContrato
from src.policy.constants import CONCESSAO, CUSTO_MENSAL_TEMPO, DURACAO_MESES
from src.policy.engine import decidir


def caso(**kw) -> CaseFeatures:
    base = dict(numero_processo="t", uf="SP", sub_assunto="Generico", valor_causa=15000.0,
                contrato=True, extrato=True, comprovante_credito=True,
                dossie=False, demonstrativo=True, laudo=False)
    return CaseFeatures(**{**base, **kw})


def test_contrato_padrao_espelha_as_premissas_de_tempo():
    padrao = ParametrosContrato()
    assert padrao.custo_mensal_tempo == CUSTO_MENSAL_TEMPO.valor
    assert padrao.duracao_meses == DURACAO_MESES.valor
    assert padrao.concessao == CONCESSAO.valor


def test_quantidade_de_subsidios_nao_decide():
    """Dois casos com exatamente 4 subsídios, decisões opostas: o que decide é QUAL documento falta."""
    sem_contrato_e_extrato = caso(uf="SP", sub_assunto="Golpe", contrato=False, extrato=False, dossie=True, laudo=True)
    completo_sem_dossie = caso(uf="SP", sub_assunto="Generico", demonstrativo=False)
    assert decidir(sem_contrato_e_extrato).acao == "ACORDAR"
    assert decidir(completo_sem_dossie).acao == "DEFENDER"


def test_honorario_na_vitoria_torna_defender_mais_caro():
    c = caso(uf="MA", contrato=False)  # C0 E1 CC1 Genérico em UF de risco baixo: defesa
    assert decidir(c).acao == "DEFENDER"
    contrato = ParametrosContrato(versao="bonus-exito", honorario_defesa_ganha=Honorario(tipo="fixo", valor=3000))
    r = decidir(c, contrato)
    assert r.acao == "ACORDAR"
    assert r.versao_contrato == "bonus-exito"


def test_honorario_por_acordo_encarece_acordar():
    c = caso(uf="MA", sub_assunto="Golpe", contrato=False)  # C0 E1 CC1 Golpe em MA: acordo
    assert decidir(c).acao == "ACORDAR"
    contrato = ParametrosContrato(honorario_acordo=Honorario(tipo="percentual_valor_causa", valor=0.15))
    assert decidir(c, contrato).acao == "DEFENDER"


def test_alcada_abaixo_da_abertura_bloqueia_o_acordo():
    c = caso(sub_assunto="Golpe", contrato=False, extrato=False, comprovante_credito=False)
    assert decidir(c).acao == "ACORDAR"
    r = decidir(c, ParametrosContrato(teto_alcada_fator=0.20))
    assert r.acao == "DEFENDER"
    assert any("alçada" in j for j in r.justificativa)


def test_alcada_limita_o_walk_away():
    c = caso(sub_assunto="Golpe", contrato=False, extrato=False, comprovante_credito=False)
    livre, limitada = decidir(c), decidir(c, ParametrosContrato(teto_alcada_fator=0.32))
    assert limitada.acordo.walk_away == pytest.approx(0.32 * 15000)
    assert limitada.acordo.walk_away < livre.acordo.walk_away


def test_sem_custo_de_tempo_o_limiar_sobe():
    c = caso(contrato=False)
    sem_tempo = decidir(c, ParametrosContrato(custo_mensal_tempo=0.0))
    assert sem_tempo.p_estrela > decidir(c).p_estrela


def test_percentual_acima_de_100_e_rejeitado():
    with pytest.raises(ValueError, match="percentual"):
        Honorario(tipo="percentual_valor_causa", valor=15)


def test_probabilidade_externa_substitui_a_tabela_sem_perder_o_gate():
    c = caso(contrato=False, extrato=False)
    r = decidir(c, p_perda=0.05)
    assert r.fonte_probabilidade == "externa"
    assert r.p_perda == 0.05
    assert r.acao == "DEFENDER"
    assert r.gate_defesa_disponivel is False
    assert any("registre o motivo" in a for a in r.alertas)


def test_valor_da_causa_ausente_decide_sem_sugerir_valor():
    r = decidir(caso(valor_causa=0.0, contrato=False, extrato=False))
    assert r.acao == "ACORDAR"
    assert r.acordo is None
    assert any("Sem o valor da causa" in a for a in r.alertas)


def test_toda_recomendacao_carrega_versoes():
    r = decidir(caso())
    assert r.versao_politica.startswith("politica-") and "+base-" in r.versao_politica
    assert r.versao_contrato == "padrao"


def test_concessao_do_contrato_sobe_o_alvo_sem_mudar_a_decisao():
    c = caso(sub_assunto="Golpe", contrato=False, extrato=False, comprovante_credito=False)
    firme, cedente = decidir(c), decidir(c, ParametrosContrato(concessao=0.5))
    assert firme.acao == cedente.acao == "ACORDAR"
    assert firme.acordo.alvo == pytest.approx(firme.acordo.abertura)
    assert cedente.acordo.alvo > firme.acordo.alvo
    assert cedente.acordo.walk_away == firme.acordo.walk_away
