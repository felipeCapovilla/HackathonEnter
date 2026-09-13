import { brl } from "./format";
import "./banco.css";

/**
 * Como o processo terminou, em dinheiro, para a empresa.
 * Sentença desfavorável mostra quanto a empresa perdeu e compara com o acordo que a política recomendava.
 */
export function ResultadoProcesso({ detail, decision, recommendation }) {
  if (!decision?.outcome) return null;
  const sentenca = detail.judicial_outcomes?.[0];
  const acordo = detail.negotiation_outcomes?.find((item) => item.status === "ACEITO");
  // Só valores observados: o que foi pago e quanto processos parecidos custaram de fato na base.
  const parecidos = recommendation?.pricing?.similar_cases_cost ?? recommendation?.policy_output?.custo_parecidos;
  const contexto = parecidos != null && <p className="muted">Processos parecidos custaram em média {brl(parecidos, true)} na base histórica.</p>;

  if (decision.outcome === "SENTENCA_DESFAVORAVEL") {
    return <article className="panel resultado-processo perda">
      <p className="eyebrow">Resultado do processo</p>
      <h3>Sentença desfavorável</h3>
      {sentenca?.condemnation_value == null ? <p className="muted">O advogado não informou o valor da condenação.</p>
        : <p className="resultado-valor">A empresa foi condenada a pagar <strong>{brl(sentenca.condemnation_value, true)}</strong></p>}
      {contexto}
    </article>;
  }
  if (decision.outcome === "ACORDO_ACEITO") {
    const fechado = acordo?.closed_value ?? decision.proposed_value;
    return <article className="panel resultado-processo ganho">
      <p className="eyebrow">Resultado do processo</p>
      <h3>Acordo fechado</h3>
      {fechado != null && <p className="resultado-valor">Fechado por <strong>{brl(fechado, true)}</strong></p>}
      {contexto}
    </article>;
  }
  if (decision.outcome === "SENTENCA_FAVORAVEL") {
    return <article className="panel resultado-processo ganho"><p className="eyebrow">Resultado do processo</p><h3>Sentença favorável</h3><p>A empresa venceu: não há condenação a pagar.</p>{contexto}</article>;
  }
  return <article className="panel resultado-processo"><p className="eyebrow">Resultado do processo</p><h3>Acordo recusado</h3><p>O autor não aceitou a proposta.</p></article>;
}
