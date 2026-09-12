import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

const DOCUMENT_TYPES = [
  "AUTOS", "CONTRATO", "EXTRATO", "COMPROVANTE_CREDITO", "DOSSIE",
  "DEMONSTRATIVO_DIVIDA", "LAUDO_REFERENCIADO", "OUTRO",
];

const labels = {
  AUTOS: "Autos", CONTRATO: "Contrato", EXTRATO: "Extrato",
  COMPROVANTE_CREDITO: "Comprovante de crédito", DOSSIE: "Dossiê",
  DEMONSTRATIVO_DIVIDA: "Demonstrativo de dívida", LAUDO_REFERENCIADO: "Laudo referenciado",
  OUTRO: "Outro", ACORDO: "Acordo", DEFESA: "Defesa",
  BANCO: "Banco", ADVOGADO_EXTERNO: "Advogado externo",
};

function money(value) {
  if (value == null) return "—";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function percentage(value) {
  return value == null ? "—" : new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 }).format(value);
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (response.ok) return response.status === 204 ? null : response.json();

  let message = `Erro ${response.status}`;
  const body = await response.text();
  if (body) {
    try {
      const parsed = JSON.parse(body);
      const detail = parsed.detail || parsed.message;
      if (Array.isArray(detail)) message = detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
      else if (detail) message = typeof detail === "string" ? detail : JSON.stringify(detail);
    } catch {
      message = body;
    }
  }
  throw new Error(message);
}

