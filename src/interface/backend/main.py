"""HTTP API for the EnterAgree evidence-backed settlement policy."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import Settings, get_settings
from .auth import COOKIE_NAME, hash_password, normalize_email, require_case_access, require_role, require_user, session_expiry, verify_password
from .database import connection_for, initialize_database
from src.utils.document_service import DocumentService
from src.utils.dossie_service import DossieService, DossieUnavailableError
from src.utils.document_type_validator import validate_document_type
from .monitoring import build_monitoring_summary
from .bank_insights import build_bank_insights
from src.utils.motivo_indisponibilidade import classificar_motivo
from src.tools.leitor_documentos import LeituraIndisponivel, ler_documento
from src.tools.mensagem_proposta import redigir_mensagem
from src.policy.service import PolicyService
from contracts.schema import ParametrosContrato
from .repository import Repository
from .schemas import (
    AnalysisRecord,
    BankContractRecord,
    BankContractUpdate,
    EngagementEventCreate,
    EngagementEventType,
    JudicialOutcomeCreate,
    JudicialOutcomeRecord,
    LawFirmCreate,
    MensagemPropostaCreate,
    LawFirmRecord,
    NegotiationOutcomeCreate,
    NegotiationOutcomeRecord,
    ContractPreview,
    CaseCreate,
    CaseAssignment,
    CaseRecord,
    DocumentRecord,
    DocumentRequestCreate,
    DocumentRequestRecord,
    DocumentRequestResponse,
    DocumentRequestStatus,
    DocumentType,
    DocumentTypeStatus,
    DossieAnalysisRecord,
    FAVORABLE_OUTCOMES,
    LawyerDecisionCreate,
    LawyerDecisionOutcomeCreate,
    LawyerPerformance,
    MonitoringSummary,
    SourceParty,
    UserRole,
    LoginRequest,
    SessionUser,
    BankCreate,
    BankRecord,
    UserCreate,
    UserRecord,
    UserUpdate,
    TypeConfirmation,
    ChangePasswordRequest,
    ResetPasswordRequest,
    AuditEventRecord,
    AuditChainStatus,
)


logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(app_settings.database_path)
        app.state.repository = Repository(app_settings.database_path)
        app.state.dossie = DossieService(app.state.repository)

        def analisar_dossie_ao_extrair(document_id: str) -> None:
            """Q37: o dossiê é analisado assim que a extração termina, para a política já usá-lo."""
            if not app_settings.dossie_auto_analysis or not os.getenv("OPENAI_API_KEY", "").strip():
                return
            document = app.state.repository.get_document_internal(document_id)
            if document is None or document["declared_type"] != DocumentType.DOSSIE.value:
                return
            try:
                app.state.dossie.analyze(document_id)
            except (LookupError, ValueError, DossieUnavailableError) as exc:
                logger.info("Análise automática do dossiê %s não realizada: %s", document_id, exc)

        def ler_com_ia(document_id: str) -> dict | None:
            """Leitura por IA do documento; falha vira registro FAILED, nunca erro para quem enviou."""
            repository_ = app.state.repository
            document = repository_.get_document_internal(document_id)
            if document is None or document.get("deleted_at"):
                return None
            modelo = os.getenv("ENTERAGREE_LEITURA_MODEL", "gpt-4o-mini")
            texto = repository_.get_document_text_sample(document_id, 24_000)
            try:
                leitura = app.state.leitor(Path(document["file_path"]), texto, document["declared_type"])
            except LeituraIndisponivel as exc:
                return repository_.save_document_reading(document_id, modelo, "FAILED", None, str(exc))
            return repository_.save_document_reading(document_id, modelo, "COMPLETED", leitura.model_dump(mode="json"), None)

        def avaliar_quando_documentos_prontos(document_id: str) -> None:
            """O advogado abre o processo com a recomendação pronta: avalia quando o último documento termina."""
            repository_ = app.state.repository
            document = repository_.get_document_internal(document_id)
            if document is None:
                return
            case_id = document["case_id"]
            if any(item["status"] in {"UPLOADED", "EXTRACTING"} for item in repository_.list_documents(case_id)):
                return
            if repository_.case_flow(case_id)["codigo"] in {"AGUARDANDO_AVALIACAO", "REAVALIAR"}:
                try:
                    app.state.policy.evaluate(case_id)
                except Exception:  # noqa: BLE001 - a avaliação automática não pode derrubar o envio
                    logger.exception("Avaliação automática do processo %s falhou", case_id)

        def ao_extrair(document_id: str) -> None:
            analisar_dossie_ao_extrair(document_id)
            # Upload sem tipo declarado já leu com IA para classificar (document_service.py).
            # Reler aqui seria uma segunda chamada paga pelo mesmo conteúdo.
            if app.state.repository.get_document_reading(document_id) is not None:
                return
            if app_settings.leitura_ia and os.getenv("OPENAI_API_KEY", "").strip():
                try:
                    ler_com_ia(document_id)
                except Exception:  # noqa: BLE001 - a leitura é complemento; o documento já está processado
                    logger.exception("Leitura por IA do documento %s falhou", document_id)
            avaliar_quando_documentos_prontos(document_id)

        app.state.leitor = ler_documento
        app.state.ler_com_ia = ler_com_ia
        app.state.documents = DocumentService(
            app.state.repository, app_settings, on_extraction_completed=ao_extrair
        )
        def contrato_do_banco(bank_id: str | None, law_firm_id: str | None = None) -> ParametrosContrato:
            record = app.state.repository.resolve_bank_contract(bank_id, law_firm_id) if bank_id else None
            if record is None:
                return ParametrosContrato()
            return ParametrosContrato.model_validate({**record["parameters"], "versao": f"{bank_id}-v{record['version']}"})

        app.state.contract_provider = contrato_do_banco
        app.state.policy = PolicyService(app.state.repository, contract_provider=contrato_do_banco)
        yield

    app = FastAPI(title="EnterAgree API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def repository() -> Repository:
        return app.state.repository

    def document_service() -> DocumentService:
        return app.state.documents

    def current_user(request: Request) -> dict:
        if not app_settings.auth_required:
            return {"id": "system", "role": "SYSTEM", "bank_id": "banco-unicamp", "name": "Sistema"}
        return require_user(request)

    def require_case(case_id: str, request: Request) -> dict:
        return require_case_access(repository(), case_id, current_user(request))

    def track(user: dict, case_id: str, event_type: EngagementEventType, document_id: str | None = None) -> None:
        """Engajamento é medido só para o advogado externo, e nunca derruba a requisição."""
        if user.get("role") != UserRole.ADVOGADO_EXTERNO.value:
            return
        try:
            repository().record_engagement(case_id, user["id"], event_type.value, document_id)
        except Exception:  # noqa: BLE001 - telemetria não pode impedir o trabalho do advogado
            logger.exception("Falha ao registrar engajamento %s do caso %s", event_type, case_id)

    def audit(user: dict | None, action: str, entity_type: str, entity_id: str,
              case_id: str | None = None, reason: str | None = None) -> None:
        """Auditoria nunca derruba a requisição principal: é rastro, não regra de negócio."""
        actor_id = user.get("id") if user and user.get("role") != "SYSTEM" else None
        try:
            repository().record_audit_event(
                actor_user_id=actor_id, action=action, entity_type=entity_type,
                entity_id=entity_id, case_id=case_id, reason=reason,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao registrar evento de auditoria %s/%s", action, entity_type)

    def require_manager(user: dict) -> dict:
        require_role(user, UserRole.BANCO)
        if user["role"] != "SYSTEM" and not user.get("is_manager"):
            raise HTTPException(403, "Somente o gestor da empresa altera o contrato.")
        return user

    def require_open_case(case_id: str, acao: str) -> None:
        """
        Barra escrita em processo encerrado.

        Depois do desfecho o caso é histórico: trocar documento, responsável ou
        decisão reescreveria a prova em que a recomendação já emitida se apoiou.
        O guarda mora aqui, e não só na tela, porque a API é chamável direto.
        """
        if repository().case_stage(case_id) == "ENCERRADO":
            raise HTTPException(409, f"Processo encerrado: não é possível {acao}.")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/login", response_model=SessionUser)
    def login(payload: LoginRequest, response: Response) -> dict:
        email = normalize_email(payload.email)
        user = repository().get_user_by_email(email)
        if user is None or not user["is_active"] or not verify_password(payload.password, user["password_hash"]):
            audit(None, "LOGIN_FAILED", "USER", (user or {}).get("id") or email)
            raise HTTPException(401, "E-mail ou senha inválidos.")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        repository().create_session(hashlib.sha256(token.encode()).hexdigest(), user["id"], csrf, session_expiry())
        response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", secure=False, max_age=8 * 3600)
        response.headers["Cache-Control"] = "no-store"
        audit(user, "LOGIN", "USER", user["id"])
        return {**user, "csrf_token": csrf}

    @app.get("/api/auth/me", response_model=SessionUser | None)
    def me(request: Request, response: Response) -> dict | None:
        response.headers["Cache-Control"] = "no-store"
        try:
            return current_user(request)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                return None
            raise

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response) -> Response:
        token = request.cookies.get(COOKIE_NAME)
        if token:
            user = repository().get_session_user(hashlib.sha256(token.encode()).hexdigest())
            repository().revoke_session(hashlib.sha256(token.encode()).hexdigest())
            if user:
                audit(user, "LOGOUT", "USER", user["id"])
        response.status_code = status.HTTP_204_NO_CONTENT
        response.headers["Cache-Control"] = "no-store"
        response.delete_cookie(COOKIE_NAME)
        return response

    @app.post("/api/auth/change-password", status_code=204)
    def change_password(payload: ChangePasswordRequest, request: Request) -> Response:
        """Autoatendimento: troca a própria senha. Revoga todas as sessões, a atual incluída — login de novo."""
        user = current_user(request)
        if user["role"] == "SYSTEM":
            raise HTTPException(403, "Autenticação necessária para trocar a senha.")
        record = repository().get_user(user["id"])
        if record is None or not verify_password(payload.current_password, record["password_hash"]):
            raise HTTPException(401, "Senha atual incorreta.")
        repository().update_user(user["id"], {"password_hash": hash_password(payload.new_password)})
        audit(user, "PASSWORD_CHANGED", "USER", user["id"])
        return Response(status_code=204)

    @app.get("/api/admin/banks", response_model=list[BankRecord])
    def admin_banks(request: Request) -> list[dict]:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        return repository().list_banks()

    @app.post("/api/admin/banks", response_model=BankRecord, status_code=201)
    def create_bank(payload: BankCreate, request: Request) -> dict:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        try:
            return repository().create_bank(payload.name)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/admin/law-firms", response_model=list[LawFirmRecord])
    def admin_law_firms(request: Request) -> list[dict]:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        return repository().list_law_firms()

    @app.post("/api/admin/law-firms", response_model=LawFirmRecord, status_code=201)
    def create_law_firm(payload: LawFirmCreate, request: Request) -> dict:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        try:
            return repository().create_law_firm(payload.name)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/admin/users", response_model=list[UserRecord])
    def admin_users(request: Request) -> list[dict]:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        return repository().list_users()

    @app.post("/api/admin/users", response_model=UserRecord, status_code=201)
    def create_user(payload: UserCreate, request: Request) -> dict:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        if (payload.role == UserRole.ADMIN_GLOBAL) != (payload.bank_id is None):
            raise HTTPException(422, "Administradores não possuem banco; usuários operacionais exigem banco.")
        if payload.bank_id and repository().get_bank(payload.bank_id) is None:
            raise HTTPException(422, "Banco não encontrado.")
        if payload.law_firm_id and (payload.role != UserRole.ADVOGADO_EXTERNO or repository().get_law_firm(payload.law_firm_id) is None):
            raise HTTPException(422, "Escritório só se aplica a advogado externo e precisa existir.")
        if payload.is_manager and payload.role != UserRole.BANCO:
            raise HTTPException(422, "Somente usuários do banco podem ser gestores.")
        admin = current_user(request)
        try:
            created = repository().create_user({"id": str(secrets.token_hex(16)), "name": payload.name.strip(), "email": normalize_email(payload.email), "password_hash": hash_password(payload.password), "role": payload.role.value, "bank_id": payload.bank_id, "law_firm_id": payload.law_firm_id, "is_manager": payload.is_manager, "is_active": True, "created_at": datetime.now(UTC).isoformat()})
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        audit(admin, "USER_CREATED", "USER", created["id"], reason=f"role={created['role']}")
        return created

    @app.patch("/api/admin/users/{user_id}", response_model=UserRecord)
    def update_user(user_id: str, payload: UserUpdate, request: Request) -> dict:
        admin = require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        changes = payload.model_dump(exclude_none=True)
        if "password" in changes:
            changes["password_hash"] = hash_password(changes.pop("password"))
            action = "PASSWORD_RESET"
        elif "is_active" in changes:
            action = "USER_ACTIVATED" if changes["is_active"] else "USER_DEACTIVATED"
        else:
            action = "USER_UPDATED"
        user = repository().update_user(user_id, changes)
        if user is None:
            raise HTTPException(404, "Usuário não encontrado.")
        audit(admin, action, "USER", user_id)
        return user

    @app.patch("/api/admin/users/{user_id}/password", status_code=204)
    def admin_reset_password(user_id: str, payload: ResetPasswordRequest, request: Request) -> Response:
        admin = require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        updated = repository().update_user(user_id, {"password_hash": hash_password(payload.new_password)})
        if updated is None:
            raise HTTPException(404, "Usuário não encontrado.")
        audit(admin, "PASSWORD_RESET", "USER", user_id)
        return Response(status_code=204)

    @app.get("/api/admin/audit-events", response_model=list[AuditEventRecord])
    def admin_audit_events(
        request: Request, limit: int = 100, before_rowid: int | None = None,
        action: str | None = None, entity_type: str | None = None, case_id: str | None = None,
    ) -> list[dict]:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        return repository().list_audit_events(
            limit=min(max(limit, 1), 500), before_rowid=before_rowid,
            action=action, entity_type=entity_type, case_id=case_id,
        )

    @app.get("/api/admin/audit-events/verify", response_model=AuditChainStatus)
    def admin_verify_audit_chain(request: Request) -> dict:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        return repository().verify_audit_chain()

    def contract_record(bank_id: str, law_firm_id: str | None = None) -> dict:
        record = repository().get_active_bank_contract(bank_id, law_firm_id)
        inherited = False
        if record is None and law_firm_id:
            record, inherited = repository().get_active_bank_contract(bank_id), True
        if record is None:
            return {"bank_id": bank_id, "version": 0, "parameters": ParametrosContrato().model_dump(),
                    "law_firm_id": law_firm_id, "inherited_from_bank": bool(law_firm_id)}
        return {**record, "law_firm_id": law_firm_id, "inherited_from_bank": inherited,
                "parameters": {**record["parameters"], "versao": f"{bank_id}-v{record['version']}"}}

    def require_firm_of_bank(bank_id: str, law_firm_id: str | None) -> None:
        if law_firm_id and law_firm_id not in {firm["id"] for firm in repository().list_law_firms(bank_id)}:
            raise HTTPException(404, "Escritório não atua para esta empresa.")

    def contract_preview(bank_id: str, law_firm_id: str | None, payload: ParametrosContrato) -> dict:
        from src.policy.preview import simular
        try:
            return simular(app.state.contract_provider(bank_id, law_firm_id), payload)
        except FileNotFoundError as exc:
            raise HTTPException(503, "Base histórica indisponível para a prévia.") from exc

    def require_bank(bank_id: str) -> None:
        if repository().get_bank(bank_id) is None:
            raise HTTPException(404, "Banco não encontrado.")

    @app.get("/api/admin/banks/{bank_id}/contract", response_model=BankContractRecord)
    def admin_bank_contract(bank_id: str, request: Request, law_firm_id: str | None = None) -> dict:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        require_bank(bank_id)
        return contract_record(bank_id, law_firm_id)

    @app.post("/api/admin/banks/{bank_id}/contract", response_model=BankContractRecord, status_code=201)
    def save_bank_contract(bank_id: str, payload: ParametrosContrato, request: Request, law_firm_id: str | None = None) -> dict:
        user = require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        require_bank(bank_id)
        if law_firm_id and repository().get_law_firm(law_firm_id) is None:
            raise HTTPException(404, "Escritório não encontrado.")
        repository().create_bank_contract(bank_id, payload.model_dump(exclude={"versao"}), user.get("id"), law_firm_id)
        audit(user, "BANK_CONTRACT_UPDATED", "BANK", bank_id, reason=f"law_firm_id={law_firm_id}")
        return contract_record(bank_id, law_firm_id)

    @app.post("/api/admin/banks/{bank_id}/contract/preview", response_model=ContractPreview)
    def preview_bank_contract(bank_id: str, payload: ParametrosContrato, request: Request, law_firm_id: str | None = None) -> dict:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        require_bank(bank_id)
        return contract_preview(bank_id, law_firm_id, payload)

    @app.get("/api/bank/contract", response_model=BankContractRecord)
    def bank_contract(request: Request, law_firm_id: str | None = None) -> dict:
        user = require_role(current_user(request), UserRole.BANCO)
        require_firm_of_bank(user["bank_id"], law_firm_id)
        return contract_record(user["bank_id"], law_firm_id)

    @app.post("/api/bank/contract", response_model=BankContractRecord, status_code=201)
    def bank_save_contract(payload: BankContractUpdate, request: Request, law_firm_id: str | None = None) -> dict:
        user = require_manager(current_user(request))
        require_firm_of_bank(user["bank_id"], law_firm_id)
        repository().create_bank_contract(user["bank_id"], payload.parametros.model_dump(exclude={"versao"}),
                                          user.get("id"), law_firm_id, payload.justificativa.strip())
        audit(user, "BANK_CONTRACT_UPDATED", "BANK", user["bank_id"], reason=payload.justificativa.strip())
        return contract_record(user["bank_id"], law_firm_id)

    @app.post("/api/bank/contract/preview", response_model=ContractPreview)
    def bank_preview_contract(payload: ParametrosContrato, request: Request, law_firm_id: str | None = None) -> dict:
        user = require_manager(current_user(request))
        require_firm_of_bank(user["bank_id"], law_firm_id)
        return contract_preview(user["bank_id"], law_firm_id, payload)

    @app.get("/api/bank/law-firms", response_model=list[LawFirmRecord])
    def bank_law_firms(request: Request) -> list[dict]:
        user = require_role(current_user(request), UserRole.BANCO)
        return repository().list_law_firms(user["bank_id"])

    @app.get("/api/bank/insights")
    def bank_insights(request: Request) -> dict:
        user = require_role(current_user(request), UserRole.BANCO)
        with connection_for(app_settings.database_path) as connection:
            return build_bank_insights(connection, user["bank_id"])

    @app.get("/api/bank/lawyers", response_model=list[UserRecord])
    def bank_lawyers(request: Request) -> list[dict]:
        user = require_role(current_user(request), UserRole.BANCO)
        return [candidate for candidate in repository().list_users(user["bank_id"]) if candidate["role"] == UserRole.ADVOGADO_EXTERNO.value and candidate["is_active"]]

    @app.patch("/api/bank/users/{user_id}/password", status_code=204)
    def bank_reset_password(user_id: str, payload: ResetPasswordRequest, request: Request) -> Response:
        """Gestor do banco redefine a senha de um usuário do próprio banco (não admin)."""
        manager = require_manager(current_user(request))
        target = repository().get_user(user_id)
        if target is None or target["bank_id"] != manager["bank_id"]:
            raise HTTPException(404, "Usuário não encontrado neste banco.")
        repository().update_user(user_id, {"password_hash": hash_password(payload.new_password)})
        audit(manager, "PASSWORD_RESET", "USER", user_id)
        return Response(status_code=204)

    @app.post("/api/cases", response_model=CaseRecord, status_code=status.HTTP_201_CREATED)
    def create_case(payload: CaseCreate, request: Request) -> dict:
        user = require_role(current_user(request), UserRole.BANCO)
        try:
            if payload.assigned_lawyer_id:
                candidate = repository().get_user(payload.assigned_lawyer_id)
                if candidate is None or candidate["role"] != UserRole.ADVOGADO_EXTERNO.value or candidate["bank_id"] != user["bank_id"] or not candidate["is_active"]:
                    raise HTTPException(422, "Advogado ativo do banco não encontrado.")
            return repository().create_case(payload, user["bank_id"], user["id"])
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/cases", response_model=list[CaseRecord])
    def list_cases(request: Request) -> list[dict]:
        user = current_user(request)
        require_role(user, UserRole.BANCO, UserRole.ADVOGADO_EXTERNO)
        return repository().list_cases(user["bank_id"], user["id"] if user["role"] == UserRole.ADVOGADO_EXTERNO.value else None)

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str, request: Request) -> dict:
        user = current_user(request)
        case = require_case_access(repository(), case_id, user)
        track(user, case_id, EngagementEventType.CASE_OPENED)
        documents = repository().list_documents(case_id)
        return {
            "negotiation_outcomes": repository().list_negotiation_outcomes(case_id),
            "document_readings": repository().list_document_readings(case_id),
            "fase": repository().case_flow(case_id),
            # A tela espera a leitura por IA só quando ela de fato vai acontecer.
            "leitura_ia_ativa": bool(app_settings.leitura_ia and os.getenv("OPENAI_API_KEY", "").strip()),
            "judicial_outcomes": repository().list_judicial_outcomes(case_id),
            "case": case,
            # ABERTO | DECIDIDO | ENCERRADO — a tela habilita ações a partir disto.
            "stage": repository().case_stage(case_id),
            "documents": documents,
            "document_requests": repository().list_document_requests(case_id),
            "analyses": repository().list_analyses(case_id),
            "dossie_analyses": app.state.dossie.summaries(case_id, documents),
            "lawyer_decisions": repository().list_lawyer_decisions(case_id),
        }

    @app.patch("/api/cases/{case_id}/assignment", response_model=CaseRecord)
    def assign_case(case_id: str, payload: CaseAssignment, request: Request) -> dict:
        user = require_role(current_user(request), UserRole.BANCO)
        require_case_access(repository(), case_id, user)
        require_open_case(case_id, "trocar o advogado responsável")
        try:
            case = repository().assign_lawyer(case_id, payload.assigned_lawyer_id, user["bank_id"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if case is None:
            raise HTTPException(404, "Processo não encontrado.")
        audit(user, "CASE_ASSIGNED", "CASE", case_id, case_id=case_id, reason=f"lawyer_id={payload.assigned_lawyer_id}")
        return case

    @app.post("/api/cases/{case_id}/documents", response_model=DocumentRecord, status_code=201)
    async def upload_document(
        case_id: str,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        declared_type: DocumentType | None = Form(default=None),
        source_party: SourceParty = Form(...),
        request_id: str | None = Form(default=None),
        request: Request = None,
    ) -> dict:
        user = current_user(request)
        require_case_access(repository(), case_id, user)
        require_open_case(case_id, "enviar novos documentos")
        source_party = SourceParty.BANCO if user["role"] in {"SYSTEM", UserRole.BANCO.value} else SourceParty.ADVOGADO_EXTERNO
        request_id = request_id or None
        if request_id:
            request = repository().get_document_request(request_id)
            if request is None or request["case_id"] != case_id:
                raise HTTPException(422, "Solicitação documental inválida para este processo.")
        try:
            document = await document_service().store_upload(
                case_id=case_id,
                upload=file,
                declared_type=declared_type,
                source_party=source_party,
                request_id=request_id,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        audit(user, "DOCUMENT_UPLOADED", "DOCUMENT", document["id"], case_id=case_id,
              reason="classificação automática por IA" if declared_type is None else f"declarado como {declared_type.value}")
        background_tasks.add_task(document_service().process_document, document["id"])
        return document

    @app.delete("/api/cases/{case_id}/documents/{document_id}", status_code=204)
    def delete_document(case_id: str, document_id: str, request: Request) -> Response:
        """
        Exclusão LÓGICA de um documento enviado pelo banco.

        A linha fica: análises já emitidas guardam este id em `feature_provenance`,
        e sem ela não há como reproduzir por que a recomendação saiu daquele jeito.
        O arquivo em disco é apagado — o conteúdo some, o rastro permanece.

        O advogado não apaga documento do banco: o gate documental é do banco, e
        deixar a outra parte remover prova seria conflito de interesse.
        """
        user = require_role(current_user(request), UserRole.BANCO)
        require_case_access(repository(), case_id, user)
        require_open_case(case_id, "excluir documentos")
        document = repository().get_document(document_id)
        if document is None or document["case_id"] != case_id:
            raise HTTPException(404, "Documento não encontrado neste processo.")
        if document["source_party"] != SourceParty.BANCO.value:
            raise HTTPException(403, "Só é possível excluir documentos enviados pelo banco.")
        internal = repository().get_document_internal(document_id)
        file_path = repository().soft_delete_document(document_id, user["id"])
        if file_path is None:
            raise HTTPException(404, "Documento não encontrado neste processo.")
        if internal:
            Path(internal["file_path"]).unlink(missing_ok=True)
        audit(user, "DOCUMENT_DELETED", "DOCUMENT", document_id, case_id=case_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/documents/{document_id}/pages/{page_number}")
    def get_document_page(document_id: str, page_number: int, request: Request) -> dict:
        document = repository().get_document(document_id)
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        user = current_user(request)
        require_case_access(repository(), document["case_id"], user)
        if page_number == 1:
            track(user, document["case_id"], EngagementEventType.DOCUMENT_OPENED, document_id)
        page = repository().get_page(document_id, page_number)
        if page is None:
            raise HTTPException(404, "Página extraída não encontrada.")
        return page

    @app.get("/api/documents/{document_id}/file")
    def download_document(document_id: str, request: Request, inline: bool = False) -> FileResponse:
        document = repository().get_document_internal(document_id)
        # Excluído logicamente não existe para quem consulta: a linha só sobrevive
        # para a auditoria das análises que já o usaram.
        if document is None or document.get("deleted_at"):
            raise HTTPException(404, "Documento não encontrado.")
        user = current_user(request)
        require_case_access(repository(), document["case_id"], user)
        track(user, document["case_id"], EngagementEventType.DOCUMENT_OPENED, document_id)
        path = Path(document["file_path"])
        if not path.exists():
            raise HTTPException(410, "Arquivo original não está mais disponível.")
        # inline=1 abre o PDF na própria tela do processo; sem ele, baixa o original.
        return FileResponse(path, filename=document["original_filename"],
                            content_disposition_type="inline" if inline else "attachment")

    @app.get("/api/documents/{document_id}/dossie-analysis", response_model=DossieAnalysisRecord)
    def get_dossie_analysis(document_id: str, request: Request) -> dict:
        document = repository().get_document(document_id)
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        require_case_access(repository(), document["case_id"], current_user(request))
        try:
            return app.state.dossie.get(document_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/documents/{document_id}/dossie-analysis", response_model=DossieAnalysisRecord, status_code=201)
    def analyze_dossie(document_id: str, request: Request) -> dict:
        document = repository().get_document(document_id)
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        require_case_access(repository(), document["case_id"], current_user(request))
        try:
            return app.state.dossie.analyze(document_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except DossieUnavailableError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/documents/{document_id}/type-confirmation", response_model=DocumentRecord)
    def confirm_document_type(document_id: str, payload: TypeConfirmation, request: Request) -> dict:
        document = repository().get_document_internal(document_id)
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        user = current_user(request)
        require_case_access(repository(), document["case_id"], user)
        if user["role"] == UserRole.BANCO.value and (document["source_party"] != SourceParty.BANCO.value or payload.action == "CONTINUE_WITH_RESERVATION"):
            raise HTTPException(403, "O banco só pode corrigir ou remover seus próprios documentos.")
        if payload.action == "REMOVE":
            repository().update_document_type(
                document_id,
                declared_type=DocumentType(document["declared_type"]),
                detected_type=document["detected_type"] and DocumentType(document["detected_type"]),
                type_status=DocumentTypeStatus.REMOVED,
            )
        elif payload.action == "CONTINUE_WITH_RESERVATION":
            repository().update_document_type(
                document_id,
                declared_type=DocumentType(document["declared_type"]),
                detected_type=document["detected_type"] and DocumentType(document["detected_type"]),
                type_status=DocumentTypeStatus.USER_CONFIRMED,
            )
        else:
            if payload.document_type is None:
                raise HTTPException(422, "Informe o novo tipo documental.")
            sample = repository().get_document_text_sample(document_id)
            validation = validate_document_type(payload.document_type, sample)
            repository().update_document_type(
                document_id,
                declared_type=payload.document_type,
                detected_type=validation.detected_type,
                type_status=validation.status,
            )
        audit(user, f"DOCUMENT_TYPE_{payload.action}", "DOCUMENT", document_id,
              case_id=document["case_id"], reason=payload.reason)
        return repository().get_document(document_id)  # type: ignore[return-value]

    @app.post("/api/cases/{case_id}/analyses", response_model=AnalysisRecord, status_code=201)
    def analyse_case(case_id: str, request: Request) -> dict:
        user = require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        require_case(case_id, request)
        require_open_case(case_id, "gerar nova avaliação")
        try:
            analysis = app.state.policy.evaluate(case_id)
            track(user, case_id, EngagementEventType.ANALYSIS_RUN)
            return analysis
        except FileNotFoundError as exc:
            raise HTTPException(503, "Artefato do modelo não disponível.") from exc

    @app.post("/api/cases/{case_id}/document-requests", response_model=DocumentRequestRecord, status_code=201)
    def create_document_request(case_id: str, payload: DocumentRequestCreate, request: Request) -> dict:
        require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        require_case(case_id, request)
        return repository().create_document_request(case_id, payload)

    @app.post("/api/document-requests/{request_id}/response", response_model=DocumentRequestRecord)
    def respond_document_request(request_id: str, payload: DocumentRequestResponse, request: Request) -> dict:
        user = require_role(current_user(request), UserRole.BANCO)
        document_request = repository().get_document_request(request_id)
        if document_request is None or require_case_access(repository(), document_request["case_id"], user) is None:
            raise HTTPException(404, "Solicitação documental não encontrada.")
        if payload.status not in {
            DocumentRequestStatus.DECLARED_UNAVAILABLE,
            DocumentRequestStatus.CANCELLED,
        }:
            raise HTTPException(422, "Resposta documental inválida.")
        motivo, fonte = None, None
        if payload.status == DocumentRequestStatus.DECLARED_UNAVAILABLE:
            if payload.unavailability_reason is not None:
                motivo, fonte = payload.unavailability_reason.value, "INFORMADO"
            else:
                motivo, fonte = classificar_motivo(payload.reason, document_request["document_type"])
        try:
            response = repository().respond_to_document_request(request_id, payload.status, payload.reason, motivo, fonte)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if response is None:
            raise HTTPException(404, "Solicitação documental não encontrada.")
        return response

    @app.post("/api/cases/{case_id}/lawyer-decisions", status_code=201)
    def create_lawyer_decision(case_id: str, analysis_id: str, payload: LawyerDecisionCreate, request: Request) -> dict:
        user = require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        case = require_case(case_id, request)
        # Uma decisão por processo (a segunda competiria com a primeira na aderência). A exceção
        # é "pedir documento": ela espera a empresa responder e, depois da reavaliação, dá lugar
        # à decisão final. A fase vem da máquina de estados em fluxo.py.
        fase = repository().case_flow(case_id)["codigo"]
        bloqueios = {
            "ENCERRADO": "Processo encerrado: não é possível registrar nova decisão.",
            "AGUARDANDO_AVALIACAO": "Avalie o processo antes de decidir.",
            "REAVALIAR": "Chegaram documentos novos: reavalie o processo antes de decidir.",
            "AGUARDANDO_DOCUMENTO": "Aguarde a empresa responder ao pedido de documento.",
        }
        if fase in bloqueios:
            raise HTTPException(409, bloqueios[fase])
        if fase != "PRONTO_PARA_DECIDIR":
            raise HTTPException(409, "Este processo já tem decisão registrada. Registre o desfecho.")
        analysis = repository().get_analysis(analysis_id)
        if analysis is None or analysis["case_id"] != case_id:
            raise HTTPException(422, "Análise inválida para este processo.")
        if repository().list_analyses(case_id)[0]["id"] != analysis_id:
            raise HTTPException(409, "Use a avaliação mais recente do processo.")
        if payload.action == "ACORDO" and not payload.proposed_value:
            raise HTTPException(422, "Informe o valor da proposta de acordo.")
        maximo = (analysis.get("pricing") or {}).get("walk_away_value")
        acima_do_maximo = payload.action == "ACORDO" and maximo is not None and payload.proposed_value > maximo + 0.01
        if (payload.action != analysis["recommendation"] or acima_do_maximo) and payload.divergence_reason is None:
            raise HTTPException(422, "A proposta passa do valor máximo: escolha o motivo." if acima_do_maximo and payload.action == analysis["recommendation"]
                                else "A decisão é diferente da recomendação: escolha o motivo.")
        if payload.divergence_reason == "OUTRO" and not (payload.reason or "").strip():
            raise HTTPException(422, "Descreva o motivo da divergência.")
        documento = None
        if payload.action == "RECUPERAR":
            plano = (analysis.get("policy_output") or {}).get("recuperacao") or {}
            documento = payload.requested_document or {"contrato": "CONTRATO", "extrato": "EXTRATO",
                                                       "comprovante_credito": "COMPROVANTE_CREDITO"}.get(plano.get("documento"))
            if documento is None:
                raise HTTPException(422, "Escolha qual documento pedir à empresa.")
        payload = payload.model_copy(update={
            "proposed_value": payload.proposed_value if payload.action == "ACORDO" else None,
            "requested_document": documento,
        })
        lawyer_id = user["id"] if user["role"] == UserRole.ADVOGADO_EXTERNO.value else case.get("assigned_lawyer_id")
        decision = repository().create_lawyer_decision(case_id, analysis_id, payload, lawyer_id)
        if documento:
            plano = (analysis.get("policy_output") or {}).get("recuperacao") or {}
            repository().create_document_request(case_id, DocumentRequestCreate(
                document_type=documento, hypothesis_key="decisao-do-advogado",
                reason=(plano.get("fundamento") or payload.reason or "Documento pedido pelo advogado antes de decidir.")[:1000]))
        track(user, case_id, EngagementEventType.DECISION_REGISTERED)
        audit(user, "LAWYER_DECISION_REGISTERED", "CASE", case_id, case_id=case_id, reason=payload.action)
        return decision

    @app.post("/api/cases/{case_id}/negotiation-outcomes", response_model=NegotiationOutcomeRecord, status_code=201)
    def create_negotiation_outcome(case_id: str, payload: NegotiationOutcomeCreate, request: Request) -> dict:
        user = require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        case = require_case(case_id, request)
        require_open_case(case_id, "registrar resultado da negociação")
        fase = repository().case_flow(case_id)
        if fase["codigo"] not in {"EM_NEGOCIACAO", "CONTRAPROPOSTA"}:
            raise HTTPException(409, "Não há negociação de acordo aberta neste processo.")
        analise_da_decisao = repository().get_analysis(fase["decisao"]["analysis_id"]) or {}
        maximo = (analise_da_decisao.get("pricing") or {}).get("walk_away_value")
        if (payload.status == "ACEITO" and maximo is not None and payload.closed_value > maximo + 0.01
                and payload.divergence_reason is None):
            raise HTTPException(422, "O valor passa do valor máximo: escolha o motivo para aceitar mesmo assim.")
        lawyer_id = user["id"] if user["role"] == UserRole.ADVOGADO_EXTERNO.value else case.get("assigned_lawyer_id")
        try:
            outcome = repository().create_negotiation_outcome(case_id, payload, lawyer_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        track(user, case_id, EngagementEventType.OUTCOME_REGISTERED)
        return outcome

    @app.post("/api/cases/{case_id}/judicial-outcomes", response_model=JudicialOutcomeRecord, status_code=201)
    def create_judicial_outcome(case_id: str, payload: JudicialOutcomeCreate, request: Request) -> dict:
        user = require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        case = require_case(case_id, request)
        if repository().case_flow(case_id)["codigo"] != "EM_DEFESA":
            raise HTTPException(409, "A sentença só entra em processo em defesa: decisão de defesa ou acordo recusado.")
        lawyer_id = user["id"] if user["role"] == UserRole.ADVOGADO_EXTERNO.value else case.get("assigned_lawyer_id")
        outcome = repository().create_judicial_outcome(case_id, payload, lawyer_id)
        track(user, case_id, EngagementEventType.OUTCOME_REGISTERED)
        return outcome

    @app.post("/api/cases/{case_id}/engagement", status_code=204)
    def record_engagement(case_id: str, payload: EngagementEventCreate, request: Request) -> Response:
        """Tela do advogado: abertura de documento pelo visualizador (tempo de tela não é coletado)."""
        user = require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        require_case(case_id, request)
        if payload.document_id:
            document = repository().get_document(payload.document_id)
            if document is None or document["case_id"] != case_id:
                raise HTTPException(422, "Documento não pertence a este processo.")
        if user["role"] == UserRole.ADVOGADO_EXTERNO.value:
            repository().record_engagement(case_id, user["id"], payload.event_type, payload.document_id)
        return Response(status_code=204)

    @app.post("/api/cases/{case_id}/lawyer-decisions/{decision_id}/outcome", status_code=201)
    def register_decision_outcome(
        case_id: str, decision_id: str, payload: LawyerDecisionOutcomeCreate, request: Request
    ) -> dict:
        """Fecha o processo: como terminou de verdade. Só o advogado do caso registra."""
        user = require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        case = require_case(case_id, request)
        decision = repository().get_decision(decision_id)
        if decision is None or decision["case_id"] != case_id:
            raise HTTPException(404, "Decisão não encontrada para este processo.")
        try:
            updated = repository().register_outcome(
                decision_id, payload.outcome.value, payload.outcome_note
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if updated is None:
            raise HTTPException(404, "Decisão não encontrada.")
        # O valor informado vira o registro detalhado que o painel da empresa usa
        # (quanto custou a sentença, por quanto o acordo fechou).
        lawyer_id = user["id"] if user["role"] == UserRole.ADVOGADO_EXTERNO.value else case.get("assigned_lawyer_id")
        desfecho = payload.outcome.value
        if desfecho == "SENTENCA_FAVORAVEL":
            repository().create_judicial_outcome(case_id, JudicialOutcomeCreate(result="EXITO"), lawyer_id)
        elif desfecho == "SENTENCA_DESFAVORAVEL" and payload.value is not None:
            repository().create_judicial_outcome(
                case_id, JudicialOutcomeCreate(result="NAO_EXITO", condemnation_value=payload.value), lawyer_id)
        elif desfecho == "ACORDO_ACEITO" and payload.value is not None and decision["action"] == "ACORDO":
            repository().create_negotiation_outcome(case_id, NegotiationOutcomeCreate(
                status="ACEITO", offered_value=decision["proposed_value"], closed_value=payload.value), lawyer_id)
        return updated

    @app.get("/api/lawyer/queue")
    def lawyer_queue(request: Request) -> list[dict]:
        """Minha fila: os processos do advogado na ordem da próxima ação."""
        user = require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        return repository().lawyer_queue(user["id"])

    @app.post("/api/cases/{case_id}/mensagem-proposta")
    def mensagem_proposta(case_id: str, payload: MensagemPropostaCreate, request: Request) -> dict:
        """Mensagem de proposta de acordo pronta para enviar ao advogado do autor."""
        user = require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        case = require_case(case_id, request)
        analises = repository().list_analyses(case_id)
        pricing = analises[0].get("pricing") if analises else None
        if not pricing:
            raise HTTPException(409, "Avalie o processo antes de redigir a proposta: ainda não há valor sugerido.")
        valor = payload.valor or pricing.get("recommended_value") or pricing["opening_value"]
        texto, fonte = redigir_mensagem(numero=case["case_number"], empresa=user.get("bank_name") or "a empresa",
                                        advogado=user.get("name") or "", valor=valor, prazo_dias=payload.prazo_dias)
        return {"mensagem": texto, "fonte": fonte, "valor": valor}

    @app.get("/api/lawyer/performance", response_model=LawyerPerformance)
    def lawyer_performance(request: Request) -> dict:
        """Números do próprio advogado. Êxito e aderência medem coisas diferentes."""
        user = require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        return repository().lawyer_performance(user["id"], frozenset(FAVORABLE_OUTCOMES))

    @app.post("/api/documents/{document_id}/leitura", status_code=201)
    def ler_documento_com_ia(document_id: str, request: Request) -> dict:
        """Refaz (ou faz pela primeira vez) a leitura por IA de um documento do processo."""
        user = require_role(current_user(request), UserRole.BANCO, UserRole.ADVOGADO_EXTERNO)
        document = repository().get_document(document_id)
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        require_case_access(repository(), document["case_id"], user)
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise HTTPException(503, "Leitura por IA indisponível: configure OPENAI_API_KEY no servidor.")
        return app.state.ler_com_ia(document_id)

    @app.get("/api/bank/search")
    def bank_search(q: str, request: Request) -> list[dict]:
        """Painel de busca da empresa: processo, número do contrato ou nome da parte."""
        user = require_role(current_user(request), UserRole.BANCO)
        termo = q.strip()
        if len(termo) < 3:
            raise HTTPException(422, "Digite ao menos 3 caracteres para buscar.")
        return repository().search_cases(user["bank_id"], termo)

    @app.get("/api/monitoring", response_model=MonitoringSummary)
    def monitoring(request: Request) -> dict:
        user = require_role(current_user(request), UserRole.BANCO)
        with connection_for(app_settings.database_path) as connection:
            return dict(build_monitoring_summary(connection, user["bank_id"]))

    return app


app = create_app()
