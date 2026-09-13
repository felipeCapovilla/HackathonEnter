"""Typed HTTP contracts for cases, documents, analyses and decisions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator
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
    # Classificação automática do tipo no upload (sem seleção manual do banco).
    AI_CONFIRMED = "AI_CONFIRMED"
    AI_REJECTED = "AI_REJECTED"


class DecisionOutcome(StrEnum):
    """Como o processo terminou de verdade. É o que separa êxito de aderência."""

    ACORDO_ACEITO = "ACORDO_ACEITO"
    ACORDO_RECUSADO = "ACORDO_RECUSADO"
    SENTENCA_FAVORAVEL = "SENTENCA_FAVORAVEL"
    SENTENCA_DESFAVORAVEL = "SENTENCA_DESFAVORAVEL"


#: Desfechos que contam como êxito do banco no numerador da taxa.
FAVORABLE_OUTCOMES = frozenset({DecisionOutcome.ACORDO_ACEITO, DecisionOutcome.SENTENCA_FAVORAVEL})


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


class UnavailabilityReason(StrEnum):
    """Por que o banco não entregou o documento. Alimenta as recomendações de infraestrutura."""
    NAO_LOCALIZADO = "NAO_LOCALIZADO"
    CONTRATO_FISICO_NAO_DIGITALIZADO = "CONTRATO_FISICO_NAO_DIGITALIZADO"
    CORRESPONDENTE_NAO_ENVIOU = "CORRESPONDENTE_NAO_ENVIOU"
    FORA_DO_PRAZO_DE_GUARDA = "FORA_DO_PRAZO_DE_GUARDA"
    SISTEMA_SEM_EXPORTACAO = "SISTEMA_SEM_EXPORTACAO"
    OPERACAO_INEXISTENTE = "OPERACAO_INEXISTENTE"
    OUTRO = "OUTRO"


class NegotiationStatus(StrEnum):
    ACEITO = "ACEITO"
    RECUSADO = "RECUSADO"
    CONTRAPROPOSTA = "CONTRAPROPOSTA"
    SEM_RESPOSTA = "SEM_RESPOSTA"


class JudicialResult(StrEnum):
    EXITO = "EXITO"
    NAO_EXITO = "NAO_EXITO"


class EngagementEventType(StrEnum):
    CASE_OPENED = "CASE_OPENED"
    DOCUMENT_OPENED = "DOCUMENT_OPENED"
    ANALYSIS_RUN = "ANALYSIS_RUN"
    DECISION_REGISTERED = "DECISION_REGISTERED"
    OUTCOME_REGISTERED = "OUTCOME_REGISTERED"
    ACTIVE_TIME = "ACTIVE_TIME"


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
    # Derivados da última decisão: `cases` não tem coluna de status.
    active: bool = True
    decided: bool = False
    outcome: DecisionOutcome | None = None
    document_count: int = 0


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
    # "AI" quando o tipo veio da classificação automática no upload; "USER" quando o banco declarou.
    type_source: Literal["USER", "AI"] = "USER"
    ai_type_reason: str | None = None


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
    unavailability_reason: UnavailabilityReason | None = None
    unavailability_reason_source: Literal["INFORMADO", "IA", "REGRA"] | None = None


class DocumentRequestResponse(BaseModel):
    status: DocumentRequestStatus = Field(
        pattern="^(DECLARED_UNAVAILABLE|CANCELLED)$"
    )
    reason: str = Field(min_length=3, max_length=1000)
    unavailability_reason: UnavailabilityReason | None = Field(
        default=None, description="Obrigatório no painel; se ausente, o texto livre é classificado (IA ou regra).")


class LawyerDecisionCreate(BaseModel):
    action: str = Field(pattern="^(ACORDO|DEFESA|RECUPERAR)$")
    reason: str | None = Field(default=None, max_length=2000)
    proposed_value: float | None = Field(default=None, ge=0)


class NegotiationOutcomeCreate(BaseModel):
    """Passo 05 do fluxo: o advogado reporta o resultado da negociação do acordo."""
    status: NegotiationStatus
    offered_value: float | None = Field(default=None, ge=0)
    counter_value: float | None = Field(default=None, ge=0)
    closed_value: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _valores_coerentes(self) -> "NegotiationOutcomeCreate":
        if self.status == NegotiationStatus.ACEITO and self.closed_value is None:
            raise ValueError("Acordo aceito exige o valor fechado.")
        if self.status == NegotiationStatus.CONTRAPROPOSTA and self.counter_value is None:
            raise ValueError("Contraproposta exige o valor pedido pela parte autora.")
        if self.status != NegotiationStatus.ACEITO and self.closed_value is not None:
            raise ValueError("Só acordo aceito tem valor fechado.")
        return self


class NegotiationOutcomeRecord(NegotiationOutcomeCreate):
    id: str
    case_id: str
    decision_id: str | None = None
    lawyer_id: str | None = None
    created_at: datetime


class JudicialOutcomeCreate(BaseModel):
    """Desfecho do processo defendido; chega meses depois da decisão."""
    result: JudicialResult
    condemnation_value: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _exito_sem_condenacao(self) -> "JudicialOutcomeCreate":
        if self.result == JudicialResult.EXITO and self.condemnation_value > 0:
            raise ValueError("Processo com êxito não tem valor de condenação.")
        return self


class JudicialOutcomeRecord(JudicialOutcomeCreate):
    id: str
    case_id: str
    lawyer_id: str | None = None
    created_at: datetime


class EngagementEventCreate(BaseModel):
    event_type: Literal["DOCUMENT_OPENED", "ACTIVE_TIME"]
    document_id: str | None = Field(default=None, max_length=80)
    active_seconds: int = Field(default=0, ge=0, le=300, description="Tempo ativo desde o último aviso; no máximo 5 min")


class LawyerDecisionOutcomeCreate(BaseModel):
    outcome: DecisionOutcome
    outcome_note: str | None = Field(default=None, max_length=2000)


class LawyerPerformance(BaseModel):
    """Painel do próprio advogado: êxito real e aderência à política, separados."""

    total_cases: int
    active_cases: int
    closed_cases: int
    decisions: int
    outcomes_recorded: int
    pending_outcome: int
    success_rate: float | None = Field(
        default=None, description="Desfechos favoráveis / desfechos registrados. None sem desfecho."
    )
    adherence_rate: float | None = Field(
        default=None, description="Decisões que seguiram a recomendação / decisões comparáveis."
    )
    outcomes: dict[str, int]
    actions: dict[str, int]


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
    law_firm_id: str | None = None
    is_manager: bool = False


class UserRecord(BaseModel):
    id: str
    name: str
    email: str
    role: UserRole
    bank_id: str | None
    bank_name: str | None = None
    law_firm_id: str | None = None
    law_firm_name: str | None = None
    is_manager: bool = False
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=15, max_length=128)
    law_firm_id: str | None = None
    is_manager: bool | None = None


class ChangePasswordRequest(BaseModel):
    """Autoatendimento: o próprio usuário logado troca a própria senha."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=15, max_length=128)