function App() {
  const [cases, setCases] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [monitoring, setMonitoring] = useState(null);
  const [loadingCases, setLoadingCases] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [connected, setConnected] = useState(null);
  const detailRequest = useRef(0);
  const selectedCase = useRef(null);

  const selectedAnalysis = useMemo(() => detail?.analyses?.[0] || null, [detail]);

  async function refreshCases() {
    try {
      setCases(await api("/cases"));
      setConnected(true);
    } catch (requestError) {
      setConnected(false);
      throw requestError;
    }
  }

  async function refreshMonitoring() {
    setMonitoring(await api("/monitoring"));
  }

  async function loadDetail(caseId) {
    if (caseId !== selectedCase.current) return null;
    const requestNumber = ++detailRequest.current;
    setLoadingDetail(true);
    try {
      const data = await api(`/cases/${encodeURIComponent(caseId)}`);
      if (requestNumber !== detailRequest.current || caseId !== selectedCase.current) return null;
      setDetail(data);
      return data;
    } catch (requestError) {
      if (requestNumber !== detailRequest.current || caseId !== selectedCase.current) return null;
      setError(`Não foi possível carregar o caso: ${requestError.message}`);
      return null;
    } finally {
      if (requestNumber === detailRequest.current) setLoadingDetail(false);
    }
  }

  function selectCase(caseId) {
    if (caseId === selectedCase.current) return;
    selectedCase.current = caseId;
    detailRequest.current += 1;
    setDetail(null);
    setError("");
    setNotice("");
    setSelectedId(caseId);
  }

  useEffect(() => {
    Promise.all([refreshCases(), refreshMonitoring()])
      .catch((requestError) => setError(`Não foi possível conectar à API: ${requestError.message}`))
      .finally(() => setLoadingCases(false));
  }, []);

  useEffect(() => {
    if (selectedId) loadDetail(selectedId);
    else setDetail(null);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || loadingDetail || !detail?.documents?.some((document) => ["UPLOADED", "EXTRACTING"].includes(document.status))) return undefined;
    const timer = window.setTimeout(() => loadDetail(selectedId), 2000);
    return () => window.clearTimeout(timer);
  }, [selectedId, detail, loadingDetail]);

  async function runMutation(action, successMessage) {
    const mutationCaseId = selectedCase.current;
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await action();
      if (mutationCaseId) await loadDetail(mutationCaseId);
      await Promise.all([refreshCases(), refreshMonitoring()]);
      if (mutationCaseId === selectedCase.current) setNotice(successMessage);
      return true;
    } catch (requestError) {
      setError(requestError.message);
      return false;
    } finally {
      setSubmitting(false);
    }
  }

  async function createCase(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = {
      case_number: form.get("case_number").trim(),
      uf: form.get("uf").trim().toUpperCase(),
      value_of_claim: form.get("value_of_claim") ? Number(form.get("value_of_claim")) : null,
      sub_subject: form.get("sub_subject").trim() || null,
      dossie_status: "AUSENTE",
    };
    setSubmitting(true);
    setError("");
    try {
      const created = await api("/cases", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      await Promise.all([refreshCases(), refreshMonitoring()]);
      selectCase(created.id);
      formElement.reset();
      setNotice("Caso criado e pronto para receber documentos.");
    } catch (requestError) {
      setError(`Não foi possível criar o caso: ${requestError.message}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function uploadDocument(event) {
    event.preventDefault();
    if (!selectedId) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const file = form.get("file");
    if (!(file instanceof File) || !file.size) {
      setError("Selecione um PDF ou arquivo de texto.");
      return;
    }
    const completed = await runMutation(
      () => api(`/cases/${encodeURIComponent(selectedId)}/documents`, { method: "POST", body: form }),
      "Documento enviado. O processamento documental foi iniciado.",
    );
    if (completed) formElement.reset();
  }

  async function confirmDocumentType(documentId, event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const action = form.get("action");
    const payload = {
      action,
      reason: form.get("reason").trim(),
      ...(action === "RECLASSIFY" ? { document_type: form.get("document_type") } : {}),
    };
    const completed = await runMutation(
      () => api(`/documents/${encodeURIComponent(documentId)}/type-confirmation`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      }),
      "Tratamento da divergência documental registrado.",
    );
    if (completed) formElement.reset();
  }

  async function createDocumentRequest(event) {
    event.preventDefault();
    if (!selectedId) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = {
      document_type: form.get("document_type"),
      hypothesis_key: form.get("hypothesis_key").trim(),
      reason: form.get("reason").trim(),
    };
    const completed = await runMutation(
      () => api(`/cases/${encodeURIComponent(selectedId)}/document-requests`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      }),
      "Pedido de documento enviado ao banco.",
    );
    if (completed) formElement.reset();
  }

  async function respondDocumentRequest(requestId, event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = { status: form.get("status"), reason: form.get("reason").trim() };
    const completed = await runMutation(
      () => api(`/document-requests/${encodeURIComponent(requestId)}/response`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      }),
      "Resposta ao pedido de documento registrada.",
    );
    if (completed) formElement.reset();
  }

  async function analyzeCase() {
    if (!selectedId) return;
    await runMutation(
      () => api(`/cases/${encodeURIComponent(selectedId)}/analyses`, { method: "POST" }),
      "Análise concluída. Revise a recomendação antes de decidir.",
    );
  }

  async function registerDecision(event) {
    event.preventDefault();
    if (!selectedId || !selectedAnalysis) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = {
      action: form.get("action"),
      reason: form.get("reason").trim() || null,
      proposed_value: form.get("proposed_value") ? Number(form.get("proposed_value")) : null,
    };
    const completed = await runMutation(
      () => api(`/cases/${encodeURIComponent(selectedId)}/lawyer-decisions?analysis_id=${encodeURIComponent(selectedAnalysis.id)}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      }),
      "Decisão do advogado registrada para o monitoramento de aderência.",
    );
    if (completed) formElement.reset();
  }

  const documents = detail?.documents || [];
  const requests = detail?.document_requests || [];
  const lawyerDecision = detail?.lawyer_decisions?.[0];

  return <main className="shell">
    <header>
      <div><p className="eyebrow">BANCO UNICAMP · ENTEROS</p><h1>EnterAgree</h1><p>Política de acordos com evidências documentais.</p></div>
      <span className={`connection ${connected ? "online" : "offline"}`}>{connected == null ? "Conectando à API…" : connected ? "API conectada" : "API indisponível"}</span>
    </header>

    {error && <div className="notice error" role="alert">{error}<button onClick={() => setError("")} aria-label="Fechar erro">×</button></div>}
    {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Fechar aviso">×</button></div>}

    <section className="layout">
      <aside className="panel case-list">
        <h2>Novo caso</h2>
        <form onSubmit={createCase}>
          <label>Número do processo<input name="case_number" required minLength="3" placeholder="0000000-00.2026.8.00.0000" /></label>
          <div className="row"><label>UF<input name="uf" required maxLength="2" placeholder="SP" /></label><label>Valor da causa<input name="value_of_claim" type="number" min="0" step="0.01" placeholder="0,00" /></label></div>
          <label>Subassunto<input name="sub_subject" placeholder="Não reconhecimento de empréstimo" /></label>
          <button disabled={submitting}>Criar caso</button>
        </form>
        <h2>Casos</h2>
        <div className="cases">
          {loadingCases && <p className="muted">Carregando casos…</p>}
          {!loadingCases && cases.length === 0 && <p className="muted">Nenhum caso criado.</p>}
          {cases.map((item) => <button key={item.id} className={`case-card ${item.id === selectedId ? "selected" : ""}`} onClick={() => selectCase(item.id)}><strong>{item.case_number}</strong><span>{item.uf} · {money(item.value_of_claim)}</span></button>)}
        </div>
      </aside>

      <section className="workspace">
        {!selectedId ? <div className="empty"><h2>Selecione ou crie um caso</h2><p>Envie os subsídios, execute a análise e registre a decisão jurídica.</p></div> : !detail ? <div className="empty">{loadingDetail ? <h2>Carregando caso…</h2> : <><h2>Não foi possível carregar o caso</h2><button onClick={() => loadDetail(selectedId)}>Tentar novamente</button></>}</div> : <>
          <div className="case-title"><div><p className="eyebrow">PROCESSO</p><h2>{detail.case.case_number}</h2><p>{detail.case.uf} · {detail.case.sub_subject || "Sem subassunto"} · {money(detail.case.value_of_claim)}</p></div><button className="primary" onClick={analyzeCase} disabled={submitting}>Executar análise</button></div>
          <div className="cards">
            <article className="panel"><h3>Documentos</h3><DocumentUploadForm key={selectedId} requests={requests} disabled={submitting} onSubmit={uploadDocument} /><div className="document-list">{documents.length === 0 ? <p className="muted">Ainda não há documentos.</p> : documents.map((document) => <div key={document.id} className="document"><strong>{document.original_filename}</strong><span>{labels[document.declared_type] || document.declared_type} · {document.status} · {document.pages_extracted}/{document.page_count} páginas</span>{document.type_status === "MISMATCH" && <TypeConfirmationForm document={document} disabled={submitting} onSubmit={confirmDocumentType} />}</div>)}</div></article>
            <article className="panel analysis"><h3>Recomendação</h3>{!selectedAnalysis ? <p className="muted">A análise aparecerá aqui após a execução.</p> : <Analysis data={selectedAnalysis} />}</article>
          </div>
          <article className="panel requests"><h3>Pedidos de documentos</h3><DocumentRequestForm key={selectedId} disabled={submitting} onSubmit={createDocumentRequest} />{requests.length === 0 ? <p className="muted">Não há pedidos de documentos.</p> : <div className="document-list">{requests.map((request) => <div className="document" key={request.id}><strong>{labels[request.document_type] || request.document_type}</strong><span>{request.status} · {request.reason}</span>{request.status === "REQUESTED" && <DocumentRequestResponseForm request={request} disabled={submitting} onSubmit={respondDocumentRequest} />}</div>)}</div>}</article>
          <article className="panel decision"><h3>Decisão do advogado</h3>{!selectedAnalysis ? <p className="muted">Execute uma análise para registrar uma decisão vinculada à recomendação.</p> : <form key={selectedAnalysis.id} onSubmit={registerDecision}><div className="row"><label>Ação<select name="action" defaultValue={selectedAnalysis.recommendation}><option value="ACORDO">Acordo</option><option value="DEFESA">Defesa</option></select></label><label>Valor proposto<input name="proposed_value" type="number" min="0" step="0.01" placeholder="Opcional" /></label></div><label>Justificativa<textarea name="reason" rows="3" placeholder="Obrigatória se divergir da recomendação." /></label><button disabled={submitting}>Registrar decisão</button></form>}{lawyerDecision && <p className="registered">Última decisão registrada: {labels[lawyerDecision.action] || lawyerDecision.action}</p>}</article>
        </>}
      </section>
    </section>
    <section className="monitor panel"><div><p className="eyebrow">MONITORAMENTO</p><h2>Resumo da operação</h2></div><Metric label="Análises" value={monitoring?.total_analyses ?? "—"} /><Metric label="Recomendação de acordo" value={monitoring ? monitoring.recommendations?.ACORDO ?? 0 : "—"} /><Metric label="Decisões registradas" value={monitoring?.total_lawyer_decisions ?? "—"} /><Metric label="Aderência" value={percentage(monitoring?.adherence_rate)} /></section>
  </main>;
}

