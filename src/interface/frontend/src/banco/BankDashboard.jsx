import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useResource } from "../hooks";
import { ContractManager } from "./ContractManager";
import { WeeklyChart } from "./WeeklyChart";
import { Bar, Kpi, Notice, Pill, ResetPasswordAction, SectionHeader } from "./ui";
import { brl, brlCompact, date, index as fmtIndex, indexTone, minutes, num, pct, segmentLabel } from "./format";
import "./banco.css";

const TABS = [
  ["geral", "Visão geral"],
  ["documentos", "Documentos"],
  ["recomendacoes", "Recomendações"],
  ["escritorios", "Escritórios"],
  ["advogados", "Advogados"],
  ["engajamento", "Engajamento"],
  ["excecoes", "Exceções"],
  ["contrato", "Contrato"],
  ["equipe", "Equipe"],
];

export default function BankDashboard({ user }) {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([key]) => key === params.get("aba")) ? params.get("aba") : "geral";
  const insights = useResource("/bank/insights");
  const data = insights.data;
  const standalone = tab === "contrato" || tab === "equipe";
  return <section className="bank-dashboard">
    <div className="bank-toolbar">
      <div className="bank-tabs" role="tablist" aria-label="Seções do painel do banco">
        {TABS.map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={key === tab}
          className={key === tab ? "active" : ""} onClick={() => setParams({ aba: key })}>
          {label}{key === "excecoes" && data?.excecoes.total ? <span className="tab-count">{data.excecoes.total}</span> : null}
        </button>)}
      </div>
      <div className="bank-toolbar-meta">
        {data?.casos_simulados > 0 && <span className="sim-badge" title="Processos sorteados da base real de 60 mil sentenças. O comportamento dos advogados e a resposta da parte autora são simulados.">
          Operação simulada · {num(data.casos_simulados)} de {num(data.casos)} processos</span>}
        {data && !standalone && <button type="button" className="ghost" onClick={insights.reload} disabled={insights.loading}>{insights.loading ? "Atualizando…" : "Atualizar"}</button>}
      </div>
    </div>
    {tab === "contrato" ? <ContractManager user={user} /> : tab === "equipe" ? <Team user={user} /> : <>
      <Notice message={insights.error} onRetry={insights.reload} />
      {!data && insights.loading && <p role="status">Calculando indicadores da operação…</p>}
      {data && tab === "geral" && <Overview data={data} />}
      {data && tab === "documentos" && <Documents data={data} />}
      {data && tab === "recomendacoes" && <Recommendations data={data} />}
      {data && tab === "escritorios" && <Firms data={data} />}
      {data && tab === "advogados" && <Lawyers data={data} />}
      {data && tab === "engajamento" && <Engagement data={data} />}
      {data && tab === "excecoes" && <Exceptions data={data} />}
    </>}
  </section>;
}

/** Gestor redefine a senha dos advogados ativos do banco. Sem tela própria para isso ainda. */
function Team({ user }) {
  const lawyers = useResource("/bank/lawyers");
  if (!user.is_manager) return <p className="muted">Somente o gestor do banco redefine senha da equipe.</p>;
  return <div className="bank-stack">
    <SectionHeader eyebrow="EQUIPE" title="Advogados com acesso" children="Redefina a senha de um advogado do seu banco quando ele esquecer a própria." />
    <Notice message={lawyers.error} onRetry={lawyers.reload} />
    {lawyers.loading && <p role="status">Carregando equipe…</p>}
    {lawyers.data && <ul className="admin-user-list">{lawyers.data.map((lawyer) => <li key={lawyer.id}>
      <span>{lawyer.name} · {lawyer.email}{lawyer.law_firm_name ? ` · ${lawyer.law_firm_name}` : ""}</span>
      <ResetPasswordAction endpoint={`/bank/users/${lawyer.id}/password`} />
    </li>)}</ul>}
  </div>;
}

