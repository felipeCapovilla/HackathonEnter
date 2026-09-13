"""
MODELO 3 - Gate de elegibilidade da defesa.

NÃO é estatística: é ônus da prova. O art. 373, II do CPC exige que o banco
comprove a contratação apresentando o instrumento contratual. Sem contrato E
sem extrato essa prova não existe — e a base confirma: 2,7% de vitória em
6.493 casos (10,8% do volume, 34,7% do custo total).

O gate NÃO proíbe defender. Ele tira a defesa do menu padrão e exige
justificativa explícita, que vira dado de aderência onde está o dinheiro.
"""
from __future__ import annotations

from dataclasses import dataclass

from contracts.schema import CaseFeatures


@dataclass(frozen=True)
class ResultadoGate:
    defesa_disponivel: bool
    motivo: str
    exige_justificativa: bool
    contrato_invalidado: bool = False
    alerta: str | None = None


def avaliar_gate(c: CaseFeatures) -> ResultadoGate:
    """
    Dossiê NÃO CONFORME não pula a economia: ele INVALIDA o contrato como
    prova. Se o perito pago pelo próprio banco diz que a assinatura não
    confere, o contrato que o banco tem não sustenta o ônus do art. 373, II —
    então o caso é reprecificado como se não houvesse contrato, e o cálculo
    de valor esperado decide normalmente.

    Forçar acordo aqui seria pagar valor certo para evitar risco pequeno:
    num caso com os 6 subsídios, o custo esperado da defesa é ~R$ 225 e o
    acordo sairia a ~R$ 4.500.
    """
    nao_conforme = bool(c.analise_dossie and c.analise_dossie.veredito == "nao_conforme")

    contrato_vale = c.contrato and not nao_conforme
    alerta = None
    if nao_conforme and c.contrato:
        alerta = (
            "Atenção: a empresa enviou o contrato, mas o próprio dossiê diz que a assinatura "
            "não confere. O contrato não foi usado como prova e não deve ser levado ao processo."
        )

    if not contrato_vale and not c.extrato:
        return ResultadoGate(
            defesa_disponivel=False,
            motivo=(
                "Sem contrato válido e sem extrato, a empresa não consegue provar que o empréstimo "
                "existiu (art. 373, II do CPC): em casos assim, a defesa vence só 3 em cada 100."
            ),
            exige_justificativa=True,
            contrato_invalidado=nao_conforme and c.contrato,
            alerta=alerta,
        )

    return ResultadoGate(
        defesa_disponivel=True,
        motivo=("A empresa tem a prova mínima da contratação (contrato ou extrato)." if not nao_conforme else
                "A empresa tem a prova mínima da contratação, mas o contrato foi desconsiderado porque a assinatura não confere."),
        exige_justificativa=False,
        contrato_invalidado=nao_conforme and c.contrato,
        alerta=alerta,
    )


def contrato_efetivo(c: CaseFeatures) -> bool:
    """Contrato que o juiz aceitaria: presente E não desmentido pelo próprio dossiê."""
    nao_conforme = bool(c.analise_dossie and c.analise_dossie.veredito == "nao_conforme")
    return c.contrato and not nao_conforme