function Analysis({ data }) {
  const targetValue = data.pricing?.target_value;
  return <><div className={`recommendation ${data.recommendation === "ACORDO" ? "agreement" : "defense"}`}><span>Recomendação</span><strong>{labels[data.recommendation] || data.recommendation}</strong></div><p><b>Status documental:</b> {data.documentary_status}</p>{targetValue != null && <p><b>Valor sugerido:</b> {money(targetValue)}</p>}<ul>{(data.reasons || []).map((reason, index) => <li key={index}>{reason}</li>)}</ul>
  <small>Fonte: {data.policy_source} · Código: {data.decision_code}</small></>;
}

function DocumentUploadForm({ requests, disabled, onSubmit }) {
  const [requestId, setRequestId] = useState("");
  const [declaredType, setDeclaredType] = useState("CONTRATO");
  const openRequests = requests.filter((request) => request.status === "REQUESTED");
  const selectedRequest = openRequests.find((request) => request.id === requestId);
  const selectedType = selectedRequest?.document_type || declaredType;

  return <form className="upload" onSubmit={onSubmit} onReset={() => { setRequestId(""); setDeclaredType("CONTRATO"); }}>
    <label>Origem<select name="source_party" defaultValue="BANCO"><option value="BANCO">Banco</option><option value="ADVOGADO_EXTERNO">Advogado externo</option></select></label>
    <label>Pedido vinculado<select name="request_id" value={selectedRequest?.id || ""} onChange={(event) => setRequestId(event.target.value)}><option value="">Nenhum</option>{openRequests.map((request) => <option key={request.id} value={request.id}>{labels[request.document_type] || request.document_type} · {request.reason}</option>)}</select></label>
    {selectedRequest && <input type="hidden" name="declared_type" value={selectedType} />}
    <label>Tipo declarado<select name={selectedRequest ? undefined : "declared_type"} value={selectedType} onChange={(event) => setDeclaredType(event.target.value)} disabled={Boolean(selectedRequest)}>{DOCUMENT_TYPES.map((type) => <option key={type} value={type}>{labels[type]}</option>)}</select></label>
    <label>Arquivo<input name="file" type="file" accept="application/pdf,text/plain,.txt" required /></label>
    <button disabled={disabled}>Enviar documento</button>
  </form>;
}

