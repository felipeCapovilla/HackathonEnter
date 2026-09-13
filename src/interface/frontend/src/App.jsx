import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { request, sendJson, SESSION_EXPIRED } from "./api";
import { useAction, useResource } from "./hooks";
import { Brand, Icon } from "./Brand";
import { DocumentPanel } from "./DocumentPanel";
import BankDashboard from "./banco/BankDashboard";
import { DocumentRequestsPanel } from "./banco/DocumentRequestsPanel";
import { BuscaProcessos } from "./banco/BuscaProcessos";
import { ResultadoProcesso } from "./banco/ResultadoProcesso";
import { useActiveTime } from "./useActiveTime";
import { MinhaFila } from "./advogado/MinhaFila";
import CasoAdvogadoRota from "./advogado/CasoAdvogado";

const labels = { ACORDO: "Acordo", DEFESA: "Defesa", RECUPERAR: "Pedir documento", BANCO: "Empresa", ADVOGADO_EXTERNO: "Advogado externo", ADMIN_GLOBAL: "Admin global" };
const money = (value) => value == null ? "—" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
const actionText = { ACORDO: "Propor acordo", DEFESA: "Seguir com a defesa no processo", RECUPERAR: "Pedir o documento que falta antes de decidir" };
const documentoFaltante = { contrato: "Contrato", extrato: "Extrato", comprovante_credito: "Comprovante de crédito" };
const recommendationClass = { ACORDO: "agreement", DEFESA: "defense", RECUPERAR: "recover" };
const homeFor = (user) => user.role === "BANCO" ? "/banco" : user.role === "ADVOGADO_EXTERNO" ? "/advogado" : "/admin";

const dateFormat = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
const shortDate = (value) => value ? dateFormat.format(new Date(value)) : "—";
/** Taxa em percentual. `null` não é 0%: é "ainda não há o que medir". */
const rate = (value) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;
/**
 * Um processo é ativo até ter desfecho. `active` vem calculado do backend; a
 * queda para `!outcome` cobre respostas antigas que não trazem o campo — sem
 * ela um processo sem `active` cairia em "encerrados" e sumiria da tela.
 */
const isActive = (item) => item.active ?? !item.outcome;

/**
 * Estágio do processo. Vem do backend em `detail.stage`; a derivação local é
 * o fallback para respostas que não trazem o campo.
 *
 *   ABERTO     sem decisão — tudo liberado
 *   DECIDIDO   decidido, sem desfecho — negociação correndo
 *   ENCERRADO  com desfecho — nada mais se altera
 */
const stageOf = (detail, decision) =>
  detail?.stage ?? (decision?.outcome ? "ENCERRADO" : decision ? "DECIDIDO" : "ABERTO");

function Locked({ children }) {
  return <p className="locked"><Icon name="lock" />{children}</p>;
}

/**
 * Desfechos possíveis de um processo.
 * `favoravel` alimenta a cor na tela e precisa espelhar FAVORABLE_OUTCOMES do backend.
 */
const OUTCOMES = {
  ACORDO_ACEITO: { label: "Acordo aceito", hint: "O autor aceitou a proposta", favoravel: true },
  ACORDO_RECUSADO: { label: "Acordo recusado", hint: "O autor não aceitou a proposta", favoravel: false },
  SENTENCA_FAVORAVEL: { label: "Sentença favorável", hint: "A empresa venceu a causa", favoravel: true },
  SENTENCA_DESFAVORAVEL: { label: "Sentença desfavorável", hint: "A empresa foi condenada", favoravel: false },
};

function ErrorNotice({ message, onRetry }) {
  if (!message) return null;
  return <div className="warning" role="alert"><p>{message}</p>{onRetry && <button type="button" onClick={onRetry}>Tentar novamente</button>}</div>;
}

function Metric({ label, value, hint, tone = "" }) {
  return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</div>;
}

function Login({ onLogin, notice }) {
  const action = useAction();
  const submit = (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    action.run(async () => {
      await sendJson("/auth/login", { email: form.get("email").trim(), password: form.get("password") });
      const user = await request("/auth/me");
      if (!user) throw new Error("O navegador não manteve a sessão. Verifique se a interface e a API usam o mesmo endereço.");
      onLogin(user);
    });
  };
  return <main className="login-page">
    <aside className="login-story">
      <Brand />
      <div className="login-story-copy"><p className="eyebrow">Inteligência jurídica em escala</p>
        <h2>Inteligência que<br />impulsiona<br /><span>a justiça.</span></h2>
        <p>Conecte documentos, política e decisões em uma operação mais eficiente.</p>
        <div className="story-steps"><span><Icon name="files" />Analise</span><span><Icon name="spark" />Decida</span><span><Icon name="chart" />Acompanhe</span></div>
      </div>
      <p className="story-footer">PESSOAS. TECNOLOGIA. EFICIÊNCIA.</p>
    </aside>
    <section className="login-form-area"><div className="login-card">
    <Brand compact />
    <p className="eyebrow">Bem-vindo</p><h1>Acesse sua operação.</h1><p className="login-description">Entre para acompanhar seus processos e transformar dados em decisões.</p>
    {notice && <p role="status">{notice}</p>}
    <form onSubmit={submit}>
      <fieldset className="form-fields" disabled={action.pending}>
        <label>E-mail<input name="email" type="email" required autoComplete="username" /></label>
        <label>Senha<input name="password" type="password" required autoComplete="current-password" /></label>
        <ErrorNotice message={action.error} />
        <button>{action.pending ? "Entrando…" : <>Entrar<Icon name="arrow" /></>}</button>
      </fieldset>
    </form>
    <p className="login-footnote"><Icon name="shield" />Acesso restrito aos usuários cadastrados.</p>
  </div><p className="login-signature">MESMA JUSTIÇA. MAIS IMPACTO.</p></section></main>;
}

