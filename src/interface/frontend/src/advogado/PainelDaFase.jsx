import { useState } from "react";
import { sendJson } from "../api";
import { useAction } from "../hooks";
import { Icon } from "../Brand";
import { ResultadoProcesso } from "../banco/ResultadoProcesso";
import { PainelRecolhivel } from "./PainelRecolhivel";
import { ACOES, DOCUMENTOS, DOCUMENTO_DO_PLANO, MOTIVOS_DIVERGENCIA, data, moeda } from "./textos";

function Erro({ mensagem }) {
  return mensagem ? <div className="warning" role="alert"><p>{mensagem}</p></div> : null;
}

/** Só aparece quando a escolha foge da recomendação ou do valor máximo. */
function Motivo({ titulo, motivo, setMotivo }) {
  return <fieldset className="motivo">
    <legend>{titulo}</legend>
    <div className="motivo-opcoes">{MOTIVOS_DIVERGENCIA.map(([valor, texto]) => <label key={valor} className={motivo === valor ? "marcado" : ""}>
      <input type="radio" name="divergence_reason" value={valor} checked={motivo === valor} onChange={() => setMotivo(valor)} required />{texto}
    </label>)}</div>
    <label>Detalhe {motivo === "OUTRO" ? "(obrigatório)" : "(opcional)"}<textarea name="reason" maxLength="2000" required={motivo === "OUTRO"} /></label>
  </fieldset>;
}

function FormDecisao({ caseId, recomendacao, onChange }) {
  const acao = useAction();
  const pricing = recomendacao.pricing;
  const [escolha, setEscolha] = useState(recomendacao.recommendation);
  const [valor, setValor] = useState(pricing?.recommended_value ?? pricing?.opening_value ?? "");
  const [motivo, setMotivo] = useState("");
  const maximo = pricing?.walk_away_value;
  const acima = escolha === "ACORDO" && maximo != null && Number(valor) > maximo + 0.01;
  const diverge = escolha !== recomendacao.recommendation;
  const planoDoc = DOCUMENTO_DO_PLANO[recomendacao.policy_output?.recuperacao?.documento];
  const enviar = (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    acao.run(async () => {
      await sendJson(`/cases/${caseId}/lawyer-decisions?analysis_id=${recomendacao.id}`, {
        action: escolha,
        proposed_value: escolha === "ACORDO" ? Number(valor) : null,
        divergence_reason: diverge || acima ? motivo || null : null,
        reason: String(form.get("reason") || "").trim() || null,
        requested_document: escolha === "RECUPERAR" ? form.get("documento") : null,
      });
      onChange();
    });
  };
  return <article className="panel decisao-advogado">
    <div className="panel-heading"><span className="panel-icon"><Icon name="check" /></span><div><h3>Sua decisão</h3><p>Seguir a recomendação não precisa de justificativa.</p></div></div>
    <form onSubmit={enviar}><fieldset className="form-fields" disabled={acao.pending}>
      <div className="opcoes-acao" role="radiogroup" aria-label="Decisão">
        {Object.entries(ACOES).map(([codigo, item]) => <label key={codigo} className={`opcao-acao ${escolha === codigo ? "marcada" : ""}`}>
          <input type="radio" name="action" value={codigo} checked={escolha === codigo} onChange={() => setEscolha(codigo)} />
          <span><b>{item.titulo}</b>{codigo === recomendacao.recommendation && <span className="pill amber">Recomendado</span>}<small>{item.ajuda}</small></span>
        </label>)}
      </div>
      {escolha === "ACORDO" && <label>Valor da proposta
        <input type="number" min="1" step="0.01" required value={valor} onChange={(event) => setValor(event.target.value)} />
        {pricing && <small className="muted">Recomendado: {moeda(pricing.recommended_value ?? pricing.opening_value)}{pricing.market_low != null ? `. Acordos parecidos fecham entre ${moeda(pricing.market_low)} e ${moeda(pricing.market_high)}` : ""}. Acima de {moeda(maximo)}, acordo não compensa.</small>}
      </label>}
      {acima && <p className="alerta-valor">Esse valor passa do máximo ({moeda(maximo)}): defender sai mais barato para a empresa.</p>}
      {escolha === "RECUPERAR" && <label>Documento a pedir à empresa
        <select name="documento" defaultValue={planoDoc || "CONTRATO"}>{["CONTRATO", "EXTRATO", "COMPROVANTE_CREDITO"].map((codigo) => <option key={codigo} value={codigo}>{DOCUMENTOS[codigo]}</option>)}</select>
      </label>}
      {(diverge || acima) && <Motivo titulo={acima && !diverge ? "Por que propor acima do valor máximo?" : "Por que decidir diferente da recomendação?"} motivo={motivo} setMotivo={setMotivo} />}
      <Erro mensagem={acao.error} />
      <button className="primary">{acao.pending ? "Registrando…" : "Registrar decisão"}</button>
    </fieldset></form>
  </article>;
}