function Overview({ data }) {
  const e = data.efetividade;
  const j = e.desfechos_judiciais;
  const [low, high] = e.aceitacao_intervalo;
  const maxCondenacao = Math.max(1, j.condenacao_esperada, j.condenacao_realizada);
  return <div className="bank-stack">
    <SectionHeader eyebrow="EFETIVIDADE DA POLÍTICA" title="O que a política entregou até agora">
      Cada número é comparado com o que a própria política esperava para aquele processo. Índice 1,0 significa que a operação entregou exatamente a economia prometida.
    </SectionHeader>
    <div className="kpi-grid">
      <Kpi tone={indexTone(e.indice)} label="Economia realizada" value={brlCompact(e.economia_realizada)}
        hint={e.indice == null ? "Ainda sem acordos com resultado" : `Índice ${fmtIndex(e.indice)} · esperado ${brlCompact(e.economia_esperada)}`} />
      <Kpi label="Aceitação dos acordos" value={pct(e.aceitacao)}
        hint={`Premissa ${pct(e.aceitacao_premissa, 0)} · aprendida ${pct(e.aceitacao_posterior, 0)} (${pct(low, 0)} a ${pct(high, 0)})`} />
      <Kpi tone={indexTone(e.aderencia)} label="Aderência à política" value={pct(e.aderencia)} hint={`${num(e.decisoes)} decisões registradas`} />
      <Kpi tone={e.custo_divergencias > 0 ? "bad" : "good"} label="Custo das divergências" value={brlCompact(e.custo_divergencias)}
        hint="Economia esperada perdida quando a recomendação não foi seguida" />
      <Kpi tone={e.pago_acima_do_alvo > 0 ? "warn" : "good"} label="Pago acima do alvo" value={brlCompact(e.pago_acima_do_alvo)}
        hint={`${num(e.fechados_acima_walk_away)} acordo(s) acima do walk-away`} />
      <Kpi label="Acordos fechados" value={`${num(e.acordos_fechados)} de ${num(e.acordos_propostos)}`}
        hint={`${num(e.negociacoes_pendentes)} em negociação · ${pct(e.valor_fechado_sobre_causa)} da causa, em média`} />
    </div>
    <div className="bank-columns">
      <article className="panel"><h3>Economia por semana</h3><WeeklyChart series={e.serie_semanal} /></article>
      <article className="panel"><h3>Frente às condenações</h3>
        <p className="muted">Processos defendidos que já têm sentença, contra o que a política projetava para eles.</p>
        <Bar label="Condenação projetada pela política" value={j.condenacao_esperada} max={maxCondenacao} display={brlCompact(j.condenacao_esperada)} tone="muted" />
        <Bar label="Condenação realizada" value={j.condenacao_realizada} max={maxCondenacao} display={brlCompact(j.condenacao_realizada)}
          tone={j.condenacao_realizada <= j.condenacao_esperada ? "good" : "bad"} />
        <dl className="facts">
          <div><dt>Sentenças</dt><dd>{num(j.casos)}</dd></div>
          <div><dt>Êxito</dt><dd>{pct(j.exito)}</dd></div>
          <div><dt>Aguardando sentença</dt><dd>{num(j.aguardando_desfecho)}</dd></div>
        </dl>
      </article>
    </div>
  </div>;
}

