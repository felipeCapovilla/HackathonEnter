"""HTTP API for the EnterAgree evidence-backed settlement policy."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import hashlib
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
from src.policy.service import PolicyService
from contracts.schema import ParametrosContrato
from .repository import Repository
from .schemas import (
    AnalysisRecord,
    BankContractRecord,
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
    LawyerDecisionCreate,
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
)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(app_settings.database_path)
        app.state.repository = Repository(app_settings.database_path)
        app.state.documents = DocumentService(app.state.repository, app_settings)
        app.state.dossie = DossieService(app.state.repository)
        def contrato_do_banco(bank_id: str | None) -> ParametrosContrato:
            record = app.state.repository.get_active_bank_contract(bank_id) if bank_id else None
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/login", response_model=SessionUser)
    def login(payload: LoginRequest, response: Response) -> dict:
        user = repository().get_user_by_email(normalize_email(payload.email))
        if user is None or not user["is_active"] or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(401, "E-mail ou senha inválidos.")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        repository().create_session(hashlib.sha256(token.encode()).hexdigest(), user["id"], csrf, session_expiry())
        response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", secure=False, max_age=8 * 3600)
        response.headers["Cache-Control"] = "no-store"
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
            repository().revoke_session(hashlib.sha256(token.encode()).hexdigest())
        response.status_code = status.HTTP_204_NO_CONTENT
        response.headers["Cache-Control"] = "no-store"
        response.delete_cookie(COOKIE_NAME)
        return response

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
        try:
            return repository().create_user({"id": str(secrets.token_hex(16)), "name": payload.name.strip(), "email": normalize_email(payload.email), "password_hash": hash_password(payload.password), "role": payload.role.value, "bank_id": payload.bank_id, "is_active": True, "created_at": datetime.now(UTC).isoformat()})
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.patch("/api/admin/users/{user_id}", response_model=UserRecord)
    def update_user(user_id: str, payload: UserUpdate, request: Request) -> dict:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        changes = payload.model_dump(exclude_none=True)
        if "password" in changes:
            changes["password_hash"] = hash_password(changes.pop("password"))
        user = repository().update_user(user_id, changes)
        if user is None:
            raise HTTPException(404, "Usuário não encontrado.")
        return user

    def contract_record(bank_id: str) -> dict:
        record = repository().get_active_bank_contract(bank_id)
        if record is None:
            return {"bank_id": bank_id, "version": 0, "parameters": ParametrosContrato().model_dump()}
        return {**record, "parameters": {**record["parameters"], "versao": f"{bank_id}-v{record['version']}"}}

    def require_bank(bank_id: str) -> None:
        if repository().get_bank(bank_id) is None:
            raise HTTPException(404, "Banco não encontrado.")

    @app.get("/api/admin/banks/{bank_id}/contract", response_model=BankContractRecord)
    def admin_bank_contract(bank_id: str, request: Request) -> dict:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        require_bank(bank_id)
        return contract_record(bank_id)

    @app.post("/api/admin/banks/{bank_id}/contract", response_model=BankContractRecord, status_code=201)
    def save_bank_contract(bank_id: str, payload: ParametrosContrato, request: Request) -> dict:
        user = require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        require_bank(bank_id)
        repository().create_bank_contract(bank_id, payload.model_dump(exclude={"versao"}), user.get("id"))
        return contract_record(bank_id)

    @app.post("/api/admin/banks/{bank_id}/contract/preview", response_model=ContractPreview)
    def preview_bank_contract(bank_id: str, payload: ParametrosContrato, request: Request) -> dict:
        require_role(current_user(request), UserRole.ADMIN_GLOBAL)
        require_bank(bank_id)
        from src.policy.preview import simular
        try:
            return simular(app.state.contract_provider(bank_id), payload)
        except FileNotFoundError as exc:
            raise HTTPException(503, "Base histórica indisponível para a prévia.") from exc

    @app.get("/api/bank/contract", response_model=BankContractRecord)
    def bank_contract(request: Request) -> dict:
        user = require_role(current_user(request), UserRole.BANCO)
        return contract_record(user["bank_id"])

    @app.get("/api/bank/lawyers", response_model=list[UserRecord])
    def bank_lawyers(request: Request) -> list[dict]:
        user = require_role(current_user(request), UserRole.BANCO)
        return [candidate for candidate in repository().list_users(user["bank_id"]) if candidate["role"] == UserRole.ADVOGADO_EXTERNO.value and candidate["is_active"]]

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
        case = require_case(case_id, request)
        documents = repository().list_documents(case_id)
        return {
            "case": case,
            "documents": documents,
            "document_requests": repository().list_document_requests(case_id),
            "analyses": repository().list_analyses(case_id),
            "dossie_analyses": app.state.dossie.summaries(case_id, documents),
            "lawyer_decisions": repository().list_lawyer_decisions(case_id),
        }

    @app.patch("/api/cases/{case_id}/assignment", response_model=CaseRecord)
    def assign_case(case_id: str, payload: CaseAssignment, request: Request) -> dict:
        user = require_role(current_user(request), UserRole.BANCO)
        try:
            case = repository().assign_lawyer(case_id, payload.assigned_lawyer_id, user["bank_id"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if case is None:
            raise HTTPException(404, "Processo não encontrado.")
        return case

    @app.post("/api/cases/{case_id}/documents", response_model=DocumentRecord, status_code=201)
    async def upload_document(
        case_id: str,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        declared_type: DocumentType = Form(...),
        source_party: SourceParty = Form(...),
        request_id: str | None = Form(default=None),
        request: Request = None,
    ) -> dict:
        user = current_user(request)
        require_case_access(repository(), case_id, user)
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
        background_tasks.add_task(document_service().process_document, document["id"])
        return document

    @app.get("/api/documents/{document_id}/pages/{page_number}")
    def get_document_page(document_id: str, page_number: int, request: Request) -> dict:
        document = repository().get_document(document_id)
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        require_case_access(repository(), document["case_id"], current_user(request))
        page = repository().get_page(document_id, page_number)
        if page is None:
            raise HTTPException(404, "Página extraída não encontrada.")
        return page

    @app.get("/api/documents/{document_id}/file")
    def download_document(document_id: str, request: Request) -> FileResponse:
        document = repository().get_document_internal(document_id)
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        require_case_access(repository(), document["case_id"], current_user(request))
        path = Path(document["file_path"])
        if not path.exists():
            raise HTTPException(410, "Arquivo original não está mais disponível.")
        return FileResponse(path, filename=document["original_filename"])

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
        return repository().get_document(document_id)  # type: ignore[return-value]

    @app.post("/api/cases/{case_id}/analyses", response_model=AnalysisRecord, status_code=201)
    def analyse_case(case_id: str, request: Request) -> dict:
        require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        require_case(case_id, request)
        try:
            return app.state.policy.evaluate(case_id)
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
        try:
            response = repository().respond_to_document_request(request_id, payload.status, payload.reason)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if response is None:
            raise HTTPException(404, "Solicitação documental não encontrada.")
        return response

    @app.post("/api/cases/{case_id}/lawyer-decisions", status_code=201)
    def create_lawyer_decision(case_id: str, analysis_id: str, payload: LawyerDecisionCreate, request: Request) -> dict:
        require_role(current_user(request), UserRole.ADVOGADO_EXTERNO)
        require_case(case_id, request)
        analysis = repository().get_analysis(analysis_id)
        if analysis is None or analysis["case_id"] != case_id:
            raise HTTPException(422, "Análise inválida para este processo.")
        return repository().create_lawyer_decision(case_id, analysis_id, payload)

    @app.get("/api/monitoring", response_model=MonitoringSummary)
    def monitoring(request: Request) -> dict:
        user = require_role(current_user(request), UserRole.BANCO)
        with connection_for(app_settings.database_path) as connection:
            return dict(build_monitoring_summary(connection, user["bank_id"]))

    return app


app = create_app()
