import os
from dotenv import load_dotenv
from pathlib import Path  # <-- Importante adicionar isso

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import List

from text_converter import text_converter

load_dotenv()

class ResumoDocie(BaseModel):
    parecer_geral: str = Field(description="Parecer geral do dossie dado pela empresa terceira, escreva APENAS conformidade ou não-conformidade")
    match_facial: float = Field(description="Match de compatibilidade facial no resultado do docie")
    # Corrigido "facial" para "da assinatura" na descrição abaixo para a IA não se confundir
    match_assinatura: float = Field(description="Match de compatibilidade da assinatura no resultado do docie") 
    documento_identidade: bool = Field(description="Indica se o documento de identidade apresentado era valido")
    comprovante_residencia: bool = Field(description="Indica se o comprovante de residencia apresentadoe era valido.")

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
strucutred_llm = llm.with_structured_output(ResumoDocie)

def analyze(input_document):
  
    text_converter(input_document)
    caminho_md = Path(input_document).with_suffix(".md")

    with open(caminho_md, "r", encoding="utf-8") as f:
        texto_markdown = f.read()

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Você é um extrator de dados. O documento em mardown vai ser lhe passado. Preencha os campos da resposta estruturada com base apenas no texto. Se a informação não existir, retorne 0 ou False."),
        ("human", "O texto do dossiê é: \n\n{documento}")
    ])

    chain = prompt | strucutred_llm
    
    result = chain.invoke({"documento": texto_markdown})
    
    return result.parecer_geral


if __name__ == "__main__":
    caminho_do_pdf = "/home/felipe-capovilla/Documents/HackatonEnter/docs/05_Dossie_Veritas.pdf"
    
    resultado_extraido = analyze(caminho_do_pdf)
    
    print(resultado_extraido)