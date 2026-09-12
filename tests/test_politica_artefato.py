"""O artefato da política é gerado da base, e o código lê dele."""
from pathlib import Path

import pytest

from src.policy import constants, table
from src.policy.artefato import carregar

ROOT = Path(__file__).resolve().parents[1]


def test_artefato_cobre_os_16_segmentos_e_as_26_ufs():
    artefato = carregar()
    assert len(table.TABELA) == 16
    assert len(artefato["uf"]["clusters"]) == 26
    assert set(artefato["uf"]["offset_logit"]) == {"alto", "medio", "baixo"}


def test_premissas_medidas_vem_do_artefato_e_nao_do_codigo():
    artefato = carregar()
    assert constants.P1.valor == artefato["condenacao_sobre_causa_se_perde"]["media"]
    assert constants.P2_ALVO.valor == artefato["acordo_sobre_causa"]["mediana"]
    assert constants.P2_PISO.valor <= constants.P2_ALVO.valor <= constants.P2_MAXIMO.valor <= constants.P2_TETO.valor


def test_artefato_versionado_bate_com_a_base_quando_ela_esta_disponivel():
    resultados, subsidios = ROOT / "data" / "resultados.csv", ROOT / "data" / "subsidios.csv"
    if not (resultados.is_file() and subsidios.is_file()):
        pytest.skip("base histórica não está em data/ (gitignored)")
    import importlib.util

    spec = importlib.util.spec_from_file_location("gerador", ROOT / "scripts" / "gerar_tabela_politica.py")
    gerador = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gerador)
    regenerado = gerador.gerar(gerador.linhas_csv(resultados, subsidios))
    versionado = {k: v for k, v in carregar().items() if k != "gerado_em"}
    assert regenerado == versionado, "rode scripts/gerar_tabela_politica.py e commite o artefato"
