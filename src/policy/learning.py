"""
Loop de aprendizado da taxa de aceitação (Beta-Binomial conjugado).

A base não tem UMA recusa registrada: os 280 acordos são todos fechados.
Então P3 começa como premissa e o produto existe, entre outras coisas, para
criar esse dado.

Beta-Binomial em vez de regressão porque:
  - funciona com 12 observações, que é o que existe por segmento no início
  - carrega incerteza nativamente (o intervalo encolhe visivelmente na tela)
  - não finge precisão que não tem
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from src.policy.constants import P3


@dataclass
class PosteriorAceitacao:
    """Crença sobre a taxa de aceitação de um segmento, atualizada por desfecho."""

    aceitos: int = 0
    recusados: int = 0
    peso_prior: float = 10.0  # equivale a 10 observações fictícias na premissa P3

    @property
    def alfa(self) -> float:
        return P3.valor * self.peso_prior + self.aceitos

    @property
    def beta(self) -> float:
        return (1 - P3.valor) * self.peso_prior + self.recusados

    @property
    def media(self) -> float:
        return self.alfa / (self.alfa + self.beta)

    @property
    def n(self) -> int:
        return self.aceitos + self.recusados

    def intervalo(self, z: float = 1.96) -> tuple[float, float]:
        """Intervalo aproximado (normal sobre a Beta). Encolhe conforme n cresce."""
        a, b = self.alfa, self.beta
        var = (a * b) / ((a + b) ** 2 * (a + b + 1))
        sd = math.sqrt(var)
        return max(0.0, self.media - z * sd), min(1.0, self.media + z * sd)

    def observar(self, aceito: bool) -> None:
        if aceito:
            self.aceitos += 1
        else:
            self.recusados += 1

    @property
    def fonte(self) -> str:
        """Rastreabilidade: a tela precisa dizer se o número é observado ou assumido."""
        if self.n == 0:
            return "assumida_P3"
        return "observada" if self.n >= 30 else "mista"


@dataclass
class RegistroAceitacao:
    """Um posterior por segmento — é a política aprendendo onde ela opera."""

    por_segmento: dict[str, PosteriorAceitacao] = field(default_factory=dict)

    def posterior(self, segmento: str) -> PosteriorAceitacao:
        return self.por_segmento.setdefault(segmento, PosteriorAceitacao())

    def registrar(self, segmento: str, aceito: bool) -> PosteriorAceitacao:
        p = self.posterior(segmento)
        p.observar(aceito)
        return p