function Shell({ user, onLogout, logout, children }) {
  const { pathname } = useLocation();
  const isCase = pathname.includes("/casos/");
  const isMonitoring = pathname.endsWith("/monitoramento");
  const title = user.role === "ADMIN_GLOBAL" ? "Uma operação conectada." : isMonitoring ? "Resultados que importam." : user.role === "BANCO" ? "Do dado à decisão." : "Seu próximo passo, com clareza.";
  const description = user.role === "ADMIN_GLOBAL" ? "Gerencie empresas e os profissionais que fazem parte da plataforma." : isMonitoring ? "Efetividade, documentos, escritórios e exceções da política de acordos da sua empresa." : user.role === "BANCO" ? "Organize processos, atribua responsáveis e acompanhe cada decisão." : "Consulte seus processos e encontre a recomendação para cada caso.";
  const initials = user.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("");
  return <div className="app-frame">
    <aside className="sidebar">
      <div className="sidebar-brand"><Brand /></div>
      <nav aria-label="Navegação principal">
        <p className="nav-caption">Espaço de trabalho</p>
        <NavLink to={homeFor(user)} end><Icon name={user.role === "ADMIN_GLOBAL" ? "users" : "files"} />{user.role === "ADMIN_GLOBAL" ? "Administração" : user.role === "BANCO" ? "Processos" : "Meus processos"}</NavLink>
        {user.role === "BANCO" && <NavLink to="/banco/monitoramento"><Icon name="chart" />Painel da empresa</NavLink>}
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-message">Mesma justiça.<br /><span>Mais impacto.</span></div>
        <div className="sidebar-account"><span className="avatar">{initials}</span><div><strong>{user.name}</strong><span>{labels[user.role]}{user.is_manager ? " · gestor" : ""}</span></div></div>
        <button className="logout-button" disabled={logout.pending} onClick={onLogout}><Icon name="logout" />{logout.pending ? "Saindo…" : "Sair"}</button>
      </div>
    </aside>
    <main className="shell">
      <header className="topbar"><div><span className="topbar-product">{user.bank_name || "Administração global"}</span></div>
        <span className="session-badge"><span />Sessão ativa</span>
      </header>
      <div className="page-content">
        {!isCase && <section className="page-intro"><p className="eyebrow">{isMonitoring ? "Inteligência da operação" : "Política de acordos"}</p><h1>{title} {user.role === "BANCO" && !isMonitoring && <span>Em escala.</span>}</h1><p>{description}</p></section>}
        <ErrorNotice message={logout.error} />
        {children}
      </div>
    </main>
  </div>;
}

/**
 * Painel do próprio advogado.
 *
 * Êxito e aderência ficam lado a lado de propósito: medem coisas diferentes.
 * Aderência diz se ele seguiu a política; êxito diz se deu certo. Quem sempre
 * acata tem 100% de aderência e pode ter êxito baixo — e o contrário também.
 */
function LawyerPerformance() {
  const resource = useResource("/lawyer/performance");
  const data = resource.data;
  return <article className="panel full-width">
    <div className="panel-heading">
      <span className="panel-icon"><Icon name="trophy" /></span>
      <div><h2>Meu desempenho</h2><p>Como seus processos terminaram e o quanto você seguiu a política.</p></div>
    </div>
    <ErrorNotice message={resource.error} onRetry={resource.reload} />
    {resource.loading && <p role="status">Carregando desempenho…</p>}
    {data && <>
      <div className="case-overview">
        <div className="metric hero">
          <span>Taxa de êxito</span>
          <strong>{rate(data.success_rate)}</strong>
          <div className="bar"><span style={{ width: `${(data.success_rate ?? 0) * 100}%` }} /></div>
          <small>{data.outcomes_recorded ? `${data.outcomes_recorded} processo(s) com desfecho registrado` : "Registre o desfecho de um processo para ver a taxa"}</small>
        </div>
        <div className="metric">
          <span>Aderência à política</span>
          <strong>{rate(data.adherence_rate)}</strong>
          <div className="bar amber"><span style={{ width: `${(data.adherence_rate ?? 0) * 100}%` }} /></div>
          <small>Quantas vezes você seguiu a recomendação</small>
        </div>
        <Metric label="Processos ativos" value={data.active_cases} hint="Ainda sem desfecho" />
        <Metric label="Encerrados" value={data.closed_cases} hint={data.pending_outcome ? `${data.pending_outcome} decisão(ões) aguardando desfecho` : "Todos os desfechos registrados"} />
      </div>
      {Boolean(data.outcomes_recorded) && <div className="case-card-tags" style={{ marginTop: "var(--s5)" }}>
        {Object.entries(data.outcomes).map(([key, count]) =>
          <span key={key} className={`pill ${OUTCOMES[key]?.favoravel ? "success" : "danger"}`}>{OUTCOMES[key]?.label || key}: {count}</span>)}
      </div>}
    </>}
  </article>;
}

