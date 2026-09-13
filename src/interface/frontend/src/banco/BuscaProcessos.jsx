import { useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api";
import { useAction } from "../hooks";
import { Notice } from "./ui";
import { brl } from "./format";
import "./banco.css";

function Destaque({ texto, termo }) {
  const posicao = texto.toLocaleLowerCase("pt-BR").indexOf(termo.toLocaleLowerCase("pt-BR"));
  if (!termo || posicao < 0) return texto;
  return <>{texto.slice(0, posicao)}<mark>{texto.slice(posicao, posicao + termo.length)}</mark>{texto.slice(posicao + termo.length)}</>;
}

/** Painel de busca da empresa: número do processo, número do contrato ou nome da parte. */
export function BuscaProcessos() {
  const action = useAction();
  const [resultado, setResultado] = useState(null);
  const buscar = (event) => {
    event.preventDefault();
    const termo = String(new FormData(event.currentTarget).get("q") || "").trim();
    action.run(async () => {
      if (termo.length < 3) throw new Error("Digite ao menos 3 caracteres para buscar.");
      setResultado({ termo, itens: await request(`/bank/search?q=${encodeURIComponent(termo)}`) });
    });
  };
  return <article className="panel full-width busca-processos">
    <div className="panel-heading"><div><h2>Buscar processo</h2><p>Pelo número do contrato, do processo ou pelo nome da parte. A busca olha o cadastro, a leitura da IA e o texto de cada documento.</p></div></div>
    <form className="busca-form" onSubmit={buscar} role="search">
      <input name="q" type="search" placeholder="Ex.: 502348719 ou Maria da Silva" aria-label="Termo da busca" minLength="3" />
      <button disabled={action.pending}>{action.pending ? "Buscando…" : "Buscar"}</button>
    </form>
    <Notice message={action.error} />
    {resultado && (resultado.itens.length ? <ul className="busca-resultados">
      {resultado.itens.map((item) => <li key={item.case_id}>
        <div className="busca-cabecalho"><Link to={`/banco/casos/${item.case_id}`}>{item.case_number}</Link><span className="muted">{item.uf} · {brl(item.value_of_claim)}</span></div>
        {item.matches.map((match, index) => <p key={index}><b>{match.onde}:</b> <Destaque texto={match.trecho} termo={resultado.termo} /></p>)}
      </li>)}
    </ul> : <p className="empty-line">Nada encontrado para “{resultado.termo}”.</p>)}
  </article>;
}
