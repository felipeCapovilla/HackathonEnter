import { Icon } from "../Brand";
import { ACOES, DOCUMENTOS, DOCUMENTO_DO_PLANO, descreverCaso, frequencia, moeda, nivelDeRisco } from "./textos";

function Risco({ p, limiar, segmento }) {
  const cheios = Math.round(p * 10);
  const caso = descreverCaso(segmento);
  return <div className="risco">
    <div className="risco-topo"><span>Chance de a empresa perder</span><strong className={`risco-${nivelDeRisco(p).replace(" ", "-")}`}>{nivelDeRisco(p)}</strong></div>
    <div className="risco-escala" role="img" aria-label={`A empresa perde ${frequencia(p)} casos parecidos`}>
      {Array.from({ length: 10 }, (_, index) => <span key={index} className={index < cheios ? "cheio" : ""} />)}
    </div>
    <p className="muted">Em casos parecidos{caso ? ` (${caso})` : ""}, a empresa perde {frequencia(p)}. O acordo passa a compensar a partir de {frequencia(limiar)}.</p>
  </div>;
}

function Valores({ pricing }) {
  const recomendado = pricing.recommended_value ?? pricing.target_value;
  return <div className="valores">
    <div className="valor-recomendado">
      <span>Ofereça</span>
      <strong>{moeda(recomendado)}</strong>
      {pricing.acceptance_chance != null && <small>Chance estimada de o autor aceitar: {Math.round(pricing.acceptance_chance * 100)}%</small>}
    </div>
    {pricing.market_low != null && <div className="faixa-mercado"><span>Acordos parecidos fecham entre</span><b>{moeda(pricing.market_low)} e {moeda(pricing.market_high)}</b></div>}
    <p className="limite"><Icon name="lock" /><span>Acima de <b>{moeda(pricing.walk_away_value)}</b>, acordo não compensa: defender sai mais barato.</span></p>
  </div>;
}

export function Recomendacao({ recomendacao, precisaAvaliar, onAvaliar, ocupado }) {
  if (!recomendacao) {
    return <article className="panel recomendacao">
      <span className="pill amber"><Icon name="spark" />Recomendação</span>
      <h3>{ocupado ? "Calculando a recomendação…" : "Aguardando documentos"}</h3>
      <p className="muted">{ocupado ? "A política está analisando os documentos deste processo." : "A recomendação aparece sozinha assim que a empresa enviar os documentos do processo."}</p>
    </article>;
  }
  const po = recomendacao.policy_output || {};
  const acao = recomendacao.recommendation;
  const plano = po.recuperacao;
  return <article className={`panel recomendacao acao-${acao.toLowerCase()}`}>
    <span className="pill amber"><Icon name="spark" />Recomendação da política</span>
    <h3 className="display">{ACOES[acao]?.titulo || acao}</h3>
    {po.p_perda != null && <Risco p={po.p_perda} limiar={po.p_estrela} segmento={po.segmento} />}
    {acao !== "DEFESA" && recomendacao.pricing?.target_value != null && <Valores pricing={recomendacao.pricing} />}
    {po.argumentos?.length > 0 && <div className="argumentos"><h4>Por que este caminho</h4><ul>{po.argumentos.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
    {acao === "RECUPERAR" && plano && <p className="plano">Peça o <b>{DOCUMENTOS[DOCUMENTO_DO_PLANO[plano.documento]] || plano.documento}</b>. {plano.fundamento} Se ele chegar, a economia esperada é de {moeda(plano.ganho_estimado)}.</p>}
    {recomendacao.limitations?.length > 0 && <ul className="ressalvas">{recomendacao.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>}
    <details className="como-chegamos"><summary>Como chegamos nisso</summary><ul>{recomendacao.reasons.map((item, index) => <li key={index}>{item}</li>)}</ul></details>
    {precisaAvaliar && <button className="primary" disabled={ocupado} onClick={onAvaliar}><Icon name="spark" />{ocupado ? "Avaliando…" : "Reavaliar com os documentos novos"}</button>}
  </article>;
}