/** Pílulas de situação do processo, na ordem em que o advogado precisa delas. */
function CaseStatus({ item }) {
  if (item.outcome) {
    const outcome = OUTCOMES[item.outcome];
    return <span className={`pill ${outcome?.favoravel ? "success" : "danger"}`}>{outcome?.label || item.outcome}</span>;
  }
  if (item.decided) return <span className="pill info dot">Em negociação</span>;
  return <span className="pill amber dot">Aguardando avaliação</span>;
}

function CaseCard({ item, to }) {
  const estado = !isActive(item) ? "closed" : item.decided ? "decided" : "open";
  return <Link className={`case-card link-card ${estado}`} to={to}>
    <span className="case-card-icon"><Icon name={isActive(item) ? "files" : "archive"} /></span>
    <span className="case-card-content">
      <strong>{item.case_number}</strong>
      <span className="case-card-meta">
        {item.uf}<span className="sep">·</span>{money(item.value_of_claim)}
        <span className="sep">·</span><Icon name="clock" className="tiny" />{shortDate(item.created_at)}
        {item.document_count > 0 && <><span className="sep">·</span>{item.document_count} doc.</>}
      </span>
      <span className="case-card-tags">
        <CaseStatus item={item} />
        {!item.assigned_lawyer_id && <span className="assignment-tag">Sem responsável</span>}
        {item.condemnation_value > 0 && <span className="pill danger">Condenação {money(item.condemnation_value)}</span>}
      </span>
    </span>
    <Icon name="arrow" />
  </Link>;
}

const SORTS = {
  recent: { label: "Mais recentes primeiro", compare: (a, b) => new Date(b.created_at) - new Date(a.created_at) },
  oldest: { label: "Mais antigos primeiro", compare: (a, b) => new Date(a.created_at) - new Date(b.created_at) },
};

/**
 * Lista de processos com separação ativo/encerrado.
 *
 * Ativo é o processo sem desfecho registrado — inclui o que já tem decisão e
 * está em negociação. O que encerra o caso é o desfecho, não a decisão: entre
 * decidir e o autor responder pode levar semanas, e nesse intervalo o processo
 * ainda está na mesa do advogado.
 */
function CaseList({ cases, user }) {
  const [tab, setTab] = useState("active");
  const [sort, setSort] = useState("recent");
  const base = homeFor(user);

  const { active, closed } = useMemo(() => {
    const items = [...(cases || [])].sort(SORTS[sort].compare);
    return { active: items.filter(isActive), closed: items.filter((item) => !isActive(item)) };
  }, [cases, sort]);

  const shown = tab === "active" ? active : closed;
  return <>
    <div className="list-toolbar">
      <div className="tabs" role="group" aria-label="Situação do processo">
        <button type="button" aria-pressed={tab === "active"} onClick={() => setTab("active")}>
          Ativos <span className="tab-count">{active.length}</span>
        </button>
        <button type="button" aria-pressed={tab === "closed"} onClick={() => setTab("closed")}>
          Encerrados <span className="tab-count">{closed.length}</span>
        </button>
      </div>
      <span className="spacer" />
      <label>Ordenar por
        <select aria-label="Ordenar processos" value={sort} onChange={(event) => setSort(event.target.value)}>
          {Object.entries(SORTS).map(([value, option]) => <option key={value} value={value}>{option.label}</option>)}
        </select>
      </label>
    </div>
    {shown.length ? <div className="cases">
      {shown.map((item) => <CaseCard key={item.id} item={item} to={`${base}/casos/${item.id}`} />)}
    </div> : <div className="empty-state">
      <Icon name={tab === "active" ? "files" : "archive"} />
      <p>{tab === "active" ? "Nenhum processo ativo" : "Nenhum processo encerrado"}</p>
      <span>{tab === "active"
        ? (user.role === "BANCO" ? "Os processos abertos aparecerão aqui." : "Os casos atribuídos pela empresa aparecerão aqui.")
        : "Um processo entra aqui quando o advogado registra o desfecho."}</span>
    </div>}
  </>;
}

