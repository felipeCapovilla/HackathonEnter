"""
Números da política em linguagem de quem usa a ferramenta.

Frequência ("6 em cada 10") em vez de probabilidade ("P(derrota) 64,7%"), e o
caso descrito pelos documentos que ele tem, não pela chave interna da tabela.
"""
from __future__ import annotations


def frequencia(p: float) -> str:
    """Nos extremos, em cada 100: "3 em cada 10" esconderia que 0,027 é quase nunca."""
    p = min(1.0, max(0.0, p))
    if p < 0.1 or p > 0.9:
        return f"{round(p * 100)} em cada 100"
    return f"{round(p * 10)} em cada 10"


def nivel_de_risco(p: float) -> str:
    return "baixa" if p < 0.25 else "média" if p < 0.5 else "alta" if p < 0.75 else "muito alta"


def descrever_caso(contrato: bool, extrato: bool, comprovante: bool, sub_assunto: str) -> str:
    marca = lambda tem, nome: f"{'com' if tem else 'sem'} {nome}"
    return ", ".join([marca(contrato, "contrato"), marca(extrato, "extrato"), marca(comprovante, "comprovante de crédito"),
                      "alegação de golpe" if sub_assunto == "Golpe" else "sem alegação de golpe"])
