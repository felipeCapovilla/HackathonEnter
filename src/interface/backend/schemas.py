"""Typed HTTP contracts for cases, documents, analyses and decisions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field
from contracts.dossie import DossieReport
from contracts.schema import ParametrosContrato


class SourceParty(StrEnum):
    BANCO = "BANCO"
    ADVOGADO_EXTERNO = "ADVOGADO_EXTERNO"


class UserRole(StrEnum):
    BANCO = "BANCO"
    ADVOGADO_EXTERNO = "ADVOGADO_EXTERNO"
    ADMIN_GLOBAL = "ADMIN_GLOBAL"


class DocumentType(StrEnum):
    AUTOS = "AUTOS"
    CONTRATO = "CONTRATO"
    EXTRATO = "EXTRATO"
    COMPROVANTE_CREDITO = "COMPROVANTE_CREDITO"
    DOSSIE = "DOSSIE"
    DEMONSTRATIVO_DIVIDA = "DEMONSTRATIVO_DIVIDA"
    LAUDO_REFERENCIADO = "LAUDO_REFERENCIADO"
    OUTRO = "OUTRO"


class DocumentTypeStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"
    MISMATCH = "MISMATCH"
    USER_CONFIRMED = "USER_CONFIRMED"
    REMOVED = "REMOVED"


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class DocumentaryStatus(StrEnum):
    SUSTENTADA_DOCUMENTALMENTE = "SUSTENTADA_DOCUMENTALMENTE"
    SUSTENTADA_COM_RESSALVAS = "SUSTENTADA_COM_RESSALVAS"
    INFORMACAO_INSUFICIENTE = "INFORMACAO_INSUFICIENTE"
    CONFLITO_MATERIAL = "CONFLITO_MATERIAL"
    ERRO_DE_ENTRADA = "ERRO_DE_ENTRADA"
    FALHA_TECNICA = "FALHA_TECNICA"
    ANALISE_PRELIMINAR = "ANALISE_PRELIMINAR"
    CONFIRMACAO_NECESSARIA = "CONFIRMACAO_NECESSARIA"


class DocumentRequestStatus(StrEnum):
    REQUESTED = "REQUESTED"
    SUBMITTED = "SUBMITTED"
    DECLARED_UNAVAILABLE = "DECLARED_UNAVAILABLE"
    CANCELLED = "CANCELLED"


class CaseCreate(BaseModel):
    case_number: str = Field(min_length=3, max_length=80)
    uf: str = Field(min_length=2, max_length=2)
    value_of_claim: float | None = Field(default=None, ge=0)
    sub_subject: str | None = Field(default=None, max_length=120)
    dossie_status: str = "AUSENTE"
    assigned_lawyer_id: str | None = None


class CaseAssignment(BaseModel):
    assigned_lawyer_id: str | None = None


class CaseRecord(CaseCreate):
    id: str
    created_at: datetime


class DocumentRecord(BaseModel):
    id: str
    case_id: str
    original_filename: str
    declared_type: DocumentType
    detected_type: DocumentType | None = None
    type_status: DocumentTypeStatus
    source_party: SourceParty
    status: DocumentStatus
    page_count: int = 0
    pages_extracted: int = 0
    sha256: str
    quality_flags: list[str] = Field(default_factory=list)
    created_at: datetime


class TypeConfirmation(BaseModel):
    action: str = Field(pattern="^(RECLASSIFY|CONTINUE_WITH_RESERVATION|REMOVE)$")
    document_type: DocumentType | None = None
    reason: str = Field(min_length=3, max_length=1000)


class DossieAnalysisRecord(BaseModel):
    id: str
    document_id: str
    status: Literal["COMPLETED", "FAILED"]
    result: DossieReport | None = None
    error_code: str | None = None
    model: str
    created_at: datetime
    evidencias_total: int = Field(default=0, ge=0)
    evidencias_carregadas: bool = True


class FeatureProvenance(BaseModel):
    feature: str
    value: int
    document_ids: list[str] = Field(default_factory=list)
    derivation_rule: str


class AnalysisRecord(BaseModel):
    id: str
    case_id: str
    recommendation: str
    decision_code: str
    policy_source: str
    agreement_probability: float | None = None
    documentary_status: DocumentaryStatus
    reasons: list[str]
    feature_vector: dict[str, int]
    feature_provenance: list[FeatureProvenance]
    pricing: dict[str, object] | None = None
    limitations: list[str] = Field(default_factory=list)
    policy_output: dict[str, object] | None = None
    policy_version: str | None = None
    contract_version: str | None = None
    created_at: datetime


class DocumentRequestCreate(BaseModel):
    document_type: DocumentType
    hypothesis_key: str = Field(min_length=3, max_length=120)
    reason: str = Field(min_length=3, max_length=1000)


class DocumentRequestRecord(DocumentRequestCreate):
    id: str
    case_id: str
    status: DocumentRequestStatus
    created_at: datetime
    responded_at: datetime | None = None


class DocumentRequestResponse(BaseModel):
    status: DocumentRequestStatus = Field(
        pattern="^(DECLARED_UNAVAILABLE|CANCELLED)$"
    )
    reason: str = Field(min_length=3, max_length=1000)


class LawyerDecisionCreate(BaseModel):
    action: str = Field(pattern="^(ACORDO|DEFESA|RECUPERAR)$")
    reason: str | None = Field(default=None, max_length=2000)
    proposed_value: float | None = Field(default=None, ge=0)


class MonitoringSummary(BaseModel):
    total_analyses: int
    total_lawyer_decisions: int
    adherence_rate: float | None
    recommendations: dict[str, int]
    documentary_statuses: dict[str, int]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class BankCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class BankRecord(BankCreate):
    id: str
    created_at: datetime


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=15, max_length=128)
    role: UserRole
    bank_id: str | None = None


class UserRecord(BaseModel):
    id: str
    name: str
    email: str
    role: UserRole
    bank_id: str | None
    bank_name: str | None = None
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=15, max_length=128)


class SessionUser(UserRecord):
    csrf_token: str


class BankContractRecord(BaseModel):
    id: str | None = None
    bank_id: str
    version: int = Field(description="0 = contrato padrão, nenhuma versão cadastrada")
    parameters: ParametrosContrato
    created_by_user_id: str | None = None
    created_at: datetime | None = None


class ContractPreviewResult(BaseModel):
    economia: float
    economia_percentual: float
    custo_sem_politica: float
    custo_com_politica: float
    acoes: dict[str, int]


class ContractPreview(BaseModel):
    casos: int
    pago_historico: float
    contrato_vigente: ContractPreviewResult
    contrato_proposto: ContractPreviewResult
    decisoes_alteradas: int
    premissas: str
