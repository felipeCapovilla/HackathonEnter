import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useResource } from "../hooks";
import { ContractManager } from "./ContractManager";
import { WeeklyChart } from "./WeeklyChart";
import { Bar, InfoTip, Kpi, Notice, Pill, ResetPasswordAction, SectionHeader } from "./ui";
import { brl, brlCompact, date, num, pct } from "./format";
import "./banco.css";

const TABS = [
  ["geral", "Visão geral"],
  ["documentos", "Documentos"],
  ["recomendacoes", "Recomendações"],
  ["escritorios", "Escritórios"],
  ["advogados", "Advogados"],
  ["excecoes", "Exceções"],
  ["contrato", "Contrato"],
  ["equipe", "Equipe"],
];
const COMPONENTES = [
  ["resultado", "Economia nos processos", "Quanto os processos encerrados custaram comparado a processos parecidos na base histórica. 50 = igual à média; acima de 50, custaram menos."],
  ["preco", "Valor dos acordos", "Onde os acordos fechados ficaram entre os 280 acordos da base, em % da causa. Quanto mais barato que o mercado, maior a nota."],
  ["aderencia", "Segue a recomendação", "100 quando sempre segue a recomendação. Decidir diferente registrando o motivo vale metade; sem motivo, zero."],
  ["aceitacao", "Acordos aceitos", "Percentual das propostas de acordo que o autor aceitou."],
];
const DICAS = {
  encerrados: "Processos com resultado final: acordo fechado ou sentença registrada.",
  nota: "De 0 a 100. Mistura as quatro notas: economia nos processos (50%), valor dos acordos (20%), segue a recomendação (20%) e acordos aceitos (10%). Com poucos processos encerrados, fica perto da média da empresa.",
  ticket: "Média do valor fechado nos acordos, em reais e em % da causa. Na base histórica, os acordos fecharam em 29,8% da causa.",
  economia: "Soma, nos processos encerrados, de quanto custaram a menos (ou a mais) que processos parecidos na base.",
};
const falarEconomia = (valor) => valor >= 0 ? `Economizou ${brlCompact(valor)}` : `Custou ${brlCompact(-valor)} a mais`;
const tomDoScore = (nota) => nota == null ? "neutral" : nota >= 70 ? "good" : nota >= 50 ? "warn" : "bad";

export default function BankDashboard({ user }) {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([key]) => key === params.get("aba")) ? params.get("aba") : "geral";
  const insights = useResource("/bank/insights");
  const data = insights.data;
  const standalone = tab === "contrato" || tab === "equipe";
  return <section className="bank-dashboard">
    <div className="bank-toolbar">
      <div className="bank-tabs" role="tablist" aria-label="Seções do painel da empresa">
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
      {data && tab === "excecoes" && <Exceptions data={data} />}
    </>}
  </section>;
}