class ResetPasswordRequest(BaseModel):
    """Admin ou gestor do banco define a senha de um terceiro."""

    new_password: str = Field(min_length=15, max_length=128)


class AuditEventRecord(BaseModel):
    id: str
    actor_user_id: str | None
    actor_name: str | None = None
    action: str
    entity_type: str
    entity_id: str
    case_id: str | None = None
    reason: str | None = None
    created_at: datetime


class AuditChainStatus(BaseModel):
    valid: bool
    checked: int
    broken_at_id: str | None = None


class LawFirmCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class LawFirmRecord(LawFirmCreate):
    id: str
    created_at: datetime


class SessionUser(UserRecord):
    csrf_token: str


class BankContractRecord(BaseModel):
    id: str | None = None
    bank_id: str
    version: int = Field(description="0 = contrato padrão, nenhuma versão cadastrada")
    parameters: ParametrosContrato
    law_firm_id: str | None = Field(default=None, description="None = contrato padrão do banco")
    inherited_from_bank: bool = Field(default=False, description="Escritório sem contrato próprio: vale o do banco")
    justification: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime | None = None


class BankContractUpdate(BaseModel):
    """Q40: o gestor do banco só grava uma versão nova com justificativa."""
    parametros: ParametrosContrato
    justificativa: str = Field(min_length=10, max_length=1000)


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
