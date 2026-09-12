"""Shared constants for the settlement policy modules."""

from dataclasses import dataclass
from pathlib import Path

from .artefato import carregar


REPO_ROOT = Path(__file__).resolve().parents[2]

SUBSIDIOS = (
    "Contrato",
    "Extrato",
    "Comprovante de crédito",
    "Dossiê",
    "Demonstrativo de evolução da dívida",
    "Laudo referenciado",
)

SUBSIDIOS_CRITICOS = (
    "Contrato",
    "Extrato",
    "Comprovante de crédito",
)

SUBSIDY_FIELD_MAP = {
    "Contrato": "contrato",
    "Extrato": "extrato",
    "Comprovante de crédito": "comprovante_credito",
    "Dossiê": "dossie",
    "Demonstrativo de evolução da dívida": "demonstrativo_divida",
    "Laudo referenciado": "laudo_referenciado",
}

HIGH_RISK_UFS = frozenset({"AM", "AP"})
MEDIUM_RISK_UFS = frozenset({
    "GO",
    "RS",
    "BA",
    "RJ",
    "ES",
    "DF",
    "AL",
    "SP",
    "PE",
})

CLUSTER_UF = {
    **{uf: "ALTO" for uf in HIGH_RISK_UFS},
    **{uf: "MEDIO" for uf in MEDIUM_RISK_UFS},
}

DEFAULT_UF_CLUSTER = "BAIXO"

FEATURE_COLUMNS = (
    *SUBSIDIOS,
    "is_golpe",
    "uf_alto",
    "uf_medio",
)

DOSSIE_STATUS_CONFORME = "CONFORME"
DOSSIE_STATUS_NAO_CONFORME = "NAO_CONFORME"
DOSSIE_STATUS_AUSENTE = "AUSENTE"
DOSSIE_STATUS_INCOMPLETO = "INCOMPLETO"

VALID_DOSSIE_STATUSES = frozenset(
    {
        DOSSIE_STATUS_CONFORME,
        DOSSIE_STATUS_NAO_CONFORME,
        DOSSIE_STATUS_AUSENTE,
        DOSSIE_STATUS_INCOMPLETO,
    }
)

DEFAULT_MODEL_THRESHOLD = 0.50
MODEL_GRAY_ZONE = (0.35, 0.65)

BASE_AGREEMENT_FACTOR = 0.30
OPENING_FLOOR_FACTOR = 0.24
HISTORICAL_MAX_ACCEPTABLE_FACTOR = 0.35
ABSOLUTE_AGREEMENT_CEILING_FACTOR = 0.40


@dataclass(frozen=True)
class Premissa:
    id: str
    descricao: str
    valor: float
    fonte: str


_BASE = carregar()
_PERDA = _BASE["condenacao_sobre_causa_se_perde"]
_ACORDO = _BASE["acordo_sobre_causa"]

P1 = Premissa("P1", "Condenação média como fração do valor da causa, dado que perdeu", _PERDA["media"],
              f"MEDIDO: {_PERDA['n']} derrotas; procedência {_PERDA['procedencia']:.2f}, "
              f"parcial {_PERDA['parcial_procedencia']:.2f}")
P2_PISO = Premissa("P2a", "Abertura da negociação (P25 dos acordos)", _ACORDO["p25"],
                   f"MEDIDO: {_ACORDO['n']} acordos da base")
P2_ALVO = Premissa("P2", "Alvo do acordo (mediana dos acordos)", _ACORDO["mediana"],
                   f"MEDIDO: {_ACORDO['n']} acordos da base")
P2_MAXIMO = Premissa("P2d", "Máximo aceitável (P75 dos acordos)", _ACORDO["p75"],
                     f"MEDIDO: {_ACORDO['n']} acordos da base")
P2_TETO = Premissa("P2b", "Teto absoluto (P90 dos acordos)", _ACORDO["p90"],
                   f"MEDIDO: {_ACORDO['n']} acordos da base")
P3 = Premissa("P3", "Probabilidade de o autor aceitar o acordo", 0.40,
              "ASSUMIDO: sem dado de recusa na base. Parametrizável (slider 0,2-0,8)")
