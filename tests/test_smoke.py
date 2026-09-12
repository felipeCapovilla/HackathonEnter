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


def test_os_dois_casos_nao_podem_dar_igual():
    a, b = decidir(CASO_01), decidir(CASO_02)
    assert a.p_perda != b.p_perda, "features chegaram zeradas ou constantes"
    assert a.p_perda < 0.10, f"Caso 01 deveria ser defesa clara, veio {a.p_perda:.1%}"
    assert b.p_perda > 0.90, f"Caso 02 deveria ser perda quase certa, veio {b.p_perda:.1%}"


def test_caso_01_defende():
    assert decidir(CASO_01).acao == "DEFENDER"


def test_caso_02_nao_defende():
    r = decidir(CASO_02)
    assert r.acao in ("ACORDAR", "RECUPERAR")
    assert r.gate_defesa_disponivel is False


def test_gate_fecha_sem_contrato_e_sem_extrato():
    assert decidir(CASO_02).gate_defesa_disponivel is False


def test_dossie_nao_conforme_forca_acordo():
    c = CASO_01.model_copy(update={"analise_dossie": AnaliseDossie(
        veredito="nao_conforme", analisou_assinatura_contrato=True)})
    assert decidir(c).acao == "ACORDAR"


def test_terceira_via_quando_dossie_prova_que_contrato_existe():
    """Sem contrato, mas o dossiê periciou a assinatura nele => recuperável."""
    c = CASO_02.model_copy(update={
        "dossie": True,
        "analise_dossie": AnaliseDossie(veredito="conforme", analisou_assinatura_contrato=True),
    })
    r = decidir(c)
    assert r.acao == "RECUPERAR"
    assert r.recuperacao.documento == "contrato"
    assert r.recuperacao.confianca == "alta"
    assert r.recuperacao.ganho_estimado > 0
