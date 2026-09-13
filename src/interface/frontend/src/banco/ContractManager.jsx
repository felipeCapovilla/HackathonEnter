import { useState } from "react";
import { sendJson } from "../api";
import { useAction, useResource } from "../hooks";
import { Kpi, Notice, SectionHeader } from "./ui";
import { brlCompact, date, num, pct } from "./format";

const HONORARIOS = [
  ["honorario_defesa_ganha", "Honorário se a defesa ganhar"],
  ["honorario_defesa_perdida", "Honorário se a defesa perder"],
  ["honorario_acordo", "Honorário por acordo fechado"],
];
const TIPOS_HONORARIO = [["fixo", "R$ fixo"], ["percentual_valor_causa", "% do valor da causa"], ["percentual_condenacao", "% da condenação"]];
const percent = (value) => value == null ? "" : Number((value * 100).toFixed(4));
const initialValue = (honorario) => honorario.tipo === "fixo" ? honorario.valor : percent(honorario.valor);

function readContractForm(form) {
  const honorario = (key) => {
    const tipo = form.get(`${key}.tipo`);
    const bruto = Number(form.get(`${key}.valor`) || 0);
    return { tipo, valor: tipo === "fixo" ? bruto : bruto / 100 };
  };
  const teto = form.get("teto_alcada_fator");
  return {
    honorario_defesa_ganha: honorario("honorario_defesa_ganha"),
    honorario_defesa_perdida: honorario("honorario_defesa_perdida"),
    honorario_acordo: honorario("honorario_acordo"),
    custo_mensal_tempo: Number(form.get("custo_mensal_tempo") || 0) / 100,
    duracao_meses: Number(form.get("duracao_meses") || 0),
    teto_alcada_fator: teto ? Number(teto) / 100 : null,
    concessao: Number(form.get("concessao") || 0) / 100,
  };
}