function Documents({ data }) {
  const d = data.documentos;
  const base = d.base_historica;
  const max = Math.max(1, ...d.carteira.por_documento.map((doc) => doc.valor_em_jogo));
  return <div className="bank-stack">
    <SectionHeader eyebrow="DOCUMENTOS · A ALAVANCA DO BANCO" title="Quanto custa o documento que não chega">
      Contrato e extrato mudam o resultado do processo, e quem entrega os dois é o banco. Esta é a economia que depende só da sua operação.
    </SectionHeader>
    <div className="bank-columns">
      <article className="panel hero-panel">
        <p className="eyebrow">VALOR EM JOGO NA CARTEIRA ANALISADA</p>
        <strong className="hero-value">{brl(d.carteira.valor_em_jogo_total)}</strong>
        <p className="muted">{num(d.carteira.casos_analisados)} processos analisados, já descontada a chance de o documento não ser encontrado.</p>
        {d.carteira.por_documento.map((doc) => <Bar key={doc.tipo} label={doc.nome} value={doc.valor_em_jogo} max={max}
          display={brlCompact(doc.valor_em_jogo)} caption={`${num(doc.casos_sem)} processos sem o documento`} />)}
      </article>
      <article className="panel"><h3>Por que o documento não veio</h3>
        {d.motivos.length ? <ul className="reason-list">{d.motivos.map((m) => <li key={`${m.documento}-${m.motivo}`}>
          <div><strong>{m.motivo_nome}</strong><span>{m.documento_nome} · {num(m.casos)} pedido(s){m.classificados_por_ia ? ` · ${num(m.classificados_por_ia)} classificado(s) por IA` : ""}</span></div>
          <b>{brlCompact(m.valor_em_jogo)}</b>
        </li>)}</ul> : <p className="empty-line">Nenhum pedido declarado indisponível ainda.</p>}
        <dl className="facts">
          <div><dt>Pedidos</dt><dd>{num(d.pedidos.total)}</dd></div>
          <div><dt>Resposta (mediana)</dt><dd>{d.pedidos.dias_para_responder_mediana == null ? "—" : `${num(d.pedidos.dias_para_responder_mediana, 1)} dias`}</dd></div>
          <div><dt>Entregues</dt><dd>{pct(d.pedidos.entregues)}</dd></div>
        </dl>
      </article>
    </div>
    <article className="panel">
      <div className="panel-title-row"><h3>Fila de recuperação</h3><span className="count-badge">{num(d.fila_total)} em aberto · {brlCompact(d.fila_valor_em_jogo)} em jogo</span></div>
      <p className="muted">Pedidos dos advogados, do maior para o menor valor que o documento pode economizar.</p>
      {d.fila_recuperacao.length ? <div className="table-scroll"><table className="data-table">
        <thead><tr><th>Processo</th><th>Documento</th><th>Advogado</th><th className="num">Em aberto</th><th className="num">Valor em jogo</th></tr></thead>
        <tbody>{d.fila_recuperacao.map((item) => <tr key={item.id}>
          <td><Link to={`/banco/casos/${item.case_id}`}>{item.case_number}</Link></td>
          <td>{item.documento_nome}</td>
          <td>{item.advogado || "—"}</td>
          <td className="num"><Pill tone={item.dias_em_aberto > 10 ? "bad" : item.dias_em_aberto > 5 ? "warn" : "neutral"}>{num(item.dias_em_aberto)} dias</Pill></td>
          <td className="num"><b>{brl(item.valor_em_jogo)}</b></td>
        </tr>)}</tbody>
      </table></div> : <p className="empty-line">Nenhum pedido em aberto.</p>}
    </article>
    {base && <article className="panel">
      <h3>O que a base histórica mostra</h3>
      <p className="muted">Em {num(base.casos)} sentenças, sem contrato e sem extrato o banco perde {pct(base.sem_contrato_e_extrato.derrota)} das vezes: são {pct(base.sem_contrato_e_extrato.pct)} dos processos e {brlCompact(base.sem_contrato_e_extrato.pago)} pagos.</p>
      <div className="table-scroll"><table className="data-table">
        <thead><tr><th>Documento</th><th className="num">Falta em</th><th className="num">Derrota com</th><th className="num">Derrota sem</th><th className="num">Valor em jogo</th></tr></thead>
        <tbody>{base.documentos.map((doc) => <tr key={doc.tipo} className={doc.muda_resultado ? "" : "row-muted"}>
          <td>{doc.nome}{!doc.muda_resultado && <small className="cell-sub">não muda o resultado</small>}</td>
          <td className="num">{pct(doc.ausente_pct)}</td>
          <td className="num">{pct(doc.derrota_com)}</td>
          <td className="num">{pct(doc.derrota_sem)}</td>
          <td className="num">{doc.valor_em_jogo == null ? "—" : brlCompact(doc.valor_em_jogo)}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="footnote">{base.premissas}</p>
    </article>}
  </div>;
}

function Recommendations({ data }) {
  const [area, setArea] = useState("");
  const areas = useMemo(() => [...new Set(data.recomendacoes.map((card) => card.area))], [data]);
  const cards = data.recomendacoes.filter((card) => !area || card.area === area);
  return <div className="bank-stack">
    <SectionHeader eyebrow="RECOMENDAÇÕES PARA A OPERAÇÃO DO BANCO" title="O que construir, e quem constrói">
      Cada recomendação nasce dos motivos que o seu time registrou ao não entregar um documento, ou da base histórica. O valor em jogo vem do motor; a IA só classifica respostas escritas em texto livre.
    </SectionHeader>
    <div className="chips" role="group" aria-label="Filtrar por área responsável">
      <button type="button" className={area ? "chip" : "chip active"} onClick={() => setArea("")}>Todas as áreas</button>
      {areas.map((name) => <button type="button" key={name} className={name === area ? "chip active" : "chip"} onClick={() => setArea(name)}>{name}</button>)}
    </div>
    <div className="rec-grid">{cards.map((card, index) => <article key={`${card.titulo}-${index}`} className={`panel rec-card origin-${card.origem}`}>
      <div className="rec-top">
        <Pill tone={card.prioridade === "Alta" ? "bad" : card.prioridade === "Média" ? "warn" : "neutral"}>{card.prioridade}</Pill>
        <span className="rec-origin">{card.origem === "operacao" ? "Da sua operação" : "Da base histórica"}</span>
      </div>
      <h3>{card.titulo}</h3>
      <p className="rec-area">Responsável: <b>{card.area}</b></p>
      <p>{card.acao}</p>
      <dl className="facts">
        <div><dt>Valor em jogo</dt><dd>{card.valor_em_jogo ? brlCompact(card.valor_em_jogo) : "—"}</dd></div>
        <div><dt>Processos</dt><dd>{num(card.casos)}</dd></div>
      </dl>
      <p className="footnote"><b>Como medir:</b> {card.indicador}. {card.evidencia}</p>
    </article>)}</div>
  </div>;
}

function Firms({ data }) {
  const { regras } = data;
  return <div className="bank-stack">
    <SectionHeader eyebrow="ESCRITÓRIOS CONTRATADOS" title="Com você e no mercado">
      O índice compara a economia realizada com a esperada para os casos que cada escritório recebeu, por isso carteiras diferentes ficam comparáveis. O mercado é anônimo: nenhum outro cliente é identificado.
    </SectionHeader>
    {data.escritorios.length ? <div className="firm-grid">{data.escritorios.map((firm) => {
      const mercado = firm.mercado;
      const max = Math.max(1.2, firm.indice ?? 0, mercado?.indice ?? 0);
      const gap = mercado?.indice != null && firm.indice != null ? firm.indice - mercado.indice : 0;
      return <article key={firm.id} className="panel firm-card">
        <div className="firm-head">
          <div><h3>{firm.nome}</h3><p className="muted">{num(firm.advogados)} advogado(s) · {num(firm.decisoes)} decisões</p></div>
          <Pill tone={indexTone(firm.indice)}>Índice {fmtIndex(firm.indice)}</Pill>
        </div>
        <Bar label="Com você" value={firm.indice ?? 0} max={max} display={fmtIndex(firm.indice)} tone={indexTone(firm.indice)} />
        {mercado ? <Bar label="No mercado (anônimo)" value={mercado.indice ?? 0} max={max} display={fmtIndex(mercado.indice)}
          tone="muted" caption={`${num(mercado.decisoes)} decisões em outros clientes`} />
          : <p className="footnote">{firm.motivo_sem_mercado}</p>}
        {firm.leitura && <p className={`reading tone-${gap < -0.1 ? "bad" : gap > 0.1 ? "good" : "neutral"}`}>{firm.leitura}</p>}
        <dl className="facts">
          <div><dt>Aderência</dt><dd>{pct(firm.aderencia)}{mercado && <small> · mercado {pct(mercado.aderencia)}</small>}</dd></div>
          <div><dt>Aceitação</dt><dd>{pct(firm.aceitacao)}{mercado && <small> · mercado {pct(mercado.aceitacao)}</small>}</dd></div>
          <div><dt>Pago acima do alvo</dt><dd>{brlCompact(firm.pago_acima_do_alvo)}</dd></div>
          <div><dt>Custo das divergências</dt><dd>{brlCompact(firm.custo_divergencias)}</dd></div>
        </dl>
      </article>;
    })}</div> : <p className="empty-line">Nenhum escritório com decisões registradas.</p>}
    <p className="footnote">O mercado só aparece quando o escritório atende ao menos {regras.min_outros_clientes} outros clientes e soma {regras.min_decisoes_mercado} decisões fora deste banco.</p>
  </div>;
}

function Lawyers({ data }) {
  return <div className="bank-stack">
    <SectionHeader eyebrow="ADVOGADOS NOS SEUS PROCESSOS" title="Quem executa a política">
      Ranking pelo índice ajustado ao risco, nunca por taxa de vitória. Com menos de {data.regras.min_decisoes_ranking} decisões, o advogado aparece sem nota.
    </SectionHeader>
    <article className="panel">
      {data.advogados.length ? <div className="table-scroll"><table className="data-table">
        <thead><tr><th>#</th><th>Advogado</th><th className="num">Decisões</th><th className="num">Índice</th><th className="num">Aderência</th><th className="num">Aceitação</th>
          <th className="num">Acima do alvo</th><th className="num">Divergências</th><th className="num">Tempo por caso</th><th className="num">Sem abrir documento</th></tr></thead>
        <tbody>{data.advogados.map((lawyer, index) => <tr key={lawyer.id} className={lawyer.amostra_suficiente ? "" : "row-muted"}>
          <td>{lawyer.amostra_suficiente ? index + 1 : "—"}</td>
          <td><strong>{lawyer.nome}</strong><small className="cell-sub">{lawyer.escritorio || "Sem escritório"}</small></td>
          <td className="num">{num(lawyer.decisoes)}</td>
          <td className="num">{lawyer.amostra_suficiente ? <Pill tone={indexTone(lawyer.indice)}>{fmtIndex(lawyer.indice)}</Pill> : <small>amostra insuficiente</small>}</td>
          <td className="num">{pct(lawyer.aderencia)}</td>
          <td className="num">{pct(lawyer.aceitacao)}</td>
          <td className="num">{brlCompact(lawyer.pago_acima_do_alvo)}</td>
          <td className="num">{brlCompact(lawyer.custo_divergencias)}</td>
          <td className="num">{minutes(lawyer.tempo_ativo_mediano_min)}</td>
          <td className="num">{lawyer.decisoes_sem_abrir_documento > 0.3 ? <Pill tone="bad">{pct(lawyer.decisoes_sem_abrir_documento, 0)}</Pill> : pct(lawyer.decisoes_sem_abrir_documento, 0)}</td>
        </tr>)}</tbody>
      </table></div> : <p className="empty-line">Nenhuma decisão registrada ainda.</p>}
      <p className="footnote">Índice = economia realizada ÷ economia esperada para os casos que o advogado recebeu. "Acima do alvo" soma o que foi pago além do alvo em acordos fechados; "Divergências" é a economia esperada perdida ao não seguir a recomendação.</p>
    </article>
  </div>;
}

function Engagement({ data }) {
  const g = data.engajamento;
  const max = Math.max(1, ...g.por_segmento.map((segment) => segment.tempo_ativo_mediano_min || 0));
  return <div className="bank-stack">
    <SectionHeader eyebrow="ENGAJAMENTO" title="Onde vai o tempo do advogado">
      O tempo ativo só conta com a tela do processo visível. Menos tempo com o mesmo índice é a IA funcionando; o alerta é decidir sem abrir documento quando o motor pediu conferência.
    </SectionHeader>
    <div className="kpi-grid">
      <Kpi label="Tempo ativo por caso" value={minutes(g.tempo_ativo_mediano_min)} hint="Mediana" />
      <Kpi label="Casos com ressalva do motor" value={minutes(g.tempo_com_ressalva_min)} hint={`Sem ressalva: ${minutes(g.tempo_sem_ressalva_min)}`} />
      <Kpi label="Documentos abertos por caso" value={num(g.documentos_abertos_medio, 1)} hint="Média" />
      <Kpi label="Da abertura à decisão" value={g.horas_ate_decisao_mediana == null ? "—" : `${num(g.horas_ate_decisao_mediana, 1)} h`} hint="Mediana" />
      <Kpi tone={g.decisoes_sem_abrir_documento > 0.15 ? "bad" : "good"} label="Decisões sem abrir documento" value={pct(g.decisoes_sem_abrir_documento)} />
    </div>
    <article className="panel"><h3>Tempo por tipo de caso</h3>
      <p className="muted">Os tipos que mais consomem tempo mesmo com a recomendação pronta mostram onde o motor pode melhorar.</p>
      <div className="segment-list">{g.por_segmento.map((segment) => <Bar key={segment.segmento} label={segmentLabel(segment.segmento)}
        value={segment.tempo_ativo_mediano_min || 0} max={max} display={minutes(segment.tempo_ativo_mediano_min)}
        caption={`${num(segment.casos)} casos · ${pct(segment.com_ressalva, 0)} com ressalva · aderência ${pct(segment.aderencia, 0)}`} />)}</div>
    </article>
  </div>;
}

const EXCEPTION_TYPES = {
  ACORDO_ACIMA_WALK_AWAY: { label: "Acordo acima do walk-away", impact: "Pago além do walk-away", tone: "bad" },
  DIVERGENCIA_CARA: { label: "Divergência cara", impact: "Custo esperado da divergência", tone: "warn" },
  DECISAO_SEM_CONFERENCIA: { label: "Decisão sem conferência", impact: "Custo esperado do caso", tone: "neutral" },
};

function Exceptions({ data }) {
  const [type, setType] = useState("");
  const x = data.excecoes;
  const items = x.itens.filter((item) => !type || item.tipo === type);
  return <div className="bank-stack">
    <SectionHeader eyebrow="GESTÃO POR EXCEÇÃO" title="O que fugiu da política">
      Em vez de acompanhar tudo, olhe o que saiu do combinado: acordo acima do walk-away, divergência com custo esperado acima de {brl(x.limiar_divergencia)} e decisão sem abrir documento quando o motor pediu conferência.
    </SectionHeader>
    <div className="chips" role="group" aria-label="Filtrar exceções">
      <button type="button" className={type ? "chip" : "chip active"} onClick={() => setType("")}>Todas · {num(x.total)}</button>
      {Object.entries(EXCEPTION_TYPES).map(([key, meta]) => <button type="button" key={key} className={key === type ? "chip active" : "chip"} onClick={() => setType(key)}>
        {meta.label} · {num(x.por_tipo[key] || 0)}</button>)}
    </div>
    <article className="panel">
      {items.length ? <ul className="exception-list">{items.map((item, index) => {
        const meta = EXCEPTION_TYPES[item.tipo];
        return <li key={`${item.case_id}-${item.tipo}-${index}`}>
          <div className="exception-main">
            <div className="exception-line"><Pill tone={meta.tone}>{meta.label}</Pill><Link to={`/banco/casos/${item.case_id}`}>{item.case_number}</Link></div>
            <span className="muted">{item.advogado || "—"} · {item.escritorio || "sem escritório"} · {date(item.data)}</span>
            <p>{item.detalhe}</p>
          </div>
          <div className="exception-impact"><small>{meta.impact}</small><strong>{brl(item.impacto)}</strong></div>
        </li>;
      })}</ul> : <p className="empty-line">Nenhuma exceção.</p>}
      {x.total > x.itens.length && <p className="footnote">Mostrando as {num(x.itens.length)} de maior impacto, de {num(x.total)}.</p>}
    </article>
  </div>;
}