function Cases({ user }) {
  const cases = useResource("/cases");
  const lawyers = useResource(user.role === "BANCO" ? "/bank/lawyers" : null);
  const action = useAction();
  const navigate = useNavigate();
  const isBank = user.role === "BANCO";
  const create = (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    action.run(async () => {
      const item = await sendJson("/cases", {
        case_number: form.get("case_number").trim(), uf: form.get("uf").trim().toUpperCase(),
        value_of_claim: Number(form.get("value_of_claim")), sub_subject: form.get("sub_subject").trim() || null,
        assigned_lawyer_id: form.get("assigned_lawyer_id") || null,
      });
      navigate(`/banco/casos/${item.id}`);
    });
  };
  const items = cases.data || [];
  return <section className={isBank ? "role-layout" : "workspace"}>
    {isBank && <div className="case-overview">
      <Metric label="Processos cadastrados" value={items.length || "—"} />
      <Metric label="Ativos" value={items.filter(isActive).length} hint="Sem desfecho registrado" />
      <Metric label="Com responsável" value={items.filter((item) => item.assigned_lawyer_id).length} />
      <Metric label="Aguardando atribuição" value={items.filter((item) => !item.assigned_lawyer_id).length} />
    </div>}
    {!isBank && <LawyerPerformance />}
    {isBank && <BuscaProcessos />}
    <ErrorNotice message={action.error} />
    {isBank && <article className="panel">
      <div className="panel-heading"><span className="panel-icon"><Icon name="files" /></span><div><h2>Abrir novo processo</h2><p>Comece pelos dados principais do caso.</p></div></div>
      <form onSubmit={create}>
        <fieldset className="form-fields" disabled={action.pending}>
          <label>Número do processo<input name="case_number" required minLength="3" maxLength="80" /></label>
          <div className="row"><label>UF<input name="uf" defaultValue="SP" required minLength="2" maxLength="2" /></label>
            <label>Valor da causa<input name="value_of_claim" type="number" min="0" step="0.01" required /></label></div>
          <label>Subassunto<input name="sub_subject" defaultValue="Não reconhecimento de empréstimo" maxLength="120" /></label>
          <label>Advogado responsável<select name="assigned_lawyer_id" defaultValue="" disabled={lawyers.loading}>
            <option value="">Atribuir depois</option>
            {(lawyers.data || []).map((lawyer) => <option key={lawyer.id} value={lawyer.id}>{lawyer.name} · {lawyer.email}</option>)}
          </select></label>
          <button>{action.pending ? "Salvando…" : <>Abrir processo<Icon name="arrow" /></>}</button>
        </fieldset>
      </form>
      <ErrorNotice message={lawyers.error} onRetry={lawyers.reload} />
    </article>}
    <article className="panel">
      <div className="panel-heading"><div><h2>{isBank ? "Processos da empresa" : "Meus processos"}</h2><p>{isBank ? "Da abertura à decisão, em um só lugar." : "Os casos sob sua responsabilidade."}</p></div><span className="count-badge">{items.length}</span></div>
      <ErrorNotice message={cases.error} onRetry={cases.reload} />
      {cases.loading && <p role="status">Carregando processos…</p>}
      {!cases.loading && !cases.error && <CaseList cases={items} user={user} />}
    </article>
  </section>;
}

function CaseRoute({ user }) {
  const { caseId } = useParams();
  return <CaseDetail key={caseId} caseId={caseId} user={user} />;
}

/**
 * Registro do desfecho: o que fecha o processo e alimenta a taxa de êxito.
 * Só aparece depois da decisão, e só uma vez — desfecho não se reescreve.
 */
function OutcomeForm({ caseId, decision, onRegistered }) {
  const action = useAction();
  const [escolha, setEscolha] = useState(Object.keys(OUTCOMES)[0]);
  const pedeValor = escolha === "ACORDO_ACEITO" || escolha === "SENTENCA_DESFAVORAVEL";
  const submit = (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    action.run(async () => {
      await sendJson(`/cases/${caseId}/lawyer-decisions/${decision.id}/outcome`, {
        outcome: form.get("outcome"), outcome_note: form.get("outcome_note").trim() || null,
        value: form.get("value") ? Number(form.get("value")) : null,
      });
      onRegistered();
    });
  };
  if (decision.outcome) {
    const outcome = OUTCOMES[decision.outcome];
    return <article className="panel">
      <div className="panel-heading"><div><h3>Desfecho do processo</h3><p>Registrado em {shortDate(decision.outcome_at)}.</p></div></div>
      <p className={`outcome-banner ${outcome?.favoravel ? "success" : "danger"}`}>
        <Icon name={outcome?.favoravel ? "check" : "scale"} />{outcome?.label || decision.outcome}
      </p>
      {decision.outcome_note && <p className="muted" style={{ marginTop: "var(--s4)" }}>{decision.outcome_note}</p>}
    </article>;
  }
  return <article className="panel decision">
    <div className="panel-heading"><span className="panel-icon"><Icon name="scale" /></span>
      <div><h3>Registrar desfecho</h3><p>Como o processo terminou de verdade. É o que gera sua taxa de êxito.</p></div></div>
    <form onSubmit={submit}>
      <fieldset className="form-fields" disabled={action.pending}>
        <div className="outcome-options">
          {Object.entries(OUTCOMES).map(([value, option], index) =>
            <label className="outcome-option" key={value}>
              <input type="radio" name="outcome" value={value} defaultChecked={index === 0} required onChange={() => setEscolha(value)} />
              <span>{option.label}<span className="hint">{option.hint}</span></span>
            </label>)}
        </div>
        {pedeValor && <label>{escolha === "ACORDO_ACEITO" ? "Valor fechado no acordo" : "Valor da condenação"}<input key={escolha} name="value" type="number" min="0" step="0.01" required defaultValue={escolha === "ACORDO_ACEITO" ? decision.proposed_value ?? "" : ""} /></label>}
        <label>Observação (opcional)<textarea name="outcome_note" maxLength="2000" placeholder="Valor efetivamente acordado, particularidade do juízo, etc." /></label>
        <ErrorNotice message={action.error} />
        <button>{action.pending ? "Registrando…" : <>Registrar desfecho<Icon name="check" /></>}</button>
      </fieldset>
    </form>
  </article>;
}

