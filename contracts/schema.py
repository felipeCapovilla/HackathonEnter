"""
Contratos da política por segmentos, consumidos por src.policy.engine.decidir.

`make schema` exporta estes tipos para o protótipo visual. A API usa os
contratos HTTP de src.interface.backend.schemas, publicados em /openapi.json,
e grava a Recomendacao completa em cada análise.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

Acao = Literal["DEFENDER", "ACORDAR", "RECUPERAR"]
SubAssunto = Literal["Golpe", "Generico"]
VereditoDossie = Literal["conforme", "nao_conforme", "inconclusivo"]
Canal = Literal["digital", "correspondente", "agencia", "desconhecido"]


class ItemDossie(BaseModel):
    tipo: Literal["assinatura", "documento_identidade", "comprovante_residencia", "liveness"]
    resultado: Literal["ok", "falha", "inconclusivo"]
    indice: Optional[float] = Field(None, ge=0, le=1, allow_inf_nan=False, description="0-1 quando o laudo traz índice")


class AnaliseDossie(BaseModel):
    """Saída do agente do Felipe. Campos 1 e 2 são obrigatórios para o motor."""

    veredito: VereditoDossie
    analisou_assinatura_contrato: bool = Field(
        description="Se o dossiê periciou assinatura em instrumento contratual. "
        "É o que autoriza inferir que o CONTRATO existe (sinal de recuperabilidade)."
    )
    numero_contrato_referenciado: Optional[str] = None
    itens: list[ItemDossie] = Field(default_factory=list)
    confianca_extracao: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)


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


class PlanoRecuperacao(BaseModel):
    documento: Literal["contrato", "extrato", "comprovante_credito"]
    confianca: Literal["alta", "media", "baixa"]
    fundamento: str
    ganho_estimado: float
    p_perda_se_recuperado: float


class Honorario(BaseModel):
    """Um honorário do contrato banco–escritório que depende do desfecho."""

    tipo: Literal["fixo", "percentual_valor_causa", "percentual_condenacao"] = "fixo"
    valor: float = Field(default=0.0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _percentual_entre_zero_e_um(self) -> "Honorario":
        if self.tipo != "fixo" and self.valor > 1:
            raise ValueError("percentual deve estar entre 0 e 1 (0,10 = 10%)")
        return self

    def em_reais(self, valor_causa: float, condenacao_esperada: float) -> float:
        if self.tipo == "fixo":
            return self.valor
        base = valor_causa if self.tipo == "percentual_valor_causa" else condenacao_esperada
        return self.valor * base


class ParametrosContrato(BaseModel):
    """
    Termos do contrato vigente que mudam o custo entre acordar e defender.

    Mensalidade e valor fixo por caso novo não estão aqui de propósito: são
    pagos em qualquer desfecho e não mudam a decisão. Os defaults de tempo
    espelham T1 e T2 de src/policy/constants.py.
    """

    versao: str = "padrao"
    honorario_defesa_ganha: Honorario = Field(default_factory=Honorario)
    honorario_defesa_perdida: Honorario = Field(default_factory=Honorario)
    honorario_acordo: Honorario = Field(default_factory=Honorario)
    custo_mensal_tempo: float = Field(default=0.01, ge=0, le=0.10)
    duracao_meses: float = Field(default=24.0, ge=0, le=120)
    teto_alcada_fator: Optional[float] = Field(default=None, gt=0, le=1,
        description="Maior oferta autorizada pelo banco, como fração do valor da causa")
    concessao: float = Field(default=0.0, ge=0, le=1,
        description="Fração do espaço entre abertura e walk-away cedida no alvo da negociação")

    @property
    def fator_tempo(self) -> float:
        return 1 + self.custo_mensal_tempo * self.duracao_meses


class Recomendacao(BaseModel):
    """Saída do motor. É isto que o front renderiza e o log de auditoria grava."""

    numero_processo: str
    acao: Acao

    gate_defesa_disponivel: bool
    gate_motivo: str

    segmento: str
    p_perda: float
    fonte_probabilidade: Literal["tabela", "externa"] = "tabela"
    p_estrela: float
    custo_esperado_defesa: float

    acordo: Optional["FaixaNegociacao"] = None
    economia_no_alvo: float = 0.0
    recuperacao: Optional[PlanoRecuperacao] = None

    justificativa: list[str]
    alertas: list[str] = []
    premissas_usadas: list[str]
    versao_politica: str
    versao_contrato: str


# ─────────────────────────────────────────────────────────────────────────────
# Saída do motor de valor de acordo (src/policy/valor_acordo.py): a faixa vai
# da abertura (preço de mercado dos acordos) ao walk-away (custo esperado de
# litigar, limitado pela alçada do banco).
# ─────────────────────────────────────────────────────────────────────────────

DecisaoAcordo = Literal["ACORDO", "DEFESA"]


class FaixaNegociacao(BaseModel):
    """Os três números da correção de 13/09: onde abre, onde mira, onde levanta."""

    abertura: float = Field(description="Onde abre. 0,29 x valor da causa, âncora dos 280 acordos")
    alvo: float = Field(description="Onde quer fechar. Walk-away menos a margem de negociação")
    walk_away: float = Field(description="Onde levanta da mesa. Igual ao custo esperado de defesa")
    amplitude: float = Field(description="walk_away - abertura: o espaço real de negociação")
    negociavel: bool = Field(
        default=True,
        description="False quando a amplitude é pequena demais para negociar. Nesse caso "
        "o advogado recebe UM número — o walk-away — em vez de uma faixa, e `alvo` "
        "já vem igual a ele. A tela não deve mostrar intervalo.")


class VereditoAcordo(BaseModel):
    """
    Veredito econômico de um caso. É isto que a tela do advogado renderiza e
    o que o log de auditoria grava.

    `faixa` é None quando a decisão é DEFESA — não existe faixa boa nesse caso,
    e devolver uma seria convidar a oferta que a política acabou de rejeitar.
    """

    decisao: DecisaoAcordo
    p_nao_exito: float = Field(ge=0, le=1, description="P(derrota) usada na viabilidade")
    p_estrela: float = Field(
        ge=0, le=1,
        description="Limiar de indiferença DESTE caso, já com as custas dele. Derivado, nunca 0,5")
    e_condenacao: float = Field(description="E[condenação | derrota] = 0,74 x valor da causa")
    custo_defesa: float = Field(description="Custo esperado de litigar, incluindo sucumbência e custas")
    faixa: Optional[FaixaNegociacao] = None
    economia_no_alvo: float = Field(
        description="custo_defesa - alvo. Quanto o banco economiza fechando na meta. 0 em DEFESA")
    motivo: str = Field(description="Linguagem jurídica, para a tela do advogado")
    premissas_usadas: list[str] = Field(default_factory=list)
    policy_version: str


Recomendacao.model_rebuild()
