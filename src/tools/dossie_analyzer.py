import os
from dotenv import load_dotenv
from pathlib import Path  

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

# Presumindo que text_converter já está importado
from .text_converter import text_converter

load_dotenv()

class ResumoDocie(BaseModel):
    docie_existe: bool = Field(description="Indica se o docie existe no registro de arquivos")
    parecer_geral: str = Field(description="Parecer geral do dossie dado pela empresa terceira, escreva APENAS conformidade ou não-conformidade")
    match_facial: float = Field(description="Match de compatibilidade facial no resultado do docie")
    match_assinatura: float = Field(description="Match de compatibilidade da assinatura no resultado do docie") 
    documento_identidade: bool = Field(description="Indica se o documento de identidade apresentado era valido")
    comprovante_residencia: bool = Field(description="Indica se o comprovante de residencia apresentadoe era valido.")

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
strucutred_llm = llm.with_structured_output(ResumoDocie)

def analyze(input_document):
    caminho_pdf = Path(input_document)

    # 1. Checagem nativa do Python: Se o arquivo não existir, aborta a chamada da LLM
    if not caminho_pdf.exists():
        print(f"[-] Arquivo não encontrado: {caminho_pdf}")
        # Retorna o modelo Pydantic preenchido com False e valores zerados
        return ResumoDocie(
            docie_existe=False,
            parecer_geral="N/A",
            match_facial=0.0,
            match_assinatura=0.0,
            documento_identidade=False,
            comprovante_residencia=False
        )
  
    # 2. Se existir, segue o fluxo de conversão
    text_converter(str(caminho_pdf))
    caminho_md = caminho_pdf.with_suffix(".md")

    with open(caminho_md, "r", encoding="utf-8") as f:
        texto_markdown = f.read()

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Você é um extrator de dados. O documento em mardown vai ser lhe passado. Preencha os campos da resposta estruturada com base apenas no texto. Como o documento foi fornecido, preencha docie_existe como True. Se a informação não existir, retorne 0 ou False."),
        ("human", "O texto do dossiê é: \n\n{documento}")
    ])

    chain = prompt | strucutred_llm
    result = chain.invoke({"documento": texto_markdown})
    
    # Retorna o objeto completo para você ter acesso a todos os campos
    return result


if __name__ == "__main__":
    caminho_do_pdf = "/home/felipe-capovilla/Documents/HackatonEnter/docs/dossie.pdf"
    
    resultado_extraido = analyze(caminho_do_pdf)
    
    print(f"Dossiê Existe? {resultado_extraido.docie_existe}")
    print(f"Parecer Geral: {resultado_extraido.parecer_geral}")