export function ContractManager({ user }) {
  const firms = useResource("/bank/law-firms");
  const [firmId, setFirmId] = useState("");
  const query = firmId ? `?law_firm_id=${encodeURIComponent(firmId)}` : "";
  const contract = useResource(`/bank/contract${query}`);
  const simulate = useAction();
  const save = useAction();
  const [preview, setPreview] = useState(null);
  const [formKey, setFormKey] = useState(null);
  const [saved, setSaved] = useState("");
  const canEdit = Boolean(user.is_manager);
  const record = contract.data;
  const parameters = record?.parameters;
  const previewMatches = Boolean(preview) && (formKey === null || formKey === preview.key);

  const reset = () => { setPreview(null); setFormKey(null); setSaved(""); };
  const onChange = (event) => {
    setFormKey(JSON.stringify(readContractForm(new FormData(event.currentTarget))));
    setSaved("");
  };
  const onSimulate = (event) => {
    const params = readContractForm(new FormData(event.currentTarget.form));
    simulate.run(async () => setPreview({ key: JSON.stringify(params), data: await sendJson(`/bank/contract/preview${query}`, params) }));
  };
  const onSave = (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const params = readContractForm(form);
    save.run(async () => {
      const result = await sendJson(`/bank/contract${query}`, { parametros: params, justificativa: String(form.get("justificativa") || "").trim() });
      reset();
      setSaved(`Versão V${result.version} gravada. Vale para as próximas análises.`);
      contract.reload();
    });
  };
  const status = !record ? "" : record.inherited_from_bank
    ? `SEM CONTRATO PRÓPRIO · VALE O PADRÃO DA EMPRESA${record.version ? ` (V${record.version})` : ""}`
    : record.version === 0 ? "CONTRATO PADRÃO · NENHUMA VERSÃO CADASTRADA" : `VERSÃO VIGENTE · V${record.version} · ${date(record.created_at)}`;

  return <div className="bank-stack">
    <SectionHeader eyebrow="CONTRATO COM OS ESCRITÓRIOS" title="Os números que o motor usa">
      Honorários, custo do tempo, alçada e concessão mudam a fronteira entre acordar e defender. Cada escritório pode ter contrato próprio; sem ele, vale o padrão da empresa.
    </SectionHeader>
    {!canEdit && <div className="bank-notice info">Somente o gestor da empresa altera o contrato. Você vê a versão vigente.</div>}
    <article className="panel contract-manager">
      <label>Contrato de<select value={firmId} onChange={(event) => { setFirmId(event.target.value); reset(); }} disabled={firms.loading}>
        <option value="">Padrão da empresa</option>
        {(firms.data || []).map((firm) => <option key={firm.id} value={firm.id}>{firm.name}</option>)}
      </select></label>
      <Notice message={firms.error} onRetry={firms.reload} />
      <Notice message={contract.error} onRetry={contract.reload} />
      {contract.loading && <p role="status">Carregando contrato…</p>}
      {record && <p className="eyebrow">{status}</p>}
      {record?.justification && !record.inherited_from_bank && <p className="footnote"><b>Justificativa desta versão:</b> {record.justification}</p>}
      {parameters && <form key={`${firmId}-${record.version}-${record.inherited_from_bank}`} onSubmit={onSave} onChange={onChange}>
        <fieldset className="form-fields" disabled={!canEdit || save.pending || simulate.pending}>
          {HONORARIOS.map(([key, label]) => <div className="contract-row" key={key}>
            <label>{label}<select name={`${key}.tipo`} defaultValue={parameters[key].tipo}>{TIPOS_HONORARIO.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
            <label>Valor (R$ ou %)<input name={`${key}.valor`} type="number" min="0" step="0.01" defaultValue={initialValue(parameters[key])} /></label>
          </div>)}
          <div className="contract-row">
            <label>Custo do tempo (% ao mês)<input name="custo_mensal_tempo" type="number" min="0" max="10" step="0.1" defaultValue={percent(parameters.custo_mensal_tempo)} /></label>
            <label>Duração esperada (meses)<input name="duracao_meses" type="number" min="0" max="120" step="1" defaultValue={parameters.duracao_meses} /></label>
          </div>
          <div className="contract-row">
            <label>Teto de alçada (% da causa, opcional)<input name="teto_alcada_fator" type="number" min="1" max="100" step="1" defaultValue={percent(parameters.teto_alcada_fator)} /></label>
            <label>Concessão na negociação (% do espaço até o valor máximo)<input name="concessao" type="number" min="0" max="100" step="1" defaultValue={percent(parameters.concessao)} /></label>
          </div>
          {canEdit && <label>Justificativa da nova versão<textarea name="justificativa" minLength="10" maxLength="1000" required placeholder="Ex.: aditivo assinado em 09/2026 reduziu o honorário por acordo fechado." /></label>}
          {canEdit && <div className="contract-row">
            <button type="button" className="ghost" onClick={onSimulate}>{simulate.pending ? "Simulando…" : "Simular impacto na carteira"}</button>
            <button disabled={!previewMatches}>{save.pending ? "Salvando…" : "Salvar nova versão"}</button>
          </div>}
          {canEdit && !previewMatches && <p className="footnote">Simule o impacto antes de salvar. Se mudar algum valor, simule de novo.</p>}
        </fieldset>
      </form>}
      <Notice message={simulate.error} />
      <Notice message={save.error} />
      {saved && <p className="registered">{saved}</p>}
    </article>
    {preview && <article className="panel">
      <h3>Impacto simulado na base histórica</h3>
      <div className="kpi-grid">
        <Kpi label="Decisões que mudam" value={`${num(preview.data.decisoes_alteradas)} de ${num(preview.data.casos)}`} />
        <Kpi label="Economia · contrato vigente" value={pct(preview.data.contrato_vigente.economia_percentual)} hint={brlCompact(preview.data.contrato_vigente.economia)} />
        <Kpi tone={preview.data.contrato_proposto.economia >= preview.data.contrato_vigente.economia ? "good" : "bad"} label="Economia · contrato proposto"
          value={pct(preview.data.contrato_proposto.economia_percentual)} hint={brlCompact(preview.data.contrato_proposto.economia)} />
      </div>
      <p className="footnote">{preview.data.premissas}</p>
    </article>}
  </div>;
}