/** Gestor redefine a senha dos advogados ativos do banco. Sem tela própria para isso ainda. */
function Team({ user }) {
  const lawyers = useResource("/bank/lawyers");
  if (!user.is_manager) return <p className="muted">Somente o gestor da empresa redefine senha da equipe.</p>;
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
  const t = e.ticket;
  const d = e.defendidos;
  const maxDefesa = Math.max(1, d.custo_parecidos, d.condenacoes_comparaveis);
  return <div className="bank-stack">
    <SectionHeader eyebrow="EFETIVIDADE DA POLÍTICA" title="O que a política entregou até agora">
      Só valores observados: o que foi pago de fato e quanto processos parecidos custaram na base de 60 mil sentenças. A economia é a soma, nos processos encerrados, de "custo médio de processos parecidos − custo real".
    </SectionHeader>
    <div className="kpi-grid">
      <Kpi tone={e.economia.total >= 0 ? "good" : "bad"} label="Economia" value={brlCompact(e.economia.total)}
        hint={`${num(e.economia.processos)} processos encerrados, contra o custo médio real de processos parecidos. Veja de onde vem abaixo.`} />
      <Kpi label="Ticket médio dos acordos" value={brl(t.ticket_medio)}
        hint={t.ticket_medio == null ? "Ainda sem acordo fechado" : `${pct(t.sobre_causa_medio)} da causa · na base: ${pct(t.referencia.sobre_causa_medio)} (${brl(t.referencia.ticket_medio)})`} />
      <Kpi label="Aceitação dos acordos" value={pct(e.aceitacao.taxa)}
        hint={`${num(e.acordos.fechados)} acordos fechados de ${num(e.acordos.propostos)} propostos · ${num(e.acordos.em_negociacao)} em negociação · premissa inicial ${pct(e.aceitacao.premissa, 0)}`} />
      <Kpi label="Aderência à política" value={pct(e.aderencia.taxa)} hint={`${num(e.aderencia.decisoes)} decisões`} />
    </div>
    <article className="panel">
      <h3>De onde vem a economia <InfoTip texto="Cada processo encerrado é comparado com o custo médio real de processos parecidos na base. Aqui a soma aparece separada entre os processos em que o advogado seguiu a recomendação e aqueles em que decidiu diferente." /></h3>
      <div className="origem-economia">
        <div className={e.economia.seguiu >= 0 ? "ganho" : "perda"}>
          <span>Quando o advogado seguiu a recomendação</span>
          <strong>{falarEconomia(e.economia.seguiu)}</strong>
          <small>{num(e.economia.seguiu_processos)} processos encerrados, comparados a processos parecidos</small>
        </div>
        <div className={e.economia.divergiu >= 0 ? "ganho" : "perda"}>
          <span>Quando decidiu diferente da recomendação</span>
          <strong>{falarEconomia(e.economia.divergiu)}</strong>
          <small>{num(e.economia.divergiu_processos)} processos encerrados, comparados a processos parecidos</small>
        </div>
      </div>
    </article>
    <article className="panel">
      <h3>Pior caso e gasto real</h3>
      <p className="muted">Nos {num(e.economia.processos)} processos encerrados com valor registrado.</p>
      <div className="lado-a-lado">
        <div><span>Se a empresa perdesse todos pelo valor da causa</span><strong>{brl(e.pior_caso)}</strong></div>
        <div><span>Gasto real (acordos + condenações)</span><strong>{brl(e.gasto_real)}</strong></div>
      </div>
    </article>
    <div className="bank-columns">
      <article className="panel"><h3>Economia por semana</h3><WeeklyChart series={e.serie_semanal} /></article>
      <article className="panel"><h3>Processos defendidos</h3>
        <p className="muted">Sentenças registradas, contra o custo médio real de processos parecidos.</p>
        <Bar label="Custo médio de processos parecidos" value={d.custo_parecidos} max={maxDefesa} display={brlCompact(d.custo_parecidos)} tone="muted" />
        <Bar label="Condenações pagas" value={d.condenacoes_comparaveis} max={maxDefesa} display={brlCompact(d.condenacoes_comparaveis)}
          tone={d.condenacoes_comparaveis <= d.custo_parecidos ? "good" : "bad"} />
        <dl className="facts">
          <div><dt>Sentenças</dt><dd>{num(d.sentencas)}</dd></div>
          <div><dt>Êxito</dt><dd>{pct(d.exito)}</dd></div>
          <div><dt>Em andamento</dt><dd>{num(e.pendentes)}</dd></div>
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
    <SectionHeader eyebrow="DOCUMENTOS · A ALAVANCA DA EMPRESA" title="Quanto vale o documento que não chega">
      Contrato e extrato mudam o resultado do processo, e quem entrega os dois é a empresa. Esta é a economia que depende só da sua operação.
    </SectionHeader>
    <div className="bank-columns">
      <article className="panel hero-panel">
        <p className="eyebrow">ECONOMIA SE OS DOCUMENTOS CHEGAREM <span className="estimativa">estimativa</span> <InfoTip texto={d.premissa_valor_em_jogo} /></p>
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
        <thead><tr><th>Processo</th><th>Documento</th><th>Advogado</th><th className="num">Valor da causa</th><th className="num">Em aberto</th>
          <th className="num">Economia se chegar <InfoTip texto={d.premissa_valor_em_jogo} /></th></tr></thead>
        <tbody>{d.fila_recuperacao.map((item) => <tr key={item.id}>
          <td><Link to={`/banco/casos/${item.case_id}`}>{item.case_number}</Link></td>
          <td>{item.documento_nome}</td>
          <td>{item.advogado || "—"}</td>
          <td className="num">{brl(item.valor_causa)}</td>
          <td className="num"><Pill tone={item.dias_em_aberto > 10 ? "bad" : item.dias_em_aberto > 5 ? "warn" : "neutral"}>{num(item.dias_em_aberto)} dias</Pill></td>
          <td className="num"><b>{brl(item.valor_em_jogo)}</b></td>
        </tr>)}</tbody>
      </table></div> : <p className="empty-line">Nenhum pedido em aberto.</p>}
    </article>
    {base && <article className="panel">
      <h3>O que a base histórica mostra</h3>
      <p className="muted">Em {num(base.casos)} sentenças, sem contrato e sem extrato a empresa perde {pct(base.sem_contrato_e_extrato.derrota)} das vezes.</p>
      <div className="table-scroll"><table className="data-table">
        <thead><tr><th>Documento</th><th className="num">Falta em</th><th className="num">Derrota com</th><th className="num">Derrota sem</th>
          <th className="num">Custo médio com</th><th className="num">Custo médio sem</th><th className="num">Economia se chegassem <InfoTip texto={d.premissa_valor_em_jogo} /></th></tr></thead>
        <tbody>{base.documentos.map((doc) => <tr key={doc.tipo} className={doc.muda_resultado ? "" : "row-muted"}>
          <td>{doc.nome}{!doc.muda_resultado && <small className="cell-sub">não muda o resultado</small>}</td>
          <td className="num">{pct(doc.ausente_pct)}</td>
          <td className="num">{pct(doc.derrota_com)}</td>
          <td className="num">{pct(doc.derrota_sem)}</td>
          <td className="num">{brl(doc.custo_medio_com)}</td>
          <td className="num">{brl(doc.custo_medio_sem)}</td>
          <td className="num">{doc.valor_em_jogo == null ? "—" : brlCompact(doc.valor_em_jogo)}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="footnote">Custo médio = valor pago por processo na base, incluindo os que a empresa ganhou. Parte dos processos sem documento é golpe real, sem documento que exista.</p>
    </article>}
  </div>;
}

function Recommendations({ data }) {
  const [area, setArea] = useState("");
  const areas = useMemo(() => [...new Set(data.recomendacoes.map((card) => card.area))], [data]);
  const cards = data.recomendacoes.filter((card) => !area || card.area === area);
  return <div className="bank-stack">
    <SectionHeader eyebrow="RECOMENDAÇÕES PARA A OPERAÇÃO DA EMPRESA" title="O que construir, e quem constrói">
      Cada recomendação nasce dos motivos que o seu time registrou ao não entregar um documento, ou da base histórica.
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
      <dl className="facts"><div><dt>Processos</dt><dd>{num(card.casos)}</dd></div></dl>
      <p className="footnote"><b>Como medir:</b> {card.indicador}. {card.evidencia}</p>
    </article>)}</div>
  </div>;
}

