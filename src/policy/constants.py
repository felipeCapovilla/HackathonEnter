"""
PREMISSAS NUMERADAS. Toda constante do modelo mora aqui e em nenhum outro lugar.

Se um número aparece num slide, ele vem daqui. Se muda aqui, muda no slide.
`fonte` diz o que é medido e o que é assumido — vai para a tela e para a
apresentação.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Premissa:
    id: str
    descricao: str
    valor: float
    fonte: str


P1 = Premissa("P1", "E[condenação | derrota] como fração do valor da causa", 0.72,
              "DERIVADO: 2/3 x 0,63 (parcial) + 1/3 x 0,90 (procedência), base 60k")
P2_ALVO = Premissa("P2", "Fator alvo do acordo", 0.30,
                   "OBSERVADO: mediana dos 280 acordos reais (média 0,298)")
P2_PISO = Premissa("P2a", "Piso da banda de acordo", 0.24, "OBSERVADO: P25 dos 280 acordos")
P2_TETO = Premissa("P2b", "Teto da banda de acordo", 0.40, "OBSERVADO: P90 dos 280 acordos")
P3 = Premissa("P3", "Probabilidade de o autor aceitar o acordo", 0.40,
              "ASSUMIDO: sem dado de recusa na base. Parametrizável (slider 0,2-0,8)")
P4 = Premissa("P4", "Recuperabilidade com sinal forte (dossiê/laudo presente)", 0.70,
              "EVIDÊNCIA POSITIVA: 17.194 casos em que o documento comprovadamente existiu")
P5 = Premissa("P5", "Recuperabilidade sem sinal forte", 0.25, "ASSUMIDO")
P6 = Premissa("P6", "Honorários sucumbenciais sobre a condenação", 0.15,
              "ASSUMIDO: praxe 10-20%, art. 85 CPC")
# P7 (custo do escritório externo por processo) NÃO é assumido de propósito.
# O banco tem esse número; inventá-lo distorce toda a política.

TODAS = [P1, P2_ALVO, P2_PISO, P2_TETO, P3, P4, P5, P6]

GATE_P_VITORIA_OBSERVADA = 0.027  # C0/E0: 2,7% de vitória em 6.493 casos
