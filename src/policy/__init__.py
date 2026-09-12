"""Política de acordos: decisão, preço, tabela de segmentos, backtest e prévia de contrato."""

from .engine import decidir
from .valor_acordo import avaliar_acordo, custo_esperado_defesa, p_estrela

__all__ = ["avaliar_acordo", "custo_esperado_defesa", "decidir", "p_estrela"]
