"""
Os 2 processos de exemplo da Enter, com os PDFs originais, atribuídos à advogada demo.

- Caso 1 (São Luís/MA, não reconhece a contratação): os 7 documentos, contrato e extrato inclusos.
- Caso 2 (Manaus/AM, alega fraude): sem contrato e sem extrato.

Os PDFs ficam em exemplos/casos e passam pela mesma extração do envio pela tela.
Uso: python -m scripts.seed_casos_exemplo --confirm-demo [--reset] [--database caminho.db]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from scripts.seed_demo import DEMO_DATABASE_PATH, seed_demo
from src.interface.backend.config import Settings
from src.interface.backend.database import connection_for
from src.interface.backend.repository import Repository
from src.interface.backend.schemas import CaseCreate, DocumentType, SourceParty
from src.policy.service import PolicyService
from src.tools.leitor_documentos import LeituraIndisponivel, ler_documento
from src.utils.document_service import DocumentService

ROOT = Path(__file__).resolve().parents[1]
EXEMPLOS = ROOT / "exemplos" / "casos"
CASOS = (
    {"pasta": "Caso_01_0801234-56-2024-8-10-0001", "numero": "0801234-56.2024.8.10.0001", "uf": "MA",
     "valor": 20000.0, "assunto": "Não reconhece a contratação"},
    {"pasta": "Caso_02_0654321-09-2024-8-04-0001", "numero": "0654321-09.2024.8.04.0001", "uf": "AM",
     "valor": 25000.0, "assunto": "Golpe"},
)
TIPOS = (("Autos", DocumentType.AUTOS), ("Contrato", DocumentType.CONTRATO), ("Extrato", DocumentType.EXTRATO),
         ("Comprovante", DocumentType.COMPROVANTE_CREDITO), ("Dossie", DocumentType.DOSSIE),
         ("Demonstrativo", DocumentType.DEMONSTRATIVO_DIVIDA), ("Laudo", DocumentType.LAUDO_REFERENCIADO))
TABELAS_POR_CASO = ("divergence_balances", "engagement_events", "negotiation_outcomes", "judicial_outcomes", "document_requests",
                    "lawyer_decisions", "analyses")


def tipo_do_arquivo(nome: str) -> DocumentType:
    parte = nome.split("_", 1)[1]
    return next(tipo for prefixo, tipo in TIPOS if parte.startswith(prefixo))


def _apagar(database_path: Path, case_id: str, document_dir: Path) -> None:
    with connection_for(database_path) as connection:
        documentos = "SELECT id FROM documents WHERE case_id = ?"
        conversas = "SELECT id FROM document_chat_conversations WHERE case_id = ?"
        mensagens = f"SELECT id FROM document_chat_messages WHERE conversation_id IN ({conversas})"
        connection.execute(f"DELETE FROM document_chat_retrievals WHERE message_id IN ({mensagens})", (case_id,))
        connection.execute(f"DELETE FROM document_chat_messages WHERE conversation_id IN ({conversas})", (case_id,))
        connection.execute("DELETE FROM document_chat_conversations WHERE case_id = ?", (case_id,))
        for tabela in ("document_ai_readings", "document_pages", "document_chunks", "dossie_analyses", "dossie_analysis_claims"):
            connection.execute(f"DELETE FROM {tabela} WHERE document_id IN ({documentos})", (case_id,))
        for tabela in TABELAS_POR_CASO:
            connection.execute(f"DELETE FROM {tabela} WHERE case_id = ?", (case_id,))
        connection.execute("DELETE FROM documents WHERE case_id = ?", (case_id,))
        connection.execute("DELETE FROM cases WHERE id = ?", (case_id,))
    shutil.rmtree(document_dir / case_id, ignore_errors=True)


def _ler(documento: dict, texto: str) -> tuple[str, dict | None, str | None]:
    try:
        leitura = ler_documento(Path(documento["file_path"]), texto, documento["declared_type"])
    except LeituraIndisponivel as exc:
        return "FAILED", None, str(exc)
    return "COMPLETED", leitura.model_dump(mode="json"), None


def ler_com_ia(repository: Repository, document_ids: list[str]) -> list[str]:
    """Leitura por IA já pronta na demo, a mesma da rota de leitura. Só roda com OPENAI_API_KEY."""
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return []
    modelo = os.getenv("ENTERAGREE_LEITURA_MODEL", "gpt-4o-mini")
    documentos = [repository.get_document_internal(document_id) for document_id in document_ids]
    textos = [repository.get_document_text_sample(document["id"], 24_000) for document in documentos]
    with ThreadPoolExecutor(max_workers=6) as pool:
        resultados = list(pool.map(_ler, documentos, textos))
    for documento, (status, resultado, erro) in zip(documentos, resultados):
        repository.save_document_reading(documento["id"], modelo, status, resultado, erro)
    return [status for status, _, _ in resultados]


def _fila_comeca_pelos_exemplos(database_path: Path, repository: Repository, advogada: dict) -> int:
    """A fila da advogada demo abre pelos processos com PDFs: simulados sem documento que passariam
    na frente vão para um colega do mesmo escritório. Os números do painel do banco não mudam."""
    numeros = {caso["numero"] for caso in CASOS}
    fila = repository.lawyer_queue(advogada["id"])
    exemplos = [item for item in fila if item["case_number"] in numeros]
    if not exemplos:
        return 0
    corte = max(item["fase"]["prioridade"] for item in exemplos)
    na_frente = [item["id"] for item in fila if item["case_number"] not in numeros and item.get("is_simulated")
                 and item["fase"]["prioridade"] <= corte]
    if not na_frente:
        return 0
    with connection_for(database_path) as connection:
        colega = connection.execute(
            """SELECT id FROM users WHERE role = 'ADVOGADO_EXTERNO' AND id != ? AND law_firm_id = ? AND bank_id = ?
            ORDER BY name LIMIT 1""", (advogada["id"], advogada.get("law_firm_id"), advogada["bank_id"])).fetchone()
        if colega is None:
            return 0
        marcas = ",".join("?" * len(na_frente))
        connection.execute(f"UPDATE cases SET assigned_lawyer_id = ? WHERE id IN ({marcas})", (colega["id"], *na_frente))
        for tabela, coluna in (("lawyer_decisions", "lawyer_id"), ("negotiation_outcomes", "lawyer_id"),
                               ("judicial_outcomes", "lawyer_id"), ("engagement_events", "user_id")):
            connection.execute(f"UPDATE {tabela} SET {coluna} = ? WHERE case_id IN ({marcas}) AND {coluna} = ?",
                               (colega["id"], *na_frente, advogada["id"]))
    return len(na_frente)


def semear(database_path: Path, *, reset: bool = False) -> list[dict]:
    seed_demo(database_path)
    repository = Repository(database_path)
    runtime = database_path.parent
    settings = Settings(runtime_dir=runtime, database_path=database_path, document_dir=runtime / "documents",
                        artifact_dir=ROOT / "artefatos", max_upload_bytes=64 * 1024 * 1024)
    documentos = DocumentService(repository, settings)
    advogada = repository.get_user_by_email("advogada@demo.local")
    empresa = repository.get_user_by_email("banco@demo.local")
    for case in repository.list_cases(bank_id="banco-unicamp"):
        if case["case_number"].startswith("smoke-"):  # sobra de teste manual: não pode aparecer na demo
            _apagar(database_path, case["id"], settings.document_dir)
    existentes = {case["case_number"]: case for case in repository.list_cases(bank_id="banco-unicamp")}
    resumo = []
    for caso in CASOS:
        if caso["numero"] in existentes:
            if not reset:
                resumo.append({"numero": caso["numero"], "situacao": "já existia"})
                continue
            _apagar(database_path, existentes[caso["numero"]]["id"], settings.document_dir)
        registro = repository.create_case(
            CaseCreate(case_number=caso["numero"], uf=caso["uf"], value_of_claim=caso["valor"], sub_subject=caso["assunto"],
                       assigned_lawyer_id=advogada["id"]),
            bank_id="banco-unicamp", created_by_user_id=empresa["id"])
        pasta = settings.document_dir / registro["id"]
        pasta.mkdir(parents=True, exist_ok=True)
        tipos, enviados = [], []
        for pdf in sorted((EXEMPLOS / caso["pasta"]).glob("*.pdf")):
            conteudo = pdf.read_bytes()
            sha = hashlib.sha256(conteudo).hexdigest()
            destino = pasta / f"{sha}-{uuid4().hex}.pdf"
            destino.write_bytes(conteudo)
            documento = repository.create_document(case_id=registro["id"], original_filename=pdf.name, file_path=destino,
                                                   declared_type=tipo_do_arquivo(pdf.name), source_party=SourceParty.BANCO,
                                                   sha256=sha, request_id=None)
            documentos.process_document(documento["id"])
            enviados.append(documento["id"])
            processado = repository.get_document(documento["id"])
            tipos.append(f"{processado['declared_type']}:{processado['type_status']}")
        PolicyService(repository).evaluate(registro["id"])  # a advogada abre o processo com a recomendação pronta
        leituras = ler_com_ia(repository, enviados)
        resumo.append({"numero": caso["numero"], "situacao": "criado", "documentos": tipos,
                       "leituras_ia": f"{leituras.count('COMPLETED')}/{len(enviados)}" if leituras else "sem OPENAI_API_KEY"})
    movidos = _fila_comeca_pelos_exemplos(database_path, repository, repository.get_user_by_email("advogada@demo.local"))
    if movidos:
        resumo.append({"numero": "fila da advogada demo", "situacao": f"{movidos} processo(s) simulado(s) passados a um colega"})
    return resumo


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria os 2 processos de exemplo com PDFs para a advogada demo.")
    parser.add_argument("--confirm-demo", action="store_true", help="Confirma uso local; nunca use em produção.")
    parser.add_argument("--reset", action="store_true", help="Recria os 2 processos (apaga decisões e documentos deles).")
    parser.add_argument("--database", type=Path, default=DEMO_DATABASE_PATH)
    arguments = parser.parse_args()
    if not arguments.confirm_demo:
        parser.error("Informe --confirm-demo para criar os processos de exemplo.")
    for item in semear(arguments.database, reset=arguments.reset):
        print(f"{item['numero']}: {item['situacao']}", *item.get("documentos", []), item.get("leituras_ia", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