function TypeConfirmationForm({ document, disabled, onSubmit }) {
  return <form className="inline-form confirmation" onSubmit={(event) => onSubmit(document.id, event)}>
    <small className="warning">O tipo detectado diverge do tipo declarado. Confirme o tratamento.</small>
    <label>Ação<select name="action" defaultValue="CONTINUE_WITH_RESERVATION"><option value="RECLASSIFY">Reclassificar</option><option value="CONTINUE_WITH_RESERVATION">Continuar com ressalva</option><option value="REMOVE">Remover documento</option></select></label>
    <label>Novo tipo (se reclassificar)<select name="document_type" defaultValue={document.detected_type || "OUTRO"}>{DOCUMENT_TYPES.map((type) => <option key={type} value={type}>{labels[type]}</option>)}</select></label>
    <label>Justificativa<textarea name="reason" rows="2" required minLength="3" placeholder="Descreva a confirmação." /></label>
    <button disabled={disabled}>Confirmar tratamento</button>
  </form>;
}

function DocumentRequestForm({ disabled, onSubmit }) {
  return <form className="inline-form request-form" onSubmit={onSubmit}>
    <p className="muted">Solicite ao banco o subsídio necessário para sustentar ou revisar a análise.</p>
    <label>Documento<select name="document_type" defaultValue="CONTRATO">{DOCUMENT_TYPES.filter((type) => type !== "OUTRO").map((type) => <option key={type} value={type}>{labels[type]}</option>)}</select></label>
    <label>Hipótese<input name="hypothesis_key" required minLength="3" placeholder="Ex.: validacao_da_contratacao" /></label>
    <label>Motivo<textarea name="reason" rows="2" required minLength="3" placeholder="Explique por que este documento é necessário." /></label>
    <button disabled={disabled}>Solicitar documento</button>
  </form>;
}

function DocumentRequestResponseForm({ request, disabled, onSubmit }) {
  return <form className="inline-form response-form" onSubmit={(event) => onSubmit(request.id, event)}>
    <label>Resposta<select name="status" defaultValue="DECLARED_UNAVAILABLE"><option value="DECLARED_UNAVAILABLE">Banco declarou indisponível</option><option value="CANCELLED">Cancelar pedido</option></select></label>
    <label>Justificativa<textarea name="reason" rows="2" required minLength="3" placeholder="Informe o motivo." /></label>
    <button disabled={disabled}>Registrar resposta</button>
  </form>;
}

function Metric({ label, value }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }

createRoot(document.getElementById("root")).render(<App />);