function Componentes({ score, mercado }) {
  return <div className="componentes">{COMPONENTES.map(([chave, rotulo, dica]) => <Bar key={chave} label={<>{rotulo} <InfoTip texto={dica} /></>}
    value={score.componentes[chave] ?? 0} max={100} tone={tomDoScore(score.componentes[chave])}
    display={score.componentes[chave] == null ? "—" : `${score.componentes[chave]}`}
    caption={mercado ? `mercado: ${mercado.componentes[chave] ?? "—"}` : undefined} />)}</div>;
}

function Firms({ data }) {
  const { regras } = data;
  return <div className="bank-stack">
    <SectionHeader eyebrow="ESCRITÓRIOS CONTRATADOS" title="Com você e no mercado">
      Nota geral de 0 a 100 que mistura economia nos processos, valor dos acordos, se segue a recomendação e acordos aceitos. Cada processo é comparado com processos parecidos, então carteiras de valores diferentes ficam comparáveis. O mercado é anônimo.
    </SectionHeader>
    {data.escritorios.length ? <div className="firm-grid">{data.escritorios.map((firm) => {
      const { score, mercado } = firm;
      const diferenca = mercado?.nota != null && score.nota != null ? score.nota - mercado.nota : 0;
      return <article key={firm.id} className="panel firm-card">
        <div className="firm-head">
          <div><h3>{firm.nome}</h3><p className="muted">{num(firm.advogados)} advogado(s) · {num(score.encerrados)} processos encerrados</p></div>
          <Pill tone={tomDoScore(score.nota)}>Nota geral {score.nota ?? "—"}</Pill>
        </div>
        <Bar label={<>Com você <InfoTip texto={DICAS.nota} /></>} value={score.nota ?? 0} max={100} display={score.nota ?? "—"} tone={tomDoScore(score.nota)} />
        {mercado ? <Bar label="No mercado (anônimo)" value={mercado.nota ?? 0} max={100} display={mercado.nota ?? "—"} tone="muted"
          caption={`${num(mercado.encerrados)} processos encerrados em outros clientes`} /> : <p className="footnote">{firm.motivo_sem_mercado}</p>}
        {firm.leitura && <p className={`reading tone-${diferenca < -5 ? "bad" : diferenca > 5 ? "good" : "neutral"}`}>{firm.leitura}</p>}
        <Componentes score={score} mercado={mercado} />
        <dl className="facts">
          <div><dt>Valor médio dos acordos <InfoTip texto={DICAS.ticket} /></dt><dd>{brl(score.ticket_medio)}{score.ticket_sobre_causa != null && <small> · {pct(score.ticket_sobre_causa)} da causa</small>}</dd></div>
          <div><dt>Economia gerada <InfoTip texto={DICAS.economia} /></dt><dd>{brlCompact(score.economia_total)}</dd></div>
        </dl>
      </article>;
    })}</div> : <p className="empty-line">Nenhum escritório com decisões registradas.</p>}
    <p className="footnote">O mercado só aparece com ao menos {regras.min_outros_clientes} outros clientes e {regras.min_encerrados_mercado} processos encerrados fora desta empresa.</p>
  </div>;
}

