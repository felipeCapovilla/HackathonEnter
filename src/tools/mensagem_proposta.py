"""
Mensagem de proposta de acordo para o advogado da parte autora.

O valor, o prazo e o número do processo vêm do motor e do cadastro; a IA só melhora
a redação. Se a versão da IA perder o valor no caminho, vale o modelo fixo.
"""
from __future__ import annotations

import os

MODELO = """Prezado(a) colega,

Em referência ao processo nº {numero}, {empresa} propõe acordo no valor de R$ {valor}, para encerrar integralmente a ação, sem reconhecimento de responsabilidade.

O pagamento será feito em até 15 dias após a homologação judicial do acordo, arcando cada parte com os honorários de seu advogado.

Pedimos retorno em até {prazo} dias úteis.

Atenciosamente,
{advogado}"""


def _brl(valor: float) -> str:
    return f"{valor:,.2f}".translate(str.maketrans({",": ".", ".": ","}))


def redigir_mensagem(*, numero: str, empresa: str, advogado: str, valor: float, prazo_dias: int = 5) -> tuple[str, str]:
    base = MODELO.format(numero=numero, empresa=empresa, valor=_brl(valor), prazo=prazo_dias, advogado=advogado or "")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return base, "MODELO"
    try:
        from openai import OpenAI

        with OpenAI(timeout=30.0, max_retries=1) as client:
            resposta = client.responses.create(
                model=os.getenv("ENTERAGREE_LEITURA_MODEL", "gpt-4o-mini"),
                input=[
                    {"role": "system", "content": (
                        "Reescreva a proposta de acordo abaixo em português formal e cordial, em até 120 palavras. "
                        "Mantenha exatamente o valor, o prazo, o número do processo e os nomes. "
                        "Não admita culpa, não invente fatos e não acrescente condições.")},
                    {"role": "user", "content": base},
                ],
                max_output_tokens=500,
                store=False,
            )
        texto = (resposta.output_text or "").strip()
    except Exception:  # noqa: BLE001 - sem IA, a mensagem fixa já serve
        return base, "MODELO"
    if _brl(valor) not in texto or numero not in texto:
        return base, "MODELO"
    return texto, "IA"