function Roteiro({ caseId, decisao, pricing }) {
  const acao = useAction();
  const [mensagem, setMensagem] = useState(null);
  const [copiado, setCopiado] = useState(false);
  const gerar = () => acao.run(async () => {
    setMensagem(await sendJson(`/cases/${caseId}/mensagem-proposta`, { valor: decisao.proposed_value }));
    setCopiado(false);
  });
  const maximo = pricing?.walk_away_value;
  return <article className="panel roteiro">
    <div className="panel-heading"><span className="panel-icon"><Icon name="scale" /></span><div><h3>Roteiro da negociação</h3><p>O que fazer até o autor responder.</p></div></div>
    <ol className="roteiro-passos">
      <li>Ofereça <b>{moeda(decisao.proposed_value)}</b>.</li>
      {pricing?.market_low != null && <li>Acordos parecidos fecham entre {moeda(pricing.market_low)} e {moeda(pricing.market_high)}.</li>}
      {maximo != null && <li>Se o autor pedir mais, você pode aceitar até <b>{moeda(maximo)}</b>.</li>}
      {maximo != null && <li><b>Acima de {moeda(maximo)}, acordo não compensa:</b> defender sai mais barato para a empresa.</li>}
      <li>Sem resposta em 7 dias, cobre o autor. Registre abaixo tudo o que ele responder.</li>
    </ol>
    <button type="button" className="subtle" disabled={acao.pending} onClick={gerar}><Icon name="spark" />{acao.pending ? "Redigindo…" : "Gerar mensagem de proposta"}</button>
    <Erro mensagem={acao.error} />
    {mensagem && <div className="mensagem-proposta">
      <textarea readOnly value={mensagem.mensagem} rows={9} />
      <div className="mensagem-rodape"><span className="muted">{mensagem.fonte === "IA" ? "Redigida com IA a partir do modelo; confira antes de enviar." : "Modelo pronto com os valores deste processo."}</span>
        <button type="button" onClick={() => navigator.clipboard?.writeText(mensagem.mensagem).then(() => setCopiado(true))}>{copiado ? "Copiada" : "Copiar"}</button></div>
    </div>}
  </article>;
}

function FormResposta({ caseId, decisao, pricing, onChange }) {
  const acao = useAction();
  const [resposta, setResposta] = useState("ACEITO");
  const [valor, setValor] = useState(decisao.proposed_value ?? "");
  const [motivo, setMotivo] = useState("");
  const maximo = pricing?.walk_away_value;
  const acima = resposta === "ACEITO" && maximo != null && Number(valor) > maximo + 0.01;
  const enviar = (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    acao.run(async () => {
      await sendJson(`/cases/${caseId}/negotiation-outcomes`, {
        status: resposta, offered_value: decisao.proposed_value,
        closed_value: resposta === "ACEITO" ? Number(valor) : null,
        counter_value: resposta === "CONTRAPROPOSTA" ? Number(valor) : null,
        divergence_reason: acima ? motivo || null : null,
        reason: String(form.get("reason") || "").trim() || null,
      });
      onChange();
    });
  };
  const opcoes = [["ACEITO", "O autor aceitou"], ["CONTRAPROPOSTA", "O autor pediu outro valor"], ["RECUSADO", "O autor recusou"], ["SEM_RESPOSTA", "O autor não respondeu"]];
  return <article className="panel decisao-advogado">
    <div className="panel-heading"><div><h3>Resposta do autor</h3><p>Recusa ou silêncio levam o processo para a defesa.</p></div></div>
    <form onSubmit={enviar}><fieldset className="form-fields" disabled={acao.pending}>
      <div className="opcoes-acao compacta">{opcoes.map(([codigo, texto]) => <label key={codigo} className={`opcao-acao ${resposta === codigo ? "marcada" : ""}`}>
        <input type="radio" name="status" value={codigo} checked={resposta === codigo} onChange={() => { setResposta(codigo); setValor(codigo === "ACEITO" ? decisao.proposed_value ?? "" : ""); }} /><span><b>{texto}</b></span>
      </label>)}</div>
      {(resposta === "ACEITO" || resposta === "CONTRAPROPOSTA") && <label>{resposta === "ACEITO" ? "Valor fechado" : "Valor que o autor pediu"}
        <input type="number" min="1" step="0.01" required value={valor} onChange={(event) => setValor(event.target.value)} /></label>}
      {resposta === "CONTRAPROPOSTA" && valor !== "" && maximo != null && <p className={Number(valor) <= maximo + 0.01 ? "dentro-limite" : "alerta-valor"}>
        {Number(valor) <= maximo + 0.01 ? `Dentro do valor máximo (${moeda(maximo)}): depois de registrar, você pode aceitar.` : `Passa do valor máximo (${moeda(maximo)}): defender sai mais barato.`}</p>}
      {acima && <Motivo titulo="Por que fechar acima do valor máximo?" motivo={motivo} setMotivo={setMotivo} />}
      {resposta !== "CONTRAPROPOSTA" && !acima && <label>Observação (opcional)<textarea name="reason" maxLength="2000" /></label>}
      <Erro mensagem={acao.error} />
      <button className="primary">{acao.pending ? "Registrando…" : "Registrar resposta"}</button>
    </fieldset></form>
  </article>;
}

