"""Evidence contracts for extraction, separate from policy decisions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from contracts.schema import AnaliseDossie, ItemDossie, VereditoDossie


class DossieEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    campo: str = Field(min_length=1, max_length=80)
    valor: str = Field(min_length=1, max_length=120)
    pagina: int = Field(ge=1)
    trecho: str = Field(min_length=8, max_length=1600)

    @field_validator("trecho")
    @classmethod
    def meaningful_quote(cls, value: str) -> str:
        if len("".join(value.split())) < 8:
            raise ValueError("A evidência deve conter pelo menos oito caracteres não brancos.")
        return value


class DossieChunkExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    veredito: VereditoDossie
    analisou_assinatura_contrato: bool | None
    numero_contrato_referenciado: str | None = Field(max_length=120)
    itens: list[ItemDossie] = Field(max_length=4)
    evidencias: list[DossieEvidence] = Field(max_length=20)


class DossieReport(BaseModel):
    docie_existe: bool
    analise: AnaliseDossie
    evidencias: list[DossieEvidence] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    paginas_processadas: int = Field(default=0, ge=0)
    trechos_processados: int = Field(default=0, ge=0)
    completo: bool = False
    assinatura_contrato_status: Literal["sim", "nao", "desconhecido", "conflitante"] = "desconhecido"
