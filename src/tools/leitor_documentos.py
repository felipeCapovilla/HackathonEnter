"""
Leitura de documento por IA, no momento em que ele entra no processo.

A extração do PDF (pypdf) devolve texto cru; quem opera precisa saber o que o
documento é, o que diz em duas frases e os campos que a busca e a conferência
usam (número do contrato, valores, parte autora). PDF escaneado, sem texto,
vai como arquivo para o modelo ler a imagem.

A IA não decide nada aqui: o tipo lido só vira alerta quando diverge do tipo
informado, e o valor da causa lido só vira aviso quando diverge do cadastro.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

MODELO_PADRAO = "gpt-4o-mini"
LIMITE_TEXTO = 24_000
TEXTO_MINIMO = 400  # abaixo disso o PDF é tratado como escaneado e vai como arquivo

TipoLido = Literal["AUTOS", "CONTRATO", "EXTRATO", "COMPROVANTE_CREDITO", "DOSSIE",
                   "DEMONSTRATIVO_DIVIDA", "LAUDO_REFERENCIADO", "OUTRO"]

PROMPT = """Você lê documentos de processos em que um cliente diz não reconhecer um empréstimo.
Use só o que está escrito no documento; se um campo não aparece, devolva null.
- tipo_documento: AUTOS (petição inicial ou peças do processo), CONTRATO, EXTRATO (extrato de conta),
  COMPROVANTE_CREDITO (comprovante de crédito/TED/registro no BACEN), DOSSIE (verificação de assinatura e documentos),
  DEMONSTRATIVO_DIVIDA, LAUDO_REFERENCIADO ou OUTRO.
- resumo: no máximo 2 frases, em português simples, sem jargão.
- numero_contrato: número do contrato ou da operação de crédito.
- valor_principal: valor do empréstimo ou do crédito liberado, em reais.
- data_referencia: data principal do documento no formato AAAA-MM-DD.
- nome_parte_autora: nome de quem processa (ou do titular, fora dos autos).
- uf e valor_causa: só nos autos ("Dá-se à causa o valor de...", comarca).
- alega_golpe: só nos autos; true se o autor diz ter sido vítima de golpe ou fraude.
- pontos_de_atencao: até 5 fatos que o advogado precisa conferir (datas, assinatura, valores, conta de destino).
Nunca copie CPF, RG ou número de conta completos."""


class LeituraDocumento(BaseModel):
    tipo_documento: TipoLido
    resumo: str
    numero_contrato: str | None = None
    valor_principal: float | None = None
    data_referencia: str | None = None
    nome_parte_autora: str | None = None
    uf: str | None = None
    valor_causa: float | None = None
    alega_golpe: bool | None = None
    pontos_de_atencao: list[str] = []


class LeituraIndisponivel(RuntimeError):
    """Sem chave, sem SDK ou falha do provedor: o documento segue válido, só sem leitura."""


def ler_documento(caminho: Path, texto: str, tipo_declarado: str) -> LeituraDocumento:
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise LeituraIndisponivel("Configure OPENAI_API_KEY no servidor para a leitura por IA.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LeituraIndisponivel("Instale o pacote openai para a leitura por IA.") from exc
    conteudo: list[dict] = [{"type": "input_text", "text": f"Tipo informado por quem enviou: {tipo_declarado}."}]
    if len(texto.strip()) < TEXTO_MINIMO and caminho.suffix.lower() == ".pdf" and caminho.exists():
        dados = base64.b64encode(caminho.read_bytes()).decode()
        conteudo.append({"type": "input_file", "filename": caminho.name, "file_data": f"data:application/pdf;base64,{dados}"})
    else:
        conteudo.append({"type": "input_text", "text": texto[:LIMITE_TEXTO]})
    modelo = os.getenv("ENTERAGREE_LEITURA_MODEL", MODELO_PADRAO).strip() or MODELO_PADRAO
    try:
        with OpenAI(timeout=60.0, max_retries=1) as client:
            resposta = client.responses.parse(
                model=modelo,
                input=[{"role": "system", "content": PROMPT}, {"role": "user", "content": conteudo}],
                text_format=LeituraDocumento,
                max_output_tokens=1500,
                store=False,
            )
    except Exception as exc:  # noqa: BLE001 - qualquer falha do provedor vira "sem leitura"
        raise LeituraIndisponivel("Não foi possível ler o documento com IA agora; tente novamente.") from exc
    if resposta.output_parsed is None:
        raise LeituraIndisponivel("A IA não devolveu uma leitura estruturada.")
    leitura = resposta.output_parsed
    return leitura.model_copy(update={"pontos_de_atencao": leitura.pontos_de_atencao[:5], "resumo": leitura.resumo[:600]})
