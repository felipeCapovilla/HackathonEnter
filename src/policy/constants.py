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
P2_MAXIMO = Premissa("P2c", "Máximo aceitável (P75 dos acordos)", _ACORDO["p75"],
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
# POLÍTICA VIGENTE DE VALOR DE ACORDO  (documento de 13/09 + correção)
#
# Substitui P1/P2_* quando `engine.py` migrar. Até lá os dois conjuntos
# coexistem: `pricing.calcular_faixa` continua na banda ancorada nos 280
# acordos, e `valor_acordo.avaliar_acordo` usa os números abaixo.
#
# DIVERGÊNCIA CONHECIDA: P1 = 0,72 (derivado pelo time como 2/3 x 0,63 +
# 1/3 x 0,90) vs RATIO_CONDENACAO = 0,74 (razão mediana medida na base).
# São estimativas do mesmo número por caminhos diferentes. `valor_acordo`
# usa 0,74 porque é a medição direta e é o que o documento apresenta.
# ─────────────────────────────────────────────────────────────────────────────

RATIO_CONDENACAO = Premissa(
    "P8", "E[condenação | derrota] como fração do valor da causa", 0.74,
    "OBSERVADO: razão mediana condenação/valor da causa, correlação 0,749, base 60k")

RATIO_ABERTURA = Premissa(
    "P2c", "Fator da oferta de abertura", 0.29,
    "OBSERVADO: mediana dos 280 acordos reais (R$ 4.362 / R$ 15.026)")

# SUCUMBÊNCIA FORA DO CÁLCULO — decisão de 13/09.
#
# A política anterior multiplicava o custo de defesa por (1 + 0,15) a título de
# honorários sucumbenciais. Não há honorário nenhum na base: o 0,15 era praxe do
# art. 85 §2º do CPC (faixa de 10%-20%), ou seja, premissa pura sobre o meio da
# faixa. Foi retirado.
#
# CONSEQUÊNCIA, e é grande: o P* sem custas sobe de 34,1% para 39,2%, porque o
# custo de litigar encolhe 15%. O bucket de 4 subsídios (P = 35,9%) passa a ficar
# ABAIXO do limiar puro de 39,2%, e sai da política.
#
# P6 continua existindo e vale 0,15: `engine.py` ainda o usa na política antiga.
# Não é esquecimento — é o escopo desta branch.

MARGEM = Premissa(
    "P10", "Meta de negociação: desconto perseguido sobre o walk-away", 0.20,
    "ASSUMIDO: partida 20-25%, calibrar pela taxa de aceitação observada. "
    "NÃO entra na viabilidade — ver correção de 13/09")

AMPLITUDE_MIN_REL = Premissa(
    "P11", "Amplitude mínima para a faixa ser negociável, como fração da abertura", 0.05,
    "ASSUMIDO: abaixo disso não há espaço de negociação e o motor entrega um "
    "valor único (o walk-away) em vez de uma faixa. NÃO afeta a decisão")

# CUSTAS PROCESSUAIS FORA DO CÁLCULO — decisão de 13/09.
#
# Uma premissa anterior (`P9`) fixava R$ 600 por processo. Não havia embasamento
# nenhum: não há custas na base, e o número era invenção pura decidindo o desfecho
# de 15.719 processos. Retirada.
#
# `avaliar_acordo(..., custas_uf=...)` continua aceitando o valor: quando o banco
# fornecer as custas reais por UF, é só passar. O default é 0,0 — e 0,0 também é
# premissa, só que uma que não finge conhecimento que não temos.

TODAS_VALOR_ACORDO = [RATIO_CONDENACAO, RATIO_ABERTURA,
                      MARGEM, AMPLITUDE_MIN_REL]

POLICY_VERSION = "acordo-2026.09.13-v1"

# Limiar de indiferença SEM custas. DERIVADO das premissas acima — nunca
# literal. Se alguma constante mudar, ele muda junto. A armadilha nº 1 do
# projeto é escrever `if p > 0.5`: o limiar é econômico, não estatístico.
P_ESTRELA_SEM_CUSTAS = RATIO_ABERTURA.valor / RATIO_CONDENACAO.valor

assert abs(P_ESTRELA_SEM_CUSTAS - 0.3919) < 5e-4, (
    f"P* derivado ({P_ESTRELA_SEM_CUSTAS:.4f}) divergiu dos 39,2% da linha "
    "'sem custas nem sucumbência' do documento. Alguma premissa mudou sem o "
    "documento ser atualizado."
)