function FormContraproposta({ caseId, fase, pricing, onChange }) {
  const acao = useAction();
  const [motivo, setMotivo] = useState("");
  const [forcar, setForcar] = useState(false);
  const pedido = fase.negociacao.counter_value;
  const maximo = pricing?.walk_away_value;
  const dentro = maximo == null || pedido <= maximo + 0.01;
  const registrar = (corpo) => acao.run(async () => { await sendJson(`/cases/${caseId}/negotiation-outcomes`, corpo); onChange(); });
  return <article className={`panel decisao-advogado ${dentro ? "contraproposta-ok" : "contraproposta-alta"}`}>
    <div className="panel-heading"><div><h3>O autor pediu {moeda(pedido)}</h3>
      <p>{dentro ? `Está dentro do valor máximo (${moeda(maximo)}): pode aceitar.` : `Passa do valor máximo (${moeda(maximo)}): defender sai mais barato.`}</p></div></div>
    <Erro mensagem={acao.error} />
    <div className="botoes-contraproposta">
      {dentro && <button className="primary" disabled={acao.pending} onClick={() => registrar({ status: "ACEITO", offered_value: fase.decisao.proposed_value, closed_value: pedido })}>Aceitar {moeda(pedido)}</button>}
      <button className={dentro ? "subtle" : "primary"} disabled={acao.pending} onClick={() => registrar({ status: "RECUSADO", offered_value: fase.decisao.proposed_value, counter_value: pedido })}>Recusar e seguir com a defesa</button>
      {!dentro && !forcar && <button className="subtle" onClick={() => setForcar(true)}>Aceitar mesmo assim</button>}
    </div>
    {!dentro && forcar && <form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); registrar({ status: "ACEITO", offered_value: fase.decisao.proposed_value, closed_value: pedido, divergence_reason: motivo || null, reason: String(form.get("reason") || "").trim() || null }); }}>
      <fieldset className="form-fields" disabled={acao.pending}>
        <Motivo titulo="Por que aceitar acima do valor máximo?" motivo={motivo} setMotivo={setMotivo} />
        <button className="primary">Aceitar {moeda(pedido)} com justificativa</button>
      </fieldset>
    </form>}
  </article>;
}

function FormSentenca({ caseId, fase, onChange }) {
  const acao = useAction();
  const [resultado, setResultado] = useState("EXITO");
  const enviar = (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    acao.run(async () => {
      await sendJson(`/cases/${caseId}/judicial-outcomes`, {
        result: resultado, condemnation_value: resultado === "NAO_EXITO" ? Number(form.get("valor")) : null,
      });
      onChange();
    });
  };
  const recusado = fase.decisao?.action === "ACORDO";
  return <article className="panel decisao-advogado">
    <div className="panel-heading"><span className="panel-icon"><Icon name="scale" /></span><div><h3>Sentença</h3>
      <p>{recusado ? "O autor não aceitou o acordo: o processo segue na Justiça." : "Registre quando a sentença sair."}</p></div></div>
    <form onSubmit={enviar}><fieldset className="form-fields" disabled={acao.pending}>
      <div className="opcoes-acao compacta">{[["EXITO", "Favorável à empresa"], ["NAO_EXITO", "Desfavorável à empresa"]].map(([codigo, texto]) => <label key={codigo} className={`opcao-acao ${resultado === codigo ? "marcada" : ""}`}>
        <input type="radio" name="result" value={codigo} checked={resultado === codigo} onChange={() => setResultado(codigo)} /><span><b>{texto}</b></span></label>)}</div>
      {resultado === "NAO_EXITO" && <label>Valor da condenação<input name="valor" type="number" min="0" step="0.01" required /></label>}
      <Erro mensagem={acao.error} />
      <button className="primary">{acao.pending ? "Registrando…" : "Registrar sentença"}</button>
    </fieldset></form>
  </article>;
}

function AguardandoDocumento({ fase }) {
  const pedido = fase.pedido_aberto;
  return <article className="panel decisao-advogado">
    <div className="panel-heading"><span className="panel-icon"><Icon name="clock" /></span><div><h3>Aguardando a empresa</h3>
      <p>Você pediu {pedido ? DOCUMENTOS[pedido.document_type] || pedido.document_type : "um documento"} em {data(pedido?.created_at)}. Quando a empresa responder, o processo volta para você reavaliar.</p></div></div>
  </article>;
}

