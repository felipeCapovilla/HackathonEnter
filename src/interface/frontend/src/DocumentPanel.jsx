import { useState } from "react";
import { documentDownloadUrl, request } from "./api";
import { useAction } from "./hooks";
import { Icon } from "./Brand";

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
  UPLOADED: { label: "Aguardando processamento", tone: "" },
  EXTRACTING: { label: "Extraindo texto", tone: "info" },
  COMPLETED: { label: "Processado", tone: "success" },
  COMPLETED_WITH_WARNINGS: { label: "Processado com ressalvas", tone: "amber" },
  FAILED: { label: "Falha no processamento", tone: "danger" },
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

/**
 * Exclusão em dois passos.
 *
 * O arquivo some do disco e o documento deixa de alimentar a política — não dá
 * para desfazer pela interface. Por isso a confirmação fica inline, mostrando o
 * nome do arquivo: um `window.confirm` seria mais barato de escrever e mais
 * fácil de clicar por engano.
 */
function DeleteDocument({ caseId, document, onDeleted }) {
  const [confirming, setConfirming] = useState(false);
  const action = useAction();
  const remove = () => action.run(async () => {
    await request(`/cases/${caseId}/documents/${document.id}`, { method: "DELETE" });
    setConfirming(false);
    onDeleted();
  });

  if (!confirming) {
    return <button type="button" className="danger-ghost" onClick={() => setConfirming(true)}>
      <Icon name="trash" />Excluir
    </button>;
  }
  return <div className="confirm-delete">
    <strong>Excluir “{document.original_filename}”?</strong>
    <span>O arquivo é apagado e o documento deixa de contar para a recomendação.</span>
    <span className="spacer" />
    <button type="button" className="subtle" disabled={action.pending} onClick={() => setConfirming(false)}>Cancelar</button>
    <button type="button" className="go" disabled={action.pending} onClick={remove}>{action.pending ? "Excluindo…" : "Excluir"}</button>
    {action.error && <p role="alert">{action.error}</p>}
  </div>;
}

export function DocumentPanel({ caseId, documents, canUpload, encerrado = false, onUploaded }) {
  // Depois do desfecho a prova é histórica: nem entra documento novo, nem sai o
  // que já sustentou a recomendação emitida.
  const podeEditar = canUpload && !encerrado;
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
    <div className="panel-heading">
      <span className="panel-icon"><Icon name="files" /></span>
      <div><h3>Documentos do processo</h3><p>O que sustenta a recomendação.</p></div>
      <span className="count-badge">{documents.length}</span>
    </div>
    {encerrado && canUpload && <p className="locked"><Icon name="lock" />Processo encerrado: os documentos não podem mais ser alterados.</p>}
    {podeEditar && <form className="document-upload" onSubmit={upload}>
      <p className="muted" id="document-upload-help">Envie os documentos do banco para o advogado responsável. Formatos aceitos: PDF e TXT, um arquivo por envio. Dossiês são enviados à OpenAI para análise automática assim que o processamento termina.</p>
      <fieldset className="form-fields" disabled={action.pending}>
        <label>Tipo de documento<select name="declared_type" required defaultValue="">
          <option value="">Selecione o tipo</option>
          {Object.entries(documentTypes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>Arquivo do documento<input name="file" type="file" accept=".pdf,.txt" required aria-describedby="document-upload-help" /></label>
        <button>{action.pending ? "Enviando documento…" : <>Enviar documento<Icon name="arrow" /></>}</button>
      </fieldset>
      {action.error && <div className="warning" role="alert">{action.error}</div>}
      {notice && <p role="status">{notice}</p>}
    </form>}
    {documents.length ? <ul className="document-list">{documents.map((document) => {
      const status = statuses[document.status] || { label: document.status, tone: "" };
      return <li key={document.id}>
        <div className="document-head">
          <strong>{document.original_filename}</strong>
          <span className={`pill ${status.tone}`}>{status.label}</span>
        </div>
        <span>
          {documentTypes[document.declared_type] || document.declared_type}
          {" · "}{document.source_party === "BANCO" ? "Enviado pelo banco" : "Enviado pelo advogado"}
          {document.page_count > 0 && ` · ${document.page_count} página(s)`}
        </span>
        <DocumentNotice document={document} />
        <div className="document-actions">
          <a href={documentDownloadUrl(document.id)} target="_blank" rel="noopener noreferrer" aria-label={`Baixar ${document.original_filename}`}>Baixar original</a>
          {/* Só o banco exclui, e só o que ele mesmo enviou: o gate documental é dele. */}
          {podeEditar && document.source_party === "BANCO" && <DeleteDocument caseId={caseId} document={document} onDeleted={onUploaded} />}
        </div>
      </li>;
    })}</ul> : <div className="empty-state">
      <Icon name="files" />
      <p>Nenhum documento enviado</p>
      <span>{podeEditar ? "Envie contrato, extrato e comprovante de crédito — são eles que decidem o caso." : "O banco não enviou documentos para este processo."}</span>
    </div>}
  </article>;
}
