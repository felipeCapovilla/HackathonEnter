"""
FONTE ÚNICA DE VERDADE dos tipos trocados entre política, API e front.

Regra do time: nenhum dict solto atravessa fronteira de módulo. Se um campo
não está aqui, ele não existe. Todo mundo importa daqui — inclusive o front,
via o JSON Schema gerado por `make schema`.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Acao = Literal["DEFENDER", "ACORDAR", "RECUPERAR"]
SubAssunto = Literal["Golpe", "Generico"]
VereditoDossie = Literal["conforme", "nao_conforme", "inconclusivo"]
Canal = Literal["digital", "correspondente", "agencia", "desconhecido"]


class ItemDossie(BaseModel):
    tipo: Literal["assinatura", "documento_identidade", "comprovante_residencia", "liveness"]
    resultado: Literal["ok", "falha", "inconclusivo"]
    indice: Optional[float] = Field(None, description="0-1 quando o laudo traz índice")


class AnaliseDossie(BaseModel):
    """Saída do agente do Felipe. Campos 1 e 2 são obrigatórios para o motor."""

    veredito: VereditoDossie
    analisou_assinatura_contrato: bool = Field(
        description="Se o dossiê periciou assinatura em instrumento contratual. "
        "É o que autoriza inferir que o CONTRATO existe (sinal de recuperabilidade)."
    )
    numero_contrato_referenciado: Optional[str] = None
    itens: list[ItemDossie] = []
    confianca_extracao: float = 1.0


class CaseFeatures(BaseModel):
    """Entrada do motor de decisão."""

    numero_processo: str
    uf: str
    sub_assunto: SubAssunto
    valor_causa: float

    # presença de subsídios (a base de 60k só tem isto)
    contrato: bool
    extrato: bool
    comprovante_credito: bool
    dossie: bool
    demonstrativo: bool
    laudo: bool

    # sinais extraídos dos PDFs por IA — None = não analisado
    analise_dossie: Optional[AnaliseDossie] = None
    canal_contratacao: Optional[Canal] = None
    contradicoes: list[str] = []


class FaixaAcordo(BaseModel):
    abertura: float
    alvo: float
    maximo_aceitavel: float
    teto_absoluto: float


class PlanoRecuperacao(BaseModel):
    documento: Literal["contrato", "extrato", "comprovante_credito"]
    confianca: Literal["alta", "media", "baixa"]
    fundamento: str
    ganho_estimado: float
    p_perda_se_recuperado: float


class Recomendacao(BaseModel):
    """Saída do motor. É isto que o front renderiza e o log de auditoria grava."""

    numero_processo: str
    acao: Acao

    gate_defesa_disponivel: bool
    gate_motivo: str

    segmento: str
    p_perda: float
    custo_esperado_defesa: float

    acordo: Optional[FaixaAcordo] = None
    recuperacao: Optional[PlanoRecuperacao] = None

    justificativa: list[str]
    alertas: list[str] = []
    premissas_usadas: list[str]