export function PainelDaFase({ caseId, detalhe, fase, recomendacao, onChange }) {
  const pricingDaDecisao = detalhe.analyses.find((analise) => analise.id === fase.decisao?.analysis_id)?.pricing || recomendacao?.pricing;
  switch (fase.codigo) {
    case "PRONTO_PARA_DECIDIR":
      return recomendacao ? <PainelRecolhivel group="action" titulo="Decisão" resumo="Registrar o próximo passo"><FormDecisao key={recomendacao.id} caseId={caseId} recomendacao={recomendacao} onChange={onChange} /></PainelRecolhivel> : null;
    case "AGUARDANDO_DOCUMENTO":
      return <PainelRecolhivel group="action" titulo="Solicitação de documento" resumo="Aguardando a empresa"><AguardandoDocumento fase={fase} /></PainelRecolhivel>;
    case "EM_NEGOCIACAO":
      return <><PainelRecolhivel group="action" titulo="Negociação" resumo="Roteiro e proposta"><Roteiro caseId={caseId} decisao={fase.decisao} pricing={pricingDaDecisao} /></PainelRecolhivel>
        <PainelRecolhivel group="action" titulo="Resposta do autor" resumo="Registrar o retorno da negociação"><FormResposta caseId={caseId} decisao={fase.decisao} pricing={pricingDaDecisao} onChange={onChange} /></PainelRecolhivel></>;
    case "CONTRAPROPOSTA":
      return <PainelRecolhivel group="action" titulo="Contraproposta" resumo={`O autor pediu ${moeda(fase.negociacao.counter_value)}`}><FormContraproposta caseId={caseId} fase={fase} pricing={pricingDaDecisao} onChange={onChange} /></PainelRecolhivel>;
    case "EM_DEFESA":
      return <PainelRecolhivel group="action" titulo="Sentença" resumo="Registrar o resultado do processo"><FormSentenca caseId={caseId} fase={fase} onChange={onChange} /></PainelRecolhivel>;
    case "ENCERRADO":
      return <PainelRecolhivel group="action" titulo="Resultado do processo" resumo="Processo encerrado"><ResultadoProcesso detail={detalhe} decision={detalhe.lawyer_decisions[0]} recommendation={recomendacao} /></PainelRecolhivel>;
    default:
      return null;
  }
}

export function LinhaDoTempo({ detalhe, initiallyCollapsed = true }) {
  const eventos = [
    ...detalhe.analyses.map((analise) => ({ quando: analise.created_at, texto: `Avaliação: ${ACOES[analise.recommendation]?.titulo || analise.recommendation}` })),
    ...detalhe.lawyer_decisions.map((decisao) => ({ quando: decisao.created_at, texto: `Decisão: ${ACOES[decisao.action]?.titulo || decisao.action}${decisao.proposed_value ? ` de ${moeda(decisao.proposed_value)}` : ""}${decisao.divergence_reason ? " (diferente da recomendação)" : ""}` })),
    ...detalhe.document_requests.map((pedido) => ({ quando: pedido.created_at, texto: `Pedido de ${DOCUMENTOS[pedido.document_type] || pedido.document_type} à empresa` })),
    ...(detalhe.negotiation_outcomes || []).map((item) => ({ quando: item.created_at, texto: { ACEITO: `Acordo fechado em ${moeda(item.closed_value)}`, CONTRAPROPOSTA: `Autor pediu ${moeda(item.counter_value)}`, RECUSADO: "Autor recusou", SEM_RESPOSTA: "Autor não respondeu" }[item.status] })),
    ...(detalhe.judicial_outcomes || []).map((item) => ({ quando: item.created_at, texto: item.result === "EXITO" ? "Sentença favorável" : `Sentença desfavorável: ${moeda(item.condemnation_value)}` })),
  ].sort((a, b) => new Date(b.quando) - new Date(a.quando));
  if (!eventos.length) return <PainelRecolhivel group="history" titulo="Histórico" resumo="Nenhum registro ainda"><article className="panel case-empty-panel"><Icon name="clock" /><h3>A história começa aqui</h3><p>Avaliações, decisões e respostas aparecerão nesta área.</p></article></PainelRecolhivel>;
  return <PainelRecolhivel group="history" titulo="Histórico" resumo={`${eventos.length} registro(s) · ${eventos[0].texto}`} initiallyCollapsed={initiallyCollapsed}><article className="panel linha-do-tempo"><ol>{eventos.map((evento, index) => <li key={index}><span className="muted">{data(evento.quando)}</span>{evento.texto}</li>)}</ol></article></PainelRecolhivel>;
}
