import { useEffect, useState } from "react";
import { documentDownloadUrl, request } from "../api";
import { useAction } from "../hooks";
import { Icon } from "../Brand";
import { DOCUMENTOS, ORDEM_DOCUMENTOS } from "./textos";
import { PainelRecolhivel } from "./PainelRecolhivel";

function TextoExtraido({ documento }) {
  const [page, setPage] = useState(1);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const total = Math.max(documento.page_count || 1, 1);
  useEffect(() => {
    const controller = new AbortController();
    setResult(null);
    setError("");
    request(`/documents/${documento.id}/pages/${page}`, { signal: controller.signal })
      .then(setResult)
      .catch((e) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [documento.id, page, attempt]);
  return <div className="text-reader">
    <div className="text-reader-pages" aria-label="Paginação do texto">
      <button type="button" title="Página anterior" aria-label="Página anterior" disabled={page === 1} onClick={() => setPage((value) => value - 1)}><Icon name="chevronLeft" /></button>
      <span>Página {page} de {total}</span>
      <button type="button" title="Próxima página" aria-label="Próxima página" disabled={page >= total} onClick={() => setPage((value) => value + 1)}><Icon name="chevronRight" /></button>
    </div>
    <div className="texto-extraido" tabIndex={0} aria-label={`Texto da página ${page}`}>
      {error ? <div role="alert"><p>{error}</p><button type="button" className="subtle" onClick={() => setAttempt((value) => value + 1)}>Tentar novamente</button></div>
        : !result ? <p role="status">Carregando página…</p>
          : <p>{result.text_content || "Não há texto extraído nesta página."}</p>}
    </div>
  </div>;
}

function documentState(document) {
  if (document.status === "FAILED") return ["danger", "Falha na leitura"];
  if (["UPLOADED", "EXTRACTING"].includes(document.status)) return ["info", "Processando"];
  if (["UNCONFIRMED", "MISMATCH"].includes(document.type_status)) return ["amber", "Tipo a conferir"];
  if (document.status === "COMPLETED_WITH_WARNINGS") return ["amber", "Leitura com ressalvas"];
  return ["success", "Texto disponível"];
}

/** A leitura é uma ação do advogado: a empresa só enxerga o resultado depois. */
function LeituraIA({ documento, leitura, ativa, onGerada }) {
  const action = useAction();
  if (!["COMPLETED", "COMPLETED_WITH_WARNINGS"].includes(documento.status)) return null;
  const gerar = () => action.run(async () => {
    await request(`/documents/${documento.id}/leitura`, { method: "POST" });
    onGerada();
  });
  if (!leitura || leitura.status === "FAILED") return <section className="viewer-summary viewer-ai-action">
    <div><Icon name="spark" /><div><strong>Leitura com IA</strong><p>{leitura?.status === "FAILED" ? `A última tentativa não foi concluída: ${leitura.error || "indisponível"}.` : "Gere um resumo e os pontos de atenção deste documento para apoiar sua análise."}</p></div></div>
    {ativa ? <button type="button" className="subtle" disabled={action.pending} onClick={gerar}>{action.pending ? "Gerando leitura…" : leitura ? "Tentar novamente" : "Gerar leitura com IA"}</button>
      : <p className="muted">Leitura com IA indisponível no momento.</p>}
    {action.error && <p role="alert" className="leitura-alerta">{action.error}</p>}
  </section>;
  const result = leitura.result;
  return <details className="viewer-summary" key={documento.id}><summary><Icon name="spark" />Resumo e pontos de atenção<Icon name="chevronDown" /></summary>
    <p>{result.resumo}</p>
    {result.pontos_de_atencao?.length > 0 && <ul>{result.pontos_de_atencao.map((ponto, position) => <li key={position}>{ponto}</li>)}</ul>}
  </details>;
}

/** Documentos do processo com navegação por abas e estado real de processamento. */
export function VisualizadorDocumentos({ documentos, leituras = [], leituraAtiva = false, onLeituraGerada = () => {}, children }) {
  const ordenados = [...documentos].sort((a, b) => ORDEM_DOCUMENTOS.indexOf(a.declared_type) - ORDEM_DOCUMENTOS.indexOf(b.declared_type));
  const [ativoId, setAtivoId] = useState(null);
  const documento = ordenados.find((item) => item.id === ativoId) || ordenados[0];
  if (!documento) {
    return <PainelRecolhivel group="documents" titulo="Documentos do processo" resumo="Nenhum arquivo enviado" afterHeader={children}>
      <article className="panel visualizador"><div className="empty-state"><Icon name="files" /><p>Nenhum documento ainda</p><span>Os arquivos enviados pela empresa aparecerão aqui.</span></div></article>
    </PainelRecolhivel>;
  }
  const leitura = leituras.find((item) => item.document_id === documento.id && item.status === "COMPLETED")?.result;
  const pdf = /\.pdf$/i.test(documento.original_filename);
  const pronto = ["COMPLETED", "COMPLETED_WITH_WARNINGS"].includes(documento.status);
  const [tone, state] = documentState(documento);
  return <PainelRecolhivel group="documents" titulo="Documentos do processo" resumo={`${documentos.length} arquivo(s) · ${documento.original_filename}`} afterHeader={children}>
    <article className="panel visualizador">
      <div className="visualizador-abas" role="tablist" aria-label="Documentos do processo">
        {ordenados.map((item, index) => <button key={item.id} type="button" role="tab" aria-selected={item.id === documento.id}
          tabIndex={item.id === documento.id ? 0 : -1} title={item.original_filename}
          className={item.id === documento.id ? "ativa" : ""} onClick={() => setAtivoId(item.id)}
          onKeyDown={(event) => {
            const next = { ArrowRight: (index + 1) % ordenados.length, ArrowLeft: (index - 1 + ordenados.length) % ordenados.length, Home: 0, End: ordenados.length - 1 }[event.key];
            if (next == null) return;
            event.preventDefault();
            setAtivoId(ordenados[next].id);
            event.currentTarget.parentElement.querySelectorAll('[role="tab"]')[next].focus();
          }}>{DOCUMENTOS[item.declared_type] || item.declared_type}</button>)}
      </div>
      <div className="viewer-document-meta"><span className={`pill ${tone}`}>{state}</span><span>{DOCUMENTOS[documento.declared_type] || documento.declared_type}{documento.page_count ? ` · ${documento.page_count} página(s)` : ""}</span>
        <a href={documentDownloadUrl(documento.id)} target="_blank" rel="noopener noreferrer"><Icon name="external" />Abrir original</a></div>
      <LeituraIA documento={documento} leitura={leituras.find((item) => item.document_id === documento.id)} ativa={leituraAtiva} onGerada={onLeituraGerada} />
      <div className="visualizador-quadro">
        {documento.status === "FAILED" ? <div className="viewer-state" role="status"><Icon name="files" /><h3>Não foi possível extrair este documento</h3><p>Abra o original para conferir o arquivo ou peça um novo envio à empresa.</p></div>
          : !pronto ? <div className="viewer-state" role="status"><Icon name="clock" /><h3>Preparando a leitura</h3><p>Você pode consultar os outros documentos enquanto este arquivo é processado.</p></div>
            : pdf ? <iframe key={documento.id} title={documento.original_filename} src={`${documentDownloadUrl(documento.id)}?inline=1`} />
              : <TextoExtraido key={documento.id} documento={documento} />}
      </div>
      <div className="visualizador-rodape"><span title={documento.original_filename}>{documento.original_filename}</span>
        <a href={documentDownloadUrl(documento.id)} target="_blank" rel="noopener noreferrer">Baixar</a></div>
    </article>
  </PainelRecolhivel>;
}