function CaseDetail({ caseId, user }) {
  const resource = useResource(`/cases/${caseId}`);
  const lawyers = useResource(user.role === "BANCO" ? "/bank/lawyers" : null);
  useActiveTime(caseId, user.role === "ADVOGADO_EXTERNO");
  const action = useAction();
  const detail = resource.data;
  const recommendation = detail?.analyses?.[0];
  const decision = detail?.lawyer_decisions?.[0];
  const isLawyer = user.role === "ADVOGADO_EXTERNO";
  const stage = stageOf(detail, decision);
  const encerrado = stage === "ENCERRADO";
  const busy = action.pending || resource.loading;
  const aguardandoLeitura = Boolean(detail?.leitura_ia_ativa) && detail.documents.some((document) =>
    ["COMPLETED", "COMPLETED_WITH_WARNINGS"].includes(document.status)
    && !detail.document_readings?.some((reading) => reading.document_id === document.id)
    && Date.now() - new Date(document.created_at).getTime() < 3 * 60 * 1000);
  const processingDocuments = aguardandoLeitura || detail?.documents.some((document) => ["UPLOADED", "EXTRACTING"].includes(document.status));
  useEffect(() => {
    if (!processingDocuments || resource.loading || resource.error) return;
    const timer = window.setTimeout(resource.reload, 2000);
    return () => window.clearTimeout(timer);
  }, [processingDocuments, resource.loading, resource.error, resource.reload]);
  const assign = (event) => {
    const lawyerId = event.target.value || null;
    action.run(async () => {
      await sendJson(`/cases/${caseId}/assignment`, { assigned_lawyer_id: lawyerId }, "PATCH");
      resource.reload();
    });
  };
  const analyze = () => action.run(async () => {
    await request(`/cases/${caseId}/analyses`, { method: "POST" });
    resource.reload();
  });
  const decide = (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    action.run(async () => {
      await sendJson(`/cases/${caseId}/lawyer-decisions?analysis_id=${recommendation.id}`, {
        action: form.get("action"), proposed_value: form.get("value") ? Number(form.get("value")) : null,
        reason: form.get("reason").trim() || null,
      });
      formElement.reset();
      resource.reload();
    });
  };
  return <section className="workspace">
    <Link to={homeFor(user)}>← Voltar aos processos</Link>
    <ErrorNotice message={resource.error} onRetry={resource.reload} />
    <ErrorNotice message={action.error} />
    {resource.loading && <p role="status">Carregando processo…</p>}
    {detail && <>
      <div className="case-title">
        <div>
          <p className="eyebrow">Processo</p>
          <h2>{detail.case.case_number}</h2>
          <p>{detail.case.uf} · {money(detail.case.value_of_claim)} · aberto em {shortDate(detail.case.created_at)}</p>
          <span className="case-card-tags" style={{ marginTop: "var(--s3)" }}>
            <CaseStatus item={{ outcome: decision?.outcome, decided: Boolean(decision), active: !decision?.outcome }} />
          </span>
        </div>
        {isLawyer && !encerrado && <button className="primary" disabled={busy} onClick={analyze}><Icon name="spark" />Avaliar risco e recomendação</button>}
      </div>
      {user.role === "BANCO" && <article className="panel"><h3>Advogado responsável</h3>
        {encerrado && <Locked>Processo encerrado: o responsável não pode mais ser trocado.</Locked>}
        <select aria-label="Advogado responsável" value={detail.case.assigned_lawyer_id || ""} disabled={busy || encerrado || lawyers.loading || Boolean(lawyers.error)} onChange={assign}>
          <option value="">Sem responsável</option>
          {detail.case.assigned_lawyer_id && !(lawyers.data || []).some((lawyer) => lawyer.id === detail.case.assigned_lawyer_id) && <option value={detail.case.assigned_lawyer_id}>Responsável indisponível</option>}
          {(lawyers.data || []).map((lawyer) => <option key={lawyer.id} value={lawyer.id}>{lawyer.name} · {lawyer.email}</option>)}
        </select>
        <ErrorNotice message={lawyers.error} onRetry={lawyers.reload} />
      </article>}
      <div className="cards"><DocumentPanel caseId={caseId} documents={detail.documents} readings={detail.document_readings} leituraAtiva={Boolean(detail.leitura_ia_ativa)} valueOfClaim={detail.case.value_of_claim} canUpload={user.role === "BANCO"} encerrado={encerrado} onUploaded={resource.reload} />
      <article className="panel analysis"><h3>Saída da ferramenta</h3>
        {recommendation ? <>
          <div className={`recommendation ${recommendationClass[recommendation.recommendation] || "defense"}`}><span><Icon name="spark" />Recomendação da política</span><strong>{labels[recommendation.recommendation] || recommendation.recommendation}</strong></div>
          <p><b>O que fazer:</b> {actionText[recommendation.recommendation] || recommendation.recommendation}</p>
          {recommendation.recommendation === "RECUPERAR" && recommendation.policy_output?.recuperacao && <div className="price-block"><span>Documento que falta · economia esperada se ele chegar</span><strong>{documentoFaltante[recommendation.policy_output.recuperacao.documento] || recommendation.policy_output.recuperacao.documento} · {money(recommendation.policy_output.recuperacao.ganho_estimado)}</strong></div>}
          {recommendation.pricing?.target_value != null && <div className="price-block"><span>{recommendation.pricing.negotiable === false ? "Valor único para propor" : "Quanto oferecer"}</span><strong>{recommendation.pricing.negotiable === false ? money(recommendation.pricing.target_value) : `${money(recommendation.pricing.opening_value)} a ${money(recommendation.pricing.walk_away_value)}`}</strong>{recommendation.pricing.negotiable !== false && <small>Comece em {money(recommendation.pricing.opening_value)}{recommendation.pricing.target_value > recommendation.pricing.opening_value + 0.01 ? ` · meta ${money(recommendation.pricing.target_value)}` : ""} · acima de {money(recommendation.pricing.walk_away_value)}, defender sai mais barato</small>}</div>}
          <ul>{recommendation.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
        </> : <div className="empty-state"><Icon name="spark" /><p>Ainda sem recomendação</p><span>{isLawyer ? "Use “Avaliar risco e recomendação” para calcular o caminho mais barato." : "O advogado responsável ainda não avaliou este processo."}</span></div>}
      </article></div>
      {user.role === "BANCO" && <ResultadoProcesso detail={detail} decision={decision} recommendation={recommendation} />}
      {user.role === "BANCO" && <DocumentRequestsPanel requests={detail.document_requests} onChanged={resource.reload} />}
      {isLawyer && recommendation && !decision && <article className="panel decision">
        <div className="panel-heading"><span className="panel-icon"><Icon name="check" /></span>
          <div><h3>Registrar decisão</h3><p>O que você vai fazer neste processo.</p></div></div>
        <form key={recommendation.id} onSubmit={decide}>
          <fieldset className="form-fields" disabled={busy}>
            <label>Ação<select aria-label="Ação" name="action" defaultValue={recommendation.recommendation}><option value="ACORDO">Acordo</option><option value="DEFESA">Defesa</option><option value="RECUPERAR">Recuperar documento</option></select></label>
            <label>Valor proposto<input name="value" type="number" min="0" step="0.01" /></label>
            <label>Justificativa<textarea name="reason" maxLength="2000" /></label>
            <button>Registrar decisão</button>
          </fieldset>
        </form>
      </article>}
      {decision && <p className="registered"><Icon name="check" />Decisão registrada pelo advogado: {labels[decision.action] || decision.action}{decision.proposed_value != null && ` · ${money(decision.proposed_value)}`}</p>}
      {isLawyer && decision && <OutcomeForm caseId={caseId} decision={decision} onRegistered={resource.reload} />}
    </>}
  </section>;
}

const HONORARIOS = [
  ["honorario_defesa_ganha", "Honorário se a defesa ganhar"],
  ["honorario_defesa_perdida", "Honorário se a defesa perder"],
  ["honorario_acordo", "Honorário por acordo fechado"],
];
const TIPOS_HONORARIO = [["fixo", "R$ fixo"], ["percentual_valor_causa", "% do valor da causa"], ["percentual_condenacao", "% da condenação"]];
const percent = (value) => value == null ? "" : Number((value * 100).toFixed(4));

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

function ContractPanel({ banks }) {
  const [bankId, setBankId] = useState("");
  const selected = bankId || banks?.[0]?.id || "";
  const contract = useResource(selected ? `/admin/banks/${encodeURIComponent(selected)}/contract` : null);
  const save = useAction();
  const simulate = useAction();
  const [preview, setPreview] = useState(null);
  const parameters = contract.data?.parameters;
  const onSimulate = (event) => {
    const form = new FormData(event.currentTarget.form);
    simulate.run(async () => setPreview(await sendJson(`/admin/banks/${encodeURIComponent(selected)}/contract/preview`, readContractForm(form))));
  };
  const onSave = (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    save.run(async () => {
      await sendJson(`/admin/banks/${encodeURIComponent(selected)}/contract`, readContractForm(form));
      setPreview(null);
      contract.reload();
    });
  };
  const initialValue = (honorario) => honorario.tipo === "fixo" ? honorario.valor : percent(honorario.valor);
  const pct = (value) => `${(value * 100).toFixed(1)}%`;
  return <article className="panel contract-panel"><h2>Contrato empresa–escritório</h2>
    <p className="muted">Só entram termos que mudam o custo entre acordar e defender. Mensalidade e valor fixo por caso novo são pagos em qualquer desfecho e não afetam a decisão.</p>
    <label>Empresa<select aria-label="Empresa do contrato" value={selected} onChange={(event) => { setBankId(event.target.value); setPreview(null); }}>
      {(banks || []).map((bank) => <option key={bank.id} value={bank.id}>{bank.name}</option>)}
    </select></label>
    <ErrorNotice message={contract.error} onRetry={contract.reload} />
    <ErrorNotice message={save.error} />
    <ErrorNotice message={simulate.error} />
    {contract.loading && <p role="status">Carregando contrato…</p>}
    {parameters && <form key={`${selected}-${contract.data.version}`} onSubmit={onSave}><fieldset className="form-fields" disabled={save.pending || simulate.pending}>
      <p className="eyebrow">{contract.data.version === 0 ? "Contrato padrão · nenhuma versão cadastrada" : `Versão vigente · v${contract.data.version}`}</p>
      {HONORARIOS.map(([key, label]) => <div className="contract-row" key={key}>
        <label>{label}<select name={`${key}.tipo`} defaultValue={parameters[key].tipo}>{TIPOS_HONORARIO.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
        <label>Valor (R$ ou %)<input name={`${key}.valor`} type="number" min="0" step="0.01" defaultValue={initialValue(parameters[key])} /></label>
      </div>)}
      <div className="contract-row">
        <label>Custo do tempo (% ao mês)<input name="custo_mensal_tempo" type="number" min="0" max="10" step="0.1" defaultValue={percent(parameters.custo_mensal_tempo)} /></label>
        <label>Duração esperada (meses)<input name="duracao_meses" type="number" min="0" max="120" step="1" defaultValue={parameters.duracao_meses} /></label>
      </div>
      <label>Teto de alçada (% do valor da causa, opcional)<input name="teto_alcada_fator" type="number" min="1" max="100" step="1" defaultValue={percent(parameters.teto_alcada_fator)} /></label>
      <label>Quanto ceder na negociação (% entre a proposta inicial e o valor máximo)<input name="concessao" type="number" min="0" max="100" step="1" defaultValue={percent(parameters.concessao)} /></label>
      <div className="contract-row">
        <button type="button" className="ghost" onClick={onSimulate}>{simulate.pending ? "Simulando…" : "Simular impacto na carteira"}</button>
        <button>{save.pending ? "Salvando…" : "Salvar nova versão"}</button>
      </div>
    </fieldset></form>}
    {preview && <div className="contract-preview">
      <div className="monitor">
        <Metric label="Decisões que mudam" value={`${preview.decisoes_alteradas.toLocaleString("pt-BR")} de ${preview.casos.toLocaleString("pt-BR")}`} />
        <Metric label="Economia · contrato vigente" value={pct(preview.contrato_vigente.economia_percentual)} />
        <Metric label="Economia · contrato proposto" value={pct(preview.contrato_proposto.economia_percentual)} />
      </div>
      <p className="muted">{preview.premissas}</p>
    </div>}
  </article>;
}

function Admin() {
  const banks = useResource("/admin/banks");
  const users = useResource("/admin/users");
  const bankAction = useAction();
  const userAction = useAction();
  const [role, setRole] = useState("ADVOGADO_EXTERNO");
  const [bankId, setBankId] = useState(null);
  const addBank = (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    bankAction.run(async () => {
      await sendJson("/admin/banks", { name: form.get("name").trim() });
      formElement.reset();
      banks.reload();
    });
  };
  const addUser = (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    userAction.run(async () => {
      await sendJson("/admin/users", {
        name: form.get("name").trim(), email: form.get("email").trim(), password: form.get("password"), role,
        bank_id: role === "ADMIN_GLOBAL" ? null : form.get("bank_id"),
      });
      formElement.reset();
      setRole("ADVOGADO_EXTERNO");
      setBankId(null);
      users.reload();
    });
  };
  return <section className="role-layout"><article className="panel">
    <div className="panel-heading"><span className="panel-icon"><Icon name="files" /></span><div><h2>Bancos</h2><p>Instituições atendidas pela plataforma.</p></div></div>
    <ErrorNotice message={banks.error} onRetry={banks.reload} />
    <ErrorNotice message={bankAction.error} />
    <form onSubmit={addBank}><fieldset className="form-fields" disabled={bankAction.pending}>
      <label>Nome<input name="name" required minLength="2" maxLength="120" /></label><button>{bankAction.pending ? "Salvando…" : "Cadastrar empresa"}</button>
    </fieldset></form>
    {banks.loading && <p role="status">Carregando empresas…</p>}
    <ul>{(banks.data || []).map((bank) => <li key={bank.id}>{bank.name}</li>)}</ul>
  </article><article className="panel">
    <div className="panel-heading"><span className="panel-icon"><Icon name="users" /></span><div><h2>Advogados e usuários</h2><p>Quem acessa a plataforma e com qual perfil.</p></div></div>
    <ErrorNotice message={users.error} onRetry={users.reload} />
    <ErrorNotice message={userAction.error} />
    <form onSubmit={addUser}><fieldset className="form-fields" disabled={userAction.pending}>
      <label>Nome<input name="name" required minLength="2" maxLength="120" /></label>
      <label>E-mail<input name="email" type="email" required maxLength="254" autoComplete="off" /></label>
      <label>Senha inicial (15+ caracteres)<input name="password" type="password" minLength="15" maxLength="128" required autoComplete="new-password" /></label>
      <label>Perfil<select name="role" value={role} onChange={(event) => setRole(event.target.value)}><option value="ADVOGADO_EXTERNO">Advogado externo</option><option value="BANCO">Banco</option><option value="ADMIN_GLOBAL">Admin global</option></select></label>
      <label>Banco<select aria-label="Banco" name="bank_id" value={bankId ?? banks.data?.[0]?.id ?? ""} onChange={(event) => setBankId(event.target.value)} required={role !== "ADMIN_GLOBAL"} disabled={role === "ADMIN_GLOBAL" || banks.loading}>
        <option value="">Selecione a empresa</option>{(banks.data || []).map((bank) => <option key={bank.id} value={bank.id}>{bank.name}</option>)}
      </select></label>
      <button disabled={role !== "ADMIN_GLOBAL" && (banks.loading || Boolean(banks.error))}>{userAction.pending ? "Salvando…" : "Cadastrar usuário"}</button>
    </fieldset></form>
    {users.loading && <p role="status">Carregando usuários…</p>}
    <ul>{(users.data || []).map((user) => <li key={user.id}>{user.name} · {labels[user.role]} · {user.is_active ? "ativo" : "inativo"}</li>)}</ul>
  </article><ContractPanel banks={banks.data} /></section>;
}

export default function App() {
  const session = useResource("/auth/me");
  const [sessionOverride, setSessionOverride] = useState(undefined);
  const [notice, setNotice] = useState("");
  const logout = useAction();
  const navigate = useNavigate();
  const user = sessionOverride === undefined ? session.data : sessionOverride;

  useEffect(() => {
    const expired = () => {
      setSessionOverride(null);
      setNotice("Sua sessão expirou. Entre novamente.");
      navigate("/login", { replace: true });
    };
    window.addEventListener(SESSION_EXPIRED, expired);
    return () => window.removeEventListener(SESSION_EXPIRED, expired);
  }, [navigate]);

  const onLogin = (nextUser) => {
    setSessionOverride(nextUser);
    setNotice("");
    navigate(homeFor(nextUser), { replace: true });
  };
  const onLogout = () => logout.run(async () => {
    await request("/auth/logout", { method: "POST" });
    setSessionOverride(null);
    setNotice("");
    navigate("/login", { replace: true });
  });

  if (sessionOverride === undefined && (session.loading || session.error)) {
    return <main className="session-page"><section className="login-card">
      {session.loading ? <p role="status">Verificando sessão…</p> : <ErrorNotice message={session.error} onRetry={session.reload} />}
    </section></main>;
  }
  if (!user) return <Routes><Route path="/login" element={<Login onLogin={onLogin} notice={notice} />} /><Route path="*" element={<Navigate to="/login" replace />} /></Routes>;
  const base = homeFor(user);
  return <Shell key={user.id} user={user} onLogout={onLogout} logout={logout}>
    <Routes>
      <Route path="/banco" element={user.role === "BANCO" ? <Cases user={user} /> : <Navigate to={base} replace />} />
      <Route path="/banco/casos/:caseId" element={user.role === "BANCO" ? <CaseRoute user={user} /> : <Navigate to={base} replace />} />
      <Route path="/banco/monitoramento" element={user.role === "BANCO" ? <BankDashboard user={user} /> : <Navigate to={base} replace />} />
      <Route path="/advogado" element={user.role === "ADVOGADO_EXTERNO" ? <MinhaFila desempenho={<LawyerPerformance />} /> : <Navigate to={base} replace />} />
      <Route path="/advogado/casos/:caseId" element={user.role === "ADVOGADO_EXTERNO" ? <CasoAdvogadoRota /> : <Navigate to={base} replace />} />
      <Route path="/admin" element={user.role === "ADMIN_GLOBAL" ? <Admin /> : <Navigate to={base} replace />} />
      <Route path="*" element={<Navigate to={base} replace />} />
    </Routes>
  </Shell>;
}
