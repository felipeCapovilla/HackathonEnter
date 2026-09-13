import { useEffect, useState } from "react";
import { documentDownloadUrl, request } from "../api";
import { Icon } from "../Brand";
import { DOCUMENTOS, ORDEM_DOCUMENTOS } from "./textos";

function TextoExtraido({ documento }) {
  const [paginas, setPaginas] = useState(null);
  useEffect(() => {
    let ativo = true;
    const total = Math.min(documento.page_count || 1, 20);
    Promise.all(Array.from({ length: total }, (_, index) => request(`/documents/${documento.id}/pages/${index + 1}`).catch(() => null)))
      .then((resultado) => { if (ativo) setPaginas(resultado.filter(Boolean)); });
    return () => { ativo = false; };
  }, [documento.id, documento.page_count]);
  if (!paginas) return <p role="status" className="muted">Carregando texto…</p>;
  return <div className="texto-extraido">{paginas.map((pagina) => <section key={pagina.page_number}><span className="muted">Página {pagina.page_number}</span><p>{pagina.text_content}</p></section>)}</div>;
}

/** Documentos do processo lidos na própria tela: PDF no leitor do navegador, texto para os demais. */
export function VisualizadorDocumentos({ documentos, leituras = [] }) {
  const ordenados = [...documentos].sort((a, b) => ORDEM_DOCUMENTOS.indexOf(a.declared_type) - ORDEM_DOCUMENTOS.indexOf(b.declared_type));
  const [ativoId, setAtivoId] = useState(null);
  const documento = ordenados.find((item) => item.id === ativoId) || ordenados[0];
  if (!documento) {
    return <article className="panel visualizador"><div className="empty-state"><Icon name="files" /><p>Nenhum documento ainda</p><span>Os documentos enviados pela empresa aparecem aqui.</span></div></article>;
  }
  const leitura = leituras.find((item) => item.document_id === documento.id && item.status === "COMPLETED")?.result;
  const pdf = /\.pdf$/i.test(documento.original_filename);
  const pronto = ["COMPLETED", "COMPLETED_WITH_WARNINGS"].includes(documento.status);
  return <article className="panel visualizador">
    <div className="visualizador-abas" role="tablist" aria-label="Documentos do processo">
      {ordenados.map((item) => <button key={item.id} type="button" role="tab" aria-selected={item.id === documento.id}
        className={item.id === documento.id ? "ativa" : ""} onClick={() => setAtivoId(item.id)}>{DOCUMENTOS[item.declared_type] || item.declared_type}</button>)}
    </div>
    {leitura && <div className="visualizador-resumo">
      <p><Icon name="spark" className="tiny" /> <b>{documento.declared_type === "AUTOS" ? "Resumo da petição" : "O que diz"}:</b> {leitura.resumo}</p>
      {leitura.pontos_de_atencao?.length > 0 && <ul>{leitura.pontos_de_atencao.map((ponto, index) => <li key={index}>{ponto}</li>)}</ul>}
    </div>}
    <div className="visualizador-quadro">
      {!pronto ? <p role="status" className="muted">Documento em processamento…</p>
        : pdf ? <iframe key={documento.id} title={documento.original_filename} src={`${documentDownloadUrl(documento.id)}?inline=1`} />
          : <TextoExtraido documento={documento} />}
    </div>
    <div className="visualizador-rodape">
      <span className="muted">{documento.original_filename}{documento.page_count ? ` · ${documento.page_count} página(s)` : ""}</span>
      <a href={documentDownloadUrl(documento.id)} target="_blank" rel="noopener noreferrer">Baixar original</a>
    </div>
  </article>;
}
