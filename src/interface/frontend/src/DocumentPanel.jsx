import { useState } from "react";
import { documentDownloadUrl, request } from "./api";
import { useAction } from "./hooks";

const documentTypes = {
  AUTOS: "Autos do processo",
  CONTRATO: "Contrato",
  EXTRATO: "Extrato bancário",
  COMPROVANTE_CREDITO: "Comprovante de crédito",
  DOSSIE: "Dossiê",
  DEMONSTRATIVO_DIVIDA: "Demonstrativo de evolução da dívida",
  LAUDO_REFERENCIADO: "Laudo referenciado",
  OUTRO: "Outro documento",
};

const statuses = {
  UPLOADED: "Aguardando processamento",
  EXTRACTING: "Extraindo texto",
  COMPLETED: "Processado",
  COMPLETED_WITH_WARNINGS: "Processado com ressalvas",
  FAILED: "Falha no processamento",
};

function DocumentNotice({ document }) {
  if (document.type_status === "REMOVED") return <p className="muted">Removido da análise.</p>;
  if (document.status === "FAILED") return <p className="warning">Não foi possível extrair o conteúdo. Verifique o arquivo e envie uma versão legível.</p>;
  if (["UPLOADED", "EXTRACTING"].includes(document.status)) return null;
  return <>
    {document.type_status === "MISMATCH" && <p className="warning">O conteúdo parece ser {documentTypes[document.detected_type] || "outro tipo de documento"}, diferente do tipo informado. A divergência precisa ser resolvida antes de usar este documento na análise.</p>}
    {document.type_status === "UNCONFIRMED" && <p className="muted">Não foi possível confirmar o tipo pelo conteúdo. Isso não comprova que o documento seja inválido.</p>}
    {document.quality_flags?.includes("LOW_TEXT_COVERAGE_TODO_OCR") && <p className="warning">Pouco texto disponível. A leitura por OCR ainda não está implementada; envie uma versão com texto selecionável, se disponível.</p>}
  </>;
}

export function DocumentPanel({ caseId, documents, canUpload, onUploaded }) {
  const action = useAction();
  const [notice, setNotice] = useState("");
  const upload = (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    action.run(async () => {
      setNotice("");
      const file = form.get("file");
      if (!file?.size) throw new Error("Selecione um arquivo que não esteja vazio.");
      if (!/\.(pdf|txt)$/i.test(file.name)) throw new Error("Envie um arquivo PDF ou TXT.");
      form.set("source_party", "BANCO");
      await request(`/cases/${caseId}/documents`, { method: "POST", body: form });
      formElement.reset();
      setNotice("Documento enviado. O processamento será atualizado automaticamente.");
      onUploaded();
    });
  };

  return <article className="panel documents-panel">
    <h3>Documentos do processo</h3>
    {canUpload && <form className="document-upload" onSubmit={upload}>
      <p className="muted" id="document-upload-help">Envie os documentos do banco para o advogado responsável. Formatos aceitos: PDF e TXT, um arquivo por envio. Dossiês são enviados à OpenAI para análise automática assim que o processamento termina.</p>
      <fieldset className="form-fields" disabled={action.pending}>
        <label>Tipo de documento<select name="declared_type" required defaultValue="">
          <option value="">Selecione o tipo</option>
          {Object.entries(documentTypes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>Arquivo do documento<input name="file" type="file" accept=".pdf,.txt" required aria-describedby="document-upload-help" /></label>
        <button>{action.pending ? "Enviando documento…" : "Enviar documento"}</button>
      </fieldset>
      {action.error && <div className="warning" role="alert">{action.error}</div>}
      {notice && <p role="status">{notice}</p>}
    </form>}
    {documents.length ? <ul className="document-list">{documents.map((document) => <li key={document.id}>
      <strong>{document.original_filename}</strong>
      <span>{documentTypes[document.declared_type] || document.declared_type} · {document.source_party === "BANCO" ? "Enviado pelo banco" : "Enviado pelo advogado"}</span>
      <span>{statuses[document.status] || document.status}{document.page_count > 0 && ` · ${document.page_count} página(s)`}</span>
      <DocumentNotice document={document} />
      <a href={documentDownloadUrl(document.id)} target="_blank" rel="noopener noreferrer" aria-label={`Baixar ${document.original_filename}`}>Baixar documento original</a>
    </li>)}</ul> : <p className="muted">Nenhum documento enviado.</p>}
  </article>;
}
