"""
TESTE DE FUMAÇA — não remover.

Uma solução premiada de um hackathon anterior levou o modelo inteiro a produção
com as features chegando zeradas: o front mandava uma chave, o back lia outra.
O advogado via a MESMA probabilidade em todo processo e ninguém percebeu.

Este teste existe para tornar isso impossível: os dois casos-exemplo estão nos
extremos opostos da tabela. Se voltarem iguais, alguém quebrou a fronteira.
"""
from contracts.schema import AnaliseDossie, CaseFeatures
from src.policy.engine import decidir

CASO_01 = CaseFeatures(  # todos os 6 subsídios; autora usou o dinheiro
    numero_processo="0801234-56.2024.8.10.0001", uf="MA", sub_assunto="Generico",
    valor_causa=15000.0, contrato=True, extrato=True, comprovante_credito=True,
    dossie=True, demonstrativo=True, laudo=True,
)
CASO_02 = CaseFeatures(  # sem contrato, sem extrato, sem dossiê; dinheiro em conta de terceiro
    numero_processo="0654321-09.2024.8.04.0001", uf="AM", sub_assunto="Golpe",
    valor_causa=15000.0, contrato=False, extrato=False, comprovante_credito=True,
    dossie=False, demonstrativo=True, laudo=True,
)
PERICIOU = AnaliseDossie(veredito="conforme", analisou_assinatura_contrato=True)


def test_os_dois_casos_nao_podem_dar_igual():
    a, b = decidir(CASO_01), decidir(CASO_02)
    assert a.p_perda != b.p_perda, "features chegaram zeradas ou constantes"
    assert a.p_perda < 0.10, f"Caso 01 deveria ser defesa clara, veio {a.p_perda:.1%}"
    assert b.p_perda > 0.90, f"Caso 02 deveria ser perda quase certa, veio {b.p_perda:.1%}"


def test_caso_01_defende():
    r = decidir(CASO_01)
    assert r.acao == "DEFENDER"
    assert r.acordo is None


def test_caso_02_acorda_com_faixa_ordenada():
    r = decidir(CASO_02)
    assert r.acao == "ACORDAR"
    assert r.gate_defesa_disponivel is False
    assert r.acordo.abertura <= r.acordo.alvo <= r.acordo.walk_away
    assert r.acordo.walk_away <= r.custo_esperado_defesa


def test_dossie_nao_conforme_invalida_o_contrato():
    """
    Não conformidade não pula a economia: derruba o contrato como prova e
    reprecifica. Forçar acordo aqui pagaria valor certo para evitar um custo
    esperado muito menor.
    """
    c = CASO_01.model_copy(update={"analise_dossie": AnaliseDossie(
        veredito="nao_conforme", analisou_assinatura_contrato=True)})
    base, r = decidir(CASO_01), decidir(c)
    assert r.p_perda > base.p_perda, "contrato deveria ter sido desconsiderado"
    assert r.segmento.startswith("C0"), r.segmento
    assert any("assinatura não confere" in a for a in r.alertas)


def test_terceira_via_quando_o_documento_muda_a_melhor_opcao():
    """Com extrato e sem contrato, o dossiê prova que o contrato existe: recuperar vence acordar."""
    c = CASO_02.model_copy(update={"extrato": True, "dossie": True, "analise_dossie": PERICIOU})
    r = decidir(c)
    assert r.acao == "RECUPERAR"
    assert r.recuperacao.documento == "contrato"
    assert r.recuperacao.confianca == "alta"
    assert r.recuperacao.ganho_estimado > 0
    assert r.acordo is not None, "o advogado precisa da faixa para o caso de o documento não vir"


def test_recuperar_so_o_contrato_sem_extrato_nao_compensa():
    """Sem extrato, mesmo com o contrato a defesa segue mais cara que acordar."""
    c = CASO_02.model_copy(update={"dossie": True, "analise_dossie": PERICIOU})
    assert decidir(c).acao == "ACORDAR"


def test_ajuste_de_uf_nao_estoura_nos_extremos():
    """Ajuste de UF é em log-odds, não multiplicativo."""
    from src.policy.table import p_perda
    for uf in ("AM", "SP", "MA"):
        p = p_perda(False, False, False, "Golpe", uf)
        assert 0.90 < p < 1.0, f"{uf}: {p}"


def test_recuperar_exige_que_o_dossie_tenha_periciado_o_contrato():
    """Dossiê que só validou RG e liveness não prova que o contrato existe."""
    base = CASO_02.model_copy(update={"extrato": True, "dossie": True})
    fraco = base.model_copy(update={"analise_dossie": AnaliseDossie(
        veredito="conforme", analisou_assinatura_contrato=False)})
    forte = base.model_copy(update={"analise_dossie": PERICIOU})
    assert decidir(forte).acao == "RECUPERAR"
    assert decidir(fraco).acao != "RECUPERAR"
