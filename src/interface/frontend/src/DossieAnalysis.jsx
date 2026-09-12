import { useEffect, useRef, useState } from "react";

const verdictLabels = {
  conforme: "Conforme",
  nao_conforme: "Não conforme",
  inconclusivo: "Inconclusivo",
};

const itemLabels = {
  assinatura: "Assinatura",
  documento_identidade: "Documento de identidade",
  comprovante_residencia: "Comprovante de residência",
  liveness: "Prova de vida",
};

const resultLabels = { ok: "OK", falha: "Falha", inconclusivo: "Inconclusivo" };
const signatureLabels = { sim: "Sim", nao: "Não", desconhecido: "Não identificado", conflitante: "Conflitante" };

function percentage(value) {
  return value == null ? "Não informado" : new Intl.NumberFormat("pt-BR", {
    style: "percent", maximumFractionDigits: 1,
  }).format(value);
}

export default function DossieAnalysis({ document, record, disabled, request, apiBase, onCompleted }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [localRecord, setLocalRecord] = useState(null);
  const [evidencePending, setEvidencePending] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");
  const mounted = useRef(false);
  const evidenceRequest = useRef(0);
  const activeRecordId = useRef(null);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    setLocalRecord((current) => current?.id === record?.id ? current : null);
    setError("");
    setEvidenceError("");
    setEvidencePending(false);
    evidenceRequest.current += 1;
  }, [record?.id]);

  const currentRecord = localRecord && record?.id === localRecord.id ? {
    ...record,
    evidencias_carregadas: localRecord.evidencias_carregadas,
    result: record.result ? { ...record.result, evidencias: localRecord.result?.evidencias || [] } : null,
  } : localRecord || record;
  activeRecordId.current = currentRecord?.id;
  const result = currentRecord?.status === "COMPLETED" ? currentRecord.result : null;
  const evidenceLoaded = currentRecord?.evidencias_carregadas !== false;
  const evidenceTotal = currentRecord?.evidencias_total ?? result?.evidencias.length ?? 0;
  const extractionReady = ["COMPLETED", "COMPLETED_WITH_WARNINGS"].includes(document.status);
  const typeBlocked = ["PENDING", "MISMATCH", "REMOVED"].includes(document.type_status);

  async function analyze() {
    if (pending || evidencePending || disabled || !extractionReady || typeBlocked) return;
    setPending(true);
    setError("");
    try {
      const response = await request(`/documents/${encodeURIComponent(document.id)}/dossie-analysis`, { method: "POST" });
      if (!mounted.current) return;
      setLocalRecord(response);
      await onCompleted();
    } catch (requestError) {
      if (mounted.current) setError(`Não foi possível analisar o dossiê: ${requestError.message}`);
    } finally {
      if (mounted.current) setPending(false);
    }
  }

  async function loadEvidence() {
    if (evidencePending || pending || !currentRecord || evidenceLoaded) return;
    const requestedRecordId = currentRecord.id;
    const requestNumber = ++evidenceRequest.current;
    setEvidencePending(true);
    setEvidenceError("");
    try {
      const response = await request(`/documents/${encodeURIComponent(document.id)}/dossie-analysis`);
      if (!mounted.current || requestNumber !== evidenceRequest.current || requestedRecordId !== activeRecordId.current) return;
      setLocalRecord(response);
      if (response.id !== requestedRecordId) await onCompleted();
    } catch (requestError) {
      if (mounted.current && requestNumber === evidenceRequest.current && requestedRecordId === activeRecordId.current) {
        setEvidenceError(`Não foi possível carregar as evidências: ${requestError.message}`);
      }
    } finally {
      if (mounted.current && requestNumber === evidenceRequest.current) setEvidencePending(false);
    }
  }

  return <section className="dossie-analysis" aria-label={`Análise de dossiê: ${document.original_filename}`} aria-busy={pending || evidencePending}>
    <h4>Análise auxiliar do dossiê</h4>
    <p>Ao clicar em Analisar dossiê com IA, o texto extraído deste documento será enviado à OpenAI. A classificação do tipo documental continua determinística, sem LLM.</p>
    <button type="button" onClick={analyze} disabled={disabled || pending || evidencePending || !extractionReady || typeBlocked}>
      {pending ? "Analisando dossiê…" : "Analisar dossiê com IA"}
    </button>
    {!extractionReady && <p className="warning">A análise requer a extração documental concluída. Se a extração falhou, envie uma versão legível do documento.</p>}
    {typeBlocked && <p className="warning">O documento está pendente de classificação, possui divergência de tipo ou foi removido. Resolva o status documental antes de analisar.</p>}
    {pending && <p role="status">Processando o dossiê. A recomendação da política não será alterada automaticamente.</p>}
    {error && <p className="warning" role="alert">{error}</p>}
    {currentRecord?.status === "FAILED" && !error && <p className="warning" role="alert">A análise anterior falhou ({currentRecord.error_code || "erro não informado"}). Você pode tentar novamente.</p>}
    {result && <div className="dossie-result">
      <p><b>Veredito do dossiê:</b> {verdictLabels[result.analise.veredito] || result.analise.veredito}</p>
      <p><b>Arquivo de dossiê disponível:</b> {result.docie_existe ? "Sim" : "Não"}. A existência do arquivo não confirma seu conteúdo.</p>
      <p><b>O dossiê examinou a assinatura do contrato:</b> {signatureLabels[result.assinatura_contrato_status] || (result.analise.analisou_assinatura_contrato ? "Sim" : "Não identificado")}</p>
      <p><b>Contrato referenciado:</b> {result.analise.numero_contrato_referenciado || "Não informado"}</p>
      <ul className="dossie-items">{result.analise.itens.map((item, index) => <li key={`${item.tipo}-${index}`}>
        <b>{itemLabels[item.tipo] || item.tipo}:</b> {resultLabels[item.resultado] || item.resultado} · Índice reportado: {percentage(item.indice)}
      </li>)}</ul>
      <p><b>Confiança da extração:</b> {result.analise.confianca_extracao === 0 ? "Não calibrada" : percentage(result.analise.confianca_extracao)}. Não é confiança jurídica nem probabilidade de êxito.</p>
      <p><b>Cobertura:</b> {result.paginas_processadas} páginas e {result.trechos_processados} trechos processados.</p>
      {!result.completo && <p className="warning">Análise incompleta ou com inconsistências. Consulte os avisos; não use este resultado como validação integral.</p>}
      {result.avisos.length > 0 && <div><h5>Avisos da análise</h5><ul>{result.avisos.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}
      <div className="dossie-evidence"><h5>Evidências no documento</h5>
        {!evidenceLoaded && evidenceTotal > 0 ? <>
          <p>{evidenceTotal} evidências disponíveis. Carregue os trechos salvos somente quando necessário, sem nova chamada à OpenAI.</p>
          <button type="button" onClick={loadEvidence} disabled={disabled || evidencePending || pending}>
            {evidencePending ? "Carregando evidências…" : "Carregar evidências"}
          </button>
        </> : result.evidencias.length === 0 ? <p>Nenhuma evidência referenciada. Revise o documento original.</p> : result.evidencias.map((evidence, index) => <div key={`${evidence.campo}-${evidence.pagina}-${index}`}>
          <p><b>{evidence.campo}:</b> {evidence.valor}</p>
          <blockquote>{evidence.trecho}</blockquote>
          <a href={`${apiBase}/documents/${encodeURIComponent(document.id)}/pages/${encodeURIComponent(evidence.pagina)}`} target="_blank" rel="noopener noreferrer">Página {evidence.pagina} (texto extraído)</a>
        </div>)}
        {evidenceError && <p className="warning" role="alert">{evidenceError}</p>}
      </div>
      <small>Modelo: {currentRecord.model}. Resultado persistido; novas consultas reutilizam a análise concluída.</small>
    </div>}
    <p className="muted">Resultado auxiliar sujeito à revisão humana. Não autentica assinaturas e não altera automaticamente a recomendação do XGBoost ou da política G9.</p>
  </section>;
}