P4 = Premissa("P4", "Recuperabilidade com sinal forte (dossiê/laudo presente)", 0.70,
              "EVIDÊNCIA POSITIVA: 17.194 casos em que o documento comprovadamente existiu")
P5 = Premissa("P5", "Recuperabilidade sem sinal forte", 0.25, "ASSUMIDO")
P6 = Premissa("P6", "Honorários sucumbenciais sobre a condenação", 0.15,
              "ASSUMIDO: praxe 10-20%, art. 85 CPC")
# P7 (custo do escritório externo por processo) NÃO é assumido de propósito.
# O banco tem esse número; inventá-lo distorce toda a política.

TODAS = [P1, P2_PISO, P2_ALVO, P2_MAXIMO, P2_TETO, P3, P4, P5, P6]

GATE_P_VITORIA_OBSERVADA = 0.027  # C0/E0: 2,7% de vitória em 6.493 casos


# ─────────────────────────────────────────────────────────────────────────────
# POLÍTICA DE VALOR DE ACORDO (motor de preço em valor_acordo.py)
#
# A condenação esperada usa a MÉDIA medida (P1), não a mediana. Custo esperado
# é média por definição: com 0,7108 a soma prevista nas derrotas reproduz o
# total pago (R$ 192,86M previstos x R$ 192,98M reais); a mediana 0,74
# superestimava em R$ 9,6M. Nenhuma decisão muda entre as duas — o limiar cai
# numa região da tabela sem segmentos — mas o custo e a economia sim.
# ─────────────────────────────────────────────────────────────────────────────

RATIO_CONDENACAO = Premissa(
    "P1", "Condenação esperada como fração do valor da causa, dado que perdeu", P1.valor, P1.fonte)

RATIO_ABERTURA = Premissa(
    "P2", "Fator da oferta de abertura (mediana dos acordos)", P2_ALVO.valor, P2_ALVO.fonte)

# Sucumbência e custas ficam fora do custo por default: não existem na base.
# Custas reais por UF entram por parâmetro em avaliar_acordo(custas_uf=...).

CONCESSAO = Premissa(
    "P10", "Fração do excedente (walk-away - abertura) cedida no alvo da negociação", 0.0,
    "MEDIDO: nos 280 acordos reais o valor fechado não sobe com o risco do caso "
    "(correlação -0,105; 29-32% da causa em todas as faixas de risco). O mercado fecha "
    "na abertura; mirar perto do walk-away pagaria o excedente ao autor. Não entra na viabilidade")

AMPLITUDE_MIN_REL = Premissa(
    "P11", "Amplitude mínima para a faixa ser negociável, como fração da abertura", 0.05,
    "ASSUMIDO: abaixo disso o motor entrega um valor único (o walk-away) em vez de "
    "uma faixa. Regra de apresentação: não afeta a decisão")

CUSTO_MENSAL_TEMPO = Premissa(
    "T1", "Custo mensal de manter o processo aberto (juros de mora e capital provisionado)", 0.01,
    "ASSUMIDO: 1% a.m. Decisões idênticas para qualquer duração entre 12 e 36 meses no backtest")

DURACAO_MESES = Premissa(
    "T2", "Duração esperada do processo até a condenação, em meses", 24.0,
    "ASSUMIDO: varia muito por juízo; 24 meses é o meio da faixa em que a decisão é robusta")

TODAS_VALOR_ACORDO = [RATIO_CONDENACAO, RATIO_ABERTURA, CONCESSAO, AMPLITUDE_MIN_REL,
                      CUSTO_MENSAL_TEMPO, DURACAO_MESES]

POLICY_VERSION = "politica-2026.09.12-v2"

# Limiar de indiferença sem custas, honorários nem tempo. DERIVADO, nunca
# literal: se uma premissa mudar, ele muda junto. O limiar é econômico, não 0,5.
P_ESTRELA_SEM_CUSTAS = RATIO_ABERTURA.valor / RATIO_CONDENACAO.valor
assert 0.0 < P_ESTRELA_SEM_CUSTAS < 0.5, f"P* sem custas fora do esperado: {P_ESTRELA_SEM_CUSTAS:.4f}"
