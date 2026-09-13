import { Link } from "react-router-dom";
import { useResource } from "../hooks";
import { Icon } from "../Brand";
import { ACOES, TOM_DA_FASE, moeda } from "./textos";
import "./advogado.css";

function ItemDaFila({ item }) {
  const { fase } = item;
  return <li>
    <Link className="fila-item" to={`/advogado/casos/${item.id}`}>
      <span className="fila-principal">
        <strong>{item.case_number}</strong>
        <span className="muted">{item.uf} · {moeda(item.value_of_claim)}{item.document_count ? ` · ${item.document_count} documento(s)` : ""}</span>
      </span>
      <span className="fila-acao">
        <span className={`pill ${TOM_DA_FASE[fase.codigo]} dot`}>{fase.rotulo}</span>
        <b>{fase.proxima_acao}</b>
        {fase.recomendacao && fase.codigo !== "ENCERRADO" && <span className="muted">Recomendação: {ACOES[fase.recomendacao]?.titulo}</span>}
        {fase.documentos_novos && <span className="pill amber">Documentos novos</span>}
      </span>
      <Icon name="arrow" />
    </Link>
  </li>;
}

function Grupo({ titulo, itens, vazio }) {
  return <section className="fila-grupo">
    {titulo && <h3>{titulo} <span className="muted">{itens.length}</span></h3>}
    {itens.length ? <ul className="fila-lista">{itens.map((item) => <ItemDaFila key={item.id} item={item} />)}</ul>
      : <p className="muted">{vazio}</p>}
  </section>;
}

/** Tela inicial do advogado: o que precisa dele agora, o que está andando e o que já acabou. */
export function MinhaFila({ desempenho }) {
  const fila = useResource("/lawyer/queue");
  const itens = fila.data || [];
  const agora = itens.filter((item) => item.fase.prioridade <= 3);
  const andamento = itens.filter((item) => item.fase.prioridade > 3 && item.fase.codigo !== "ENCERRADO");
  const encerrados = itens.filter((item) => item.fase.codigo === "ENCERRADO");
  return <section className="workspace fila-advogado">
    {desempenho}
    <article className="panel">
      <div className="panel-heading">
        <span className="panel-icon"><Icon name="clock" /></span>
        <div><h2>Minha fila</h2><p>Seus processos na ordem do que precisa de você.</p></div>
        <span className="count-badge">{agora.length} para agora</span>
      </div>
      {fila.error && <div className="warning" role="alert"><p>{fila.error}</p><button type="button" onClick={fila.reload}>Tentar novamente</button></div>}
      {fila.loading && <p role="status">Carregando sua fila…</p>}
      {fila.data && <>
        <Grupo titulo="Precisa de você agora" itens={agora} vazio="Nada pendente com você agora." />
        <Grupo titulo="Andando" itens={andamento} vazio="Nenhum processo esperando o autor, a empresa ou a Justiça." />
        {encerrados.length > 0 && <details className="fila-encerrados"><summary>Encerrados ({encerrados.length})</summary><Grupo itens={encerrados} vazio="" /></details>}
      </>}
    </article>
  </section>;
}
