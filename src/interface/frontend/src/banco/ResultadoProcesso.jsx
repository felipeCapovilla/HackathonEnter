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
  const meta = recommendation?.pricing?.target_value;
  const custoDefesa = recommendation?.pricing?.expected_defense_cost ?? recommendation?.policy_output?.custo_esperado_defesa;

  if (decision.outcome === "SENTENCA_DESFAVORAVEL") {
    const perdido = sentenca?.condemnation_value;
    return <article className="panel resultado-processo perda">
      <p className="eyebrow">Resultado do processo</p>
      <h3>Sentença desfavorável</h3>
      {perdido == null ? <p className="muted">O advogado não informou o valor da condenação.</p> : <>
        <p className="resultado-valor">A empresa foi condenada a pagar <strong>{brl(perdido, true)}</strong></p>
        {recommendation?.recommendation === "ACORDO" && meta != null && <p>A política recomendava acordo com meta de {brl(meta, true)}.
          {perdido > meta ? <> A sentença custou <strong>{brl(perdido - meta, true)}</strong> a mais do que o acordo.</> : " A condenação ficou abaixo da meta de acordo."}</p>}
        {recommendation?.recommendation === "DEFESA" && <p>A política indicava defesa para este caso: o risco de perder era baixo.</p>}
      </>}
    </article>;
  }
  if (decision.outcome === "ACORDO_ACEITO") {
    const fechado = acordo?.closed_value ?? decision.proposed_value;
    return <article className="panel resultado-processo ganho">
      <p className="eyebrow">Resultado do processo</p>
      <h3>Acordo fechado</h3>
      {fechado != null && <p className="resultado-valor">Fechado por <strong>{brl(fechado, true)}</strong></p>}
      {fechado != null && custoDefesa != null && custoDefesa > fechado && <p>Defender custaria {brl(custoDefesa, true)}, em média: economia de <strong>{brl(custoDefesa - fechado, true)}</strong>.</p>}
    </article>;
  }
  if (decision.outcome === "SENTENCA_FAVORAVEL") {
    return <article className="panel resultado-processo ganho"><p className="eyebrow">Resultado do processo</p><h3>Sentença favorável</h3><p>A empresa venceu: não há condenação a pagar.</p></article>;
  }
  return <article className="panel resultado-processo"><p className="eyebrow">Resultado do processo</p><h3>Acordo recusado</h3><p>O autor não aceitou a proposta.</p></article>;
}