function Lawyers({ data }) {
  return <div className="bank-stack">
    <SectionHeader eyebrow="ADVOGADOS NOS SEUS PROCESSOS" title="Quem executa a política">
      Ranking pela nota geral de 0 a 100. Passe o mouse no "i" de cada coluna para ver o que ela mede. Com menos de {data.regras.min_encerrados_ranking} processos encerrados, o advogado aparece sem posição.
    </SectionHeader>
    <article className="panel">
      {data.advogados.length ? <div className="table-scroll"><table className="data-table tabela-advogados">
        <thead><tr><th>#</th><th>Advogado</th>
          <th className="num">Processos encerrados <InfoTip texto={DICAS.encerrados} /></th>
          <th className="num">Nota geral <InfoTip texto={DICAS.nota} /></th>
          {COMPONENTES.map(([chave, rotulo, dica]) => <th key={chave} className="num">{rotulo} <InfoTip texto={dica} /></th>)}
          <th className="num">Valor médio dos acordos <InfoTip texto={DICAS.ticket} /></th>
          <th className="num">Economia gerada <InfoTip texto={DICAS.economia} /></th></tr></thead>
        <tbody>{data.advogados.map((lawyer, index) => {
          const s = lawyer.score;
          return <tr key={lawyer.id} className={s.amostra_suficiente ? "" : "row-muted"}>
            <td>{s.amostra_suficiente ? index + 1 : "—"}</td>
            <td><strong>{lawyer.nome}</strong><small className="cell-sub">{lawyer.escritorio || "Sem escritório"}</small></td>
            <td className="num">{num(s.encerrados)}</td>
            <td className="num">{s.amostra_suficiente ? <Pill tone={tomDoScore(s.nota)}>{s.nota ?? "—"}</Pill> : <small>{s.nota ?? "—"} · poucos encerrados</small>}</td>
            {COMPONENTES.map(([chave]) => <td key={chave} className="num">{s.componentes[chave] ?? "—"}</td>)}
            <td className="num">{brl(s.ticket_medio)}{s.ticket_sobre_causa != null && <small className="cell-sub">{pct(s.ticket_sobre_causa)} da causa</small>}</td>
            <td className="num">{brlCompact(s.economia_total)}</td>
          </tr>;
        })}</tbody>
      </table></div> : <p className="empty-line">Nenhuma decisão registrada ainda.</p>}
    </article>
  </div>;
}

