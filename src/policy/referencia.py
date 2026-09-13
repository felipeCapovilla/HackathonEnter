"""
Referências OBSERVADAS na base de 60 mil sentenças (artefatos/insights_base_historica.json).

- custo_parecidos: quanto processos com os mesmos documentos, a mesma alegação e a mesma região
  custaram de fato, em média, como fração da causa. É a base da economia que o painel mostra.
- chance_aceite: a curva dos 280 acordos da base. A chance de o autor aceitar uma oferta é a fração
  dos acordos que fecharam até aquele % da causa (limitada entre 5% e 85%).
- valor_recomendado: dentro da faixa de mercado (25% a 35% da causa), a oferta que maximiza chance de aceite ×
  economia até o limite. Fora da faixa a conta às vezes preferiria pagar mais para subir a aceitação, mas o
  advogado levaria à mesa um valor acima do que os acordos costumam fechar.
"""
from __future__ import annotations

import bisect
import json
from functools import lru_cache
from pathlib import Path

from . import table

ARTEFATO = Path(__file__).resolve().parents[2] / "artefatos" / "insights_base_historica.json"
MIN_PARECIDOS = 30
ACEITE_MIN, ACEITE_MAX = 0.05, 0.85


@lru_cache(maxsize=1)
def _base() -> dict:
    return json.loads(ARTEFATO.read_text(encoding="utf-8"))


def acordos() -> dict:
    return _base()["acordos"]


def chave(contrato: bool, extrato: bool, comprovante: bool, sub_assunto: str, grupo: str = "*") -> str:
    return f"C{int(bool(contrato))}E{int(bool(extrato))}CC{int(bool(comprovante))}|{sub_assunto}|{grupo}"


def custo_parecidos(contrato: bool, extrato: bool, comprovante: bool, sub_assunto: str, uf: str | None,
                    valor_causa: float) -> dict | None:
    """Custo médio real de processos parecidos para esta causa; sem região quando o recorte é pequeno."""
    tabela = _base()["custo_parecidos"]
    for grupo in ((table.cluster_uf(uf), "*") if uf else ("*",)):
        item = tabela.get(chave(contrato, extrato, comprovante, sub_assunto, grupo))
        if item and item["n"] >= MIN_PARECIDOS:
            return {"valor": round(item["custo_sobre_causa"] * valor_causa, 2), "n": item["n"],
                    "custo_sobre_causa": item["custo_sobre_causa"], "com_regiao": grupo != "*"}
    return None


def _cdf(razao: float) -> float:
    quantis = acordos()["quantis"]
    if razao <= quantis[0]:
        return 0.0
    if razao >= quantis[-1]:
        return 1.0
    i = bisect.bisect_right(quantis, razao) - 1
    largura = quantis[i + 1] - quantis[i]
    fracao = (razao - quantis[i]) / largura if largura else 1.0
    return (i + fracao) / (len(quantis) - 1)


def chance_aceite(valor: float, valor_causa: float, fator: float = 1.0) -> float:
    if valor_causa <= 0:
        return ACEITE_MIN
    return min(ACEITE_MAX, max(ACEITE_MIN, _cdf(valor / valor_causa) * fator))


def faixa_mercado(valor_causa: float) -> tuple[float, float]:
    return round(acordos()["p25"] * valor_causa, 2), round(acordos()["p75"] * valor_causa, 2)


def posicao_no_mercado(valor: float, valor_causa: float) -> float:
    """Fração dos acordos da base que fecharam por menos (em % da causa) do que este valor."""
    return _cdf(valor / valor_causa) if valor_causa > 0 else 0.0


def valor_recomendado(valor_causa: float, limite: float, fator: float = 1.0) -> tuple[float, float] | None:
    """Oferta dentro da faixa de mercado que maximiza chance de aceite × (limite − oferta), arredondada a R$ 10."""
    if valor_causa <= 0 or limite <= 0:
        return None
    quantis = acordos()["quantis"]
    melhor = None
    razao, teto = acordos()["p25"], acordos()["p75"]
    while razao <= teto + 1e-9:
        oferta = round(razao * valor_causa / 10) * 10
        if 0 < oferta <= limite:
            chance = chance_aceite(oferta, valor_causa, fator)
            ganho = chance * (limite - oferta)
            if melhor is None or ganho > melhor[0] + 1e-9:
                melhor = (ganho, oferta, chance)
        razao += 0.005
    if melhor is None:
        oferta = round(min(limite, acordos()["p25"] * valor_causa) / 10) * 10
        return (oferta, chance_aceite(oferta, valor_causa, fator)) if oferta > 0 else None
    return float(melhor[1]), round(melhor[2], 4)
