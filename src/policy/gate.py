"""
MODELO 3 - Gate de elegibilidade da defesa.

NÃO é estatística: é ônus da prova. O art. 373, II do CPC exige que o banco
comprove a contratação apresentando o instrumento contratual. Sem contrato E
sem extrato, essa prova não existe — e a base confirma: 2,7% de vitória em
6.493 casos (10,8% do volume, 34,7% do custo total).

O gate NÃO proíbe defender. Ele tira a defesa do menu padrão e exige
justificativa explícita — que vira dado de aderência exatamente onde está
o dinheiro.
"""
from __future__ import annotations

from dataclasses import dataclass

from contracts.schema import CaseFeatures


@dataclass(frozen=True)
class ResultadoGate:
    defesa_disponivel: bool
    motivo: str
    exige_justificativa: bool


def avaliar_gate(c: CaseFeatures) -> ResultadoGate:
    if not c.contrato and not c.extrato:
        return ResultadoGate(
            defesa_disponivel=False,
            motivo=(
                "Sem contrato e sem extrato o banco não satisfaz o ônus probatório "
                "do art. 373, II do CPC. Segmento com 2,7% de êxito histórico."
            ),
            exige_justificativa=True,
        )

    if c.analise_dossie and c.analise_dossie.veredito == "nao_conforme":
        return ResultadoGate(
            defesa_disponivel=False,
            motivo=(
                "Dossiê do próprio banco aponta NÃO CONFORMIDADE. Prova contra si; "
                "não deve ser juntada aos autos e indica composição."
            ),
            exige_justificativa=True,
        )

    return ResultadoGate(True, "Prova mínima presente.", False)
