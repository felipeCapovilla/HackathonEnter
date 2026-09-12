"""HTTP API for the EnterAgree evidence-backed settlement policy."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import Settings, get_settings
from .database import connection_for, initialize_database
from src.utils.document_service import DocumentService
from src.utils.document_type_validator import validate_document_type
from .monitoring import build_monitoring_summary
from src.policy.service import PolicyService
from .repository import Repository
from .schemas import (
    AnalysisRecord,
    CaseCreate,
    CaseRecord,
    DocumentRecord,
    DocumentRequestCreate,
    DocumentRequestRecord,
    DocumentRequestResponse,
    DocumentRequestStatus,
    DocumentType,
    DocumentTypeStatus,
    LawyerDecisionCreate,
    MonitoringSummary,
    SourceParty,
    TypeConfirmation,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(app_settings.database_path)
        app.state.repository = Repository(app_settings.database_path)
        app.state.documents = DocumentService(app.state.repository, app_settings)
        app.state.policy = PolicyService(
            app.state.repository, str(app_settings.artifact_dir / "modelo_xgboost.pkl")
        )
        yield

    app = FastAPI(title="EnterAgree API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def repository() -> Repository:
        return app.state.repository

    def document_service() -> DocumentService:
        return app.state.documents

    def require_case(case_id: str) -> dict:
        case = repository().get_case(case_id)
        if case is None:
            raise HTTPException(404, "Processo não encontrado.")
        return case

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/cases", response_model=CaseRecord, status_code=status.HTTP_201_CREATED)
    def create_case(payload: CaseCreate) -> dict:
        try:
            return repository().create_case(payload)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/cases", response_model=list[CaseRecord])
    def list_cases() -> list[dict]:
        return repository().list_cases()

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str) -> dict:
        case = require_case(case_id)
        return {
            "case": case,
            "documents": repository().list_documents(case_id),
            "document_requests": repository().list_document_requests(case_id),
            "analyses": repository().list_analyses(case_id),
            "lawyer_decisions": repository().list_lawyer_decisions(case_id),
        }

    @app.post("/api/cases/{case_id}/documents", response_model=DocumentRecord, status_code=201)
    async def upload_document(
        case_id: str,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        declared_type: DocumentType = Form(...),
        source_party: SourceParty = Form(...),
        request_id: str | None = Form(default=None),
    ) -> dict:
        require_case(case_id)
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
    def get_document_page(document_id: str, page_number: int) -> dict:
        page = repository().get_page(document_id, page_number)
        if page is None:
            raise HTTPException(404, "Página extraída não encontrada.")
        return page

    @app.get("/api/documents/{document_id}/file")
    def download_document(document_id: str) -> FileResponse:
        document = repository().get_document_internal(document_id)
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        path = Path(document["file_path"])
        if not path.exists():
            raise HTTPException(410, "Arquivo original não está mais disponível.")
        return FileResponse(path, filename=document["original_filename"])

    @app.post("/api/documents/{document_id}/type-confirmation", response_model=DocumentRecord)
    def confirm_document_type(document_id: str, payload: TypeConfirmation) -> dict:
        document = repository().get_document_internal(document_id)
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
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
    def analyse_case(case_id: str) -> dict:
        require_case(case_id)
        try:
            return app.state.policy.evaluate(case_id)
        except FileNotFoundError as exc:
            raise HTTPException(503, "Artefato do modelo não disponível.") from exc

    @app.post("/api/cases/{case_id}/document-requests", response_model=DocumentRequestRecord, status_code=201)
    def create_document_request(case_id: str, payload: DocumentRequestCreate) -> dict:
        require_case(case_id)
        return repository().create_document_request(case_id, payload)

    @app.post("/api/document-requests/{request_id}/response", response_model=DocumentRequestRecord)
    def respond_document_request(request_id: str, payload: DocumentRequestResponse) -> dict:
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
    def create_lawyer_decision(case_id: str, analysis_id: str, payload: LawyerDecisionCreate) -> dict:
        require_case(case_id)
        analysis = repository().get_analysis(analysis_id)
        if analysis is None or analysis["case_id"] != case_id:
            raise HTTPException(422, "Análise inválida para este processo.")
        return repository().create_lawyer_decision(case_id, analysis_id, payload)

    @app.get("/api/monitoring", response_model=MonitoringSummary)
    def monitoring() -> dict:
        with connection_for(app_settings.database_path) as connection:
            return dict(build_monitoring_summary(connection))

    return app


app = create_app()
