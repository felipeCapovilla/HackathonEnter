"""
Saldo ESTIMADO das divergências — interno, sem tela.

Quando o advogado não segue a recomendação (ou fecha acima do limite), guardamos quanto o caminho
recomendado custaria, em valor esperado, e quanto o escolhido custou de fato:

    caminho recomendado = acordo: chance de aceite × oferta + chance de recusa × custo esperado de defender
                          defesa: custo esperado de defender
    saldo = caminho recomendado − gasto real   (positivo: a divergência economizou)

É estimativa, por isso não entra no painel. É a entrada do human in the loop: padrões por motivo e tipo
de caso viram sugestão de ajuste da política para o gestor aprovar.
"""
from __future__ import annotations

from src.policy.referencia import chance_aceite


def custo_caminho_recomendado(recomendacao: str, policy_output: dict, valor_causa: float) -> float | None:
    custo_defesa = policy_output.get("custo_esperado_defesa")
    if custo_defesa is None:
        return None
    if recomendacao == "DEFESA":
        return float(custo_defesa)
    if recomendacao == "ACORDO":
        oferta = policy_output.get("valor_recomendado") or (policy_output.get("acordo") or {}).get("abertura")
        if not oferta or valor_causa <= 0:
            return None
        chance = chance_aceite(oferta, valor_causa)
        return round(chance * oferta + (1 - chance) * float(custo_defesa), 2)
    return None