const EXCEPTION_TYPES = {
  ACORDO_ACIMA_DO_LIMITE: { label: "Acordo acima do limite", tone: "bad" },
  DECISAO_DIFERENTE: { label: "Decisão diferente da recomendação", tone: "warn" },
  DECISAO_SEM_CONFERENCIA: { label: "Decisão sem conferência", tone: "neutral" },
};

function Exceptions({ data }) {
  const [type, setType] = useState("");
  const [todos, setTodos] = useState(false);
  const x = data.excecoes;
  const filtrados = x.itens.filter((item) => !type || item.tipo === type);
  const items = todos ? filtrados : filtrados.slice(0, 50);
  return <div className="bank-stack">
    <SectionHeader eyebrow="GESTÃO POR EXCEÇÃO" title="O que fugiu da política">
      Em vez de acompanhar tudo, olhe o que saiu do combinado: acordo acima do limite, decisão diferente da recomendação e decisão sem abrir documento quando o motor pediu conferência.
    </SectionHeader>
    <div className="chips" role="group" aria-label="Filtrar exceções">
      <button type="button" className={type ? "chip" : "chip active"} onClick={() => { setType(""); setTodos(false); }}>Todas · {num(x.total)}</button>
      {Object.entries(EXCEPTION_TYPES).map(([key, meta]) => <button type="button" key={key} className={key === type ? "chip active" : "chip"} onClick={() => { setType(key); setTodos(false); }}>
        {meta.label} · {num(x.por_tipo[key] || 0)}</button>)}
    </div>
    <article className="panel">
      {items.length ? <ul className="exception-list">{items.map((item, index) => {
        const meta = EXCEPTION_TYPES[item.tipo];
        return <li key={`${item.case_id}-${item.tipo}-${index}`}>
          <div className="exception-main">
            <div className="exception-line"><Pill tone={meta.tone}>{meta.label}</Pill><Link to={`/banco/casos/${item.case_id}`}>{item.case_number}</Link></div>
            <span className="muted">{item.advogado || "—"} · {item.escritorio || "sem escritório"} · {date(item.data)}</span>
            <p>{item.detalhe}{item.motivo ? ` Motivo: ${item.motivo}.` : ""}</p>
          </div>
          <div className="exception-impact"><small>Valor da causa</small><strong>{brl(item.valor_causa)}</strong></div>
        </li>;
      })}</ul> : <p className="empty-line">Nenhuma exceção.</p>}
      {filtrados.length > items.length && <button type="button" className="ghost" onClick={() => setTodos(true)}>Mostrar todas ({num(filtrados.length)})</button>}
    </article>
  </div>;
}
