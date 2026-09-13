import { Icon } from "../Brand";
import { PainelRecolhivel } from "./PainelRecolhivel";
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

function Faixa({ pricing }) {
  const meta = pricing.target_value > pricing.opening_value + 0.01;
  return <div className="faixa">
    {pricing.negotiable === false ? <div><span>Valor único para propor</span><strong>{moeda(pricing.target_value)}</strong></div> : <>
      <div><span>Comece em</span><strong>{moeda(pricing.opening_value)}</strong></div>
      {meta && <div><span>Meta</span><strong>{moeda(pricing.target_value)}</strong></div>}
      <div><span>Pode subir até</span><strong>{moeda(pricing.walk_away_value)}</strong></div>
    </>}
    <p className="muted">Acima de {moeda(pricing.walk_away_value)}, defender sai mais barato: a defesa custaria {moeda(pricing.expected_defense_cost)}, em média.</p>
  </div>;
}

export function Recomendacao({ recomendacao, precisaAvaliar, onAvaliar, ocupado }) {
  if (!recomendacao) {
    return <PainelRecolhivel group="evaluation" titulo="Recomendação" resumo="Ainda não avaliado"><article className="panel recomendacao">
      <h3>Ainda não avaliado</h3>
      <p className="muted">Quando os documentos estiverem no processo, peça a avaliação: a política calcula o caminho mais barato para a empresa.</p>
      <button className="primary" disabled={ocupado} onClick={onAvaliar}><Icon name="spark" />{ocupado ? "Avaliando…" : "Avaliar o processo"}</button>
    </article></PainelRecolhivel>;
  }
  const po = recomendacao.policy_output || {};
  const acao = recomendacao.recommendation;
  const plano = po.recuperacao;
  return <PainelRecolhivel group="evaluation" titulo="Recomendação" resumo={ACOES[acao]?.titulo || acao}><article className={`panel recomendacao acao-${acao.toLowerCase()}`}>
    {precisaAvaliar && <p className="recommendation-stale"><Icon name="clock" />Há documentos novos. Reavalie antes de decidir.</p>}
    <h3 className="display">{ACOES[acao]?.titulo || acao}</h3>
    {po.p_perda != null && <Risco p={po.p_perda} limiar={po.p_estrela} segmento={po.segmento} />}
    {acao !== "DEFESA" && recomendacao.pricing?.target_value != null && <Faixa pricing={recomendacao.pricing} />}
    {acao === "RECUPERAR" && plano && <p className="plano">Peça o <b>{DOCUMENTOS[DOCUMENTO_DO_PLANO[plano.documento]] || plano.documento}</b>. {plano.fundamento} Se ele chegar, a economia esperada é de {moeda(plano.ganho_estimado)}.</p>}
    {recomendacao.limitations?.length > 0 && <ul className="ressalvas">{recomendacao.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>}
    <details className="como-chegamos"><summary>Como chegamos nisso</summary><ul>{recomendacao.reasons.map((item, index) => <li key={index}>{item}</li>)}</ul></details>
    {precisaAvaliar && <button className="primary" disabled={ocupado} onClick={onAvaliar}><Icon name="spark" />{ocupado ? "Avaliando…" : "Reavaliar com os documentos novos"}</button>}
  </article></PainelRecolhivel>;
}
