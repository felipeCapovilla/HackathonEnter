import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { request, sendJson, SESSION_EXPIRED } from "./api";
import { useAction, useResource } from "./hooks";
import { Brand, Icon } from "./Brand";
import { DocumentPanel } from "./DocumentPanel";

const labels = { ACORDO: "Acordo", DEFESA: "Defesa", RECUPERAR: "Recuperar documento", BANCO: "Banco", ADVOGADO_EXTERNO: "Advogado externo", ADMIN_GLOBAL: "Admin global" };
const money = (value) => value == null ? "—" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
const actionText = { ACORDO: "Propor acordo", DEFESA: "Disputar a causa", RECUPERAR: "Solicitar o documento ao banco antes de decidir" };
const recommendationClass = { ACORDO: "agreement", DEFESA: "defense", RECUPERAR: "recover" };
const homeFor = (user) => user.role === "BANCO" ? "/banco" : user.role === "ADVOGADO_EXTERNO" ? "/advogado" : "/admin";

function ErrorNotice({ message, onRetry }) {
  if (!message) return null;
  return <div className="warning" role="alert"><p>{message}</p>{onRetry && <button type="button" onClick={onRetry}>Tentar novamente</button>}</div>;
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
      <div className="login-story-copy"><p className="eyebrow">INTELIGÊNCIA JURÍDICA EM ESCALA</p>
        <h2>Inteligência que<br />impulsiona<br /><span>a justiça.</span></h2>
        <p>Conecte documentos, política e decisões em uma operação mais eficiente.</p>
        <div className="story-steps"><span><Icon name="files" />Analise</span><span><Icon name="spark" />Decida</span><span><Icon name="chart" />Acompanhe</span></div>
      </div>
      <p className="story-footer">PESSOAS. TECNOLOGIA. EFICIÊNCIA.</p>
    </aside>
    <section className="login-form-area"><div className="login-card">
    <Brand compact />
    <p className="eyebrow">BEM-VINDO AO ENTEROS</p><h1>Acesse sua operação.</h1><p className="login-description">Entre no EnterAgree para acompanhar seus processos e transformar dados em decisões.</p>
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
  const description = user.role === "ADMIN_GLOBAL" ? "Gerencie bancos e os profissionais que fazem parte da plataforma." : isMonitoring ? "Acompanhe decisões e a aderência à política de acordos do seu banco." : user.role === "BANCO" ? "Organize processos, atribua responsáveis e acompanhe cada decisão." : "Consulte seus processos e encontre a recomendação para cada caso.";
  const initials = user.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("");
  return <div className="app-frame">
    <aside className="sidebar">
      <div className="sidebar-brand"><Brand /><span>ENTERAGREE <span className="product-tag">ENTEROS</span></span></div>
      <nav aria-label="Navegação principal">
        <p className="nav-caption">ESPAÇO DE TRABALHO</p>
        <NavLink to={homeFor(user)} end><Icon name={user.role === "ADMIN_GLOBAL" ? "users" : "files"} />{user.role === "ADMIN_GLOBAL" ? "Administração" : user.role === "BANCO" ? "Processos" : "Meus processos"}</NavLink>
        {user.role === "BANCO" && <NavLink to="/banco/monitoramento"><Icon name="chart" />Monitoramento</NavLink>}
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-message">Mesma justiça.<br /><span>Mais impacto.</span></div>
        <div className="sidebar-account"><span className="avatar">{initials}</span><div><strong>{user.name}</strong><span>{labels[user.role]}</span></div></div>
        <button className="logout-button" disabled={logout.pending} onClick={onLogout}><Icon name="logout" />{logout.pending ? "Saindo…" : "Sair"}</button>
      </div>
    </aside>
    <main className="shell">
      <header className="topbar"><div><span className="topbar-product">EnterOS</span><span className="breadcrumb-divider">/</span><span>{user.bank_name || "Administração global"}</span></div>
        <span className="session-badge"><span />Sessão ativa</span>
      </header>
      <div className="page-content">
        {!isCase && <section className="page-intro"><p className="eyebrow">{isMonitoring ? "INTELIGÊNCIA DA OPERAÇÃO" : "POLÍTICA DE ACORDOS"}</p><h1>{title} {user.role === "BANCO" && !isMonitoring && <span>Em escala.</span>}</h1><p>{description}</p></section>}
        <ErrorNotice message={logout.error} />
        {children}
      </div>
    </main>
  </div>;
}

function Cases({ user }) {
  const cases = useResource("/cases");
  const lawyers = useResource(user.role === "BANCO" ? "/bank/lawyers" : null);
  const action = useAction();
  const navigate = useNavigate();
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
  return <section className={user.role === "BANCO" ? "role-layout" : "workspace"}>
    <div className="case-overview"><Metric label={user.role === "BANCO" ? "Processos cadastrados" : "Processos atribuídos"} value={cases.data?.length ?? "—"} />
      {user.role === "BANCO" && <><Metric label="Com responsável" value={cases.data?.filter((item) => item.assigned_lawyer_id).length ?? "—"} /><Metric label="Aguardando atribuição" value={cases.data?.filter((item) => !item.assigned_lawyer_id).length ?? "—"} /></>}
    </div>
    <ErrorNotice message={action.error} />
    {user.role === "BANCO" && <article className="panel">
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
      <div className="panel-heading"><div><h2>{user.role === "BANCO" ? "Processos do banco" : "Meus processos"}</h2><p>{user.role === "BANCO" ? "Da abertura à decisão, em um só lugar." : "Os casos sob sua responsabilidade."}</p></div><span className="count-badge">{cases.data?.length ?? "—"}</span></div>
      <ErrorNotice message={cases.error} onRetry={cases.reload} />
      {cases.loading && <p role="status">Carregando processos…</p>}
      {cases.data?.length ? <div className="cases">{cases.data.map((item) =>
        <Link className="case-card link-card" key={item.id} to={`${homeFor(user)}/casos/${item.id}`}>
          <span className="case-card-icon"><Icon name="files" /></span><span className="case-card-content"><strong>{item.case_number}</strong><span>{item.uf} · {money(item.value_of_claim)}</span><small className={item.assigned_lawyer_id ? "assignment-tag assigned" : "assignment-tag"}>{item.assigned_lawyer_id ? "Responsável atribuído" : "Sem responsável"}</small></span><Icon name="arrow" />
        </Link>)}
      </div> : !cases.loading && !cases.error && <div className="empty-state"><Icon name="files" /><p>Nenhum processo disponível.</p><span>{user.role === "BANCO" ? "Os casos cadastrados aparecerão aqui." : "Os casos atribuídos pelo banco aparecerão aqui."}</span></div>}
    </article>
  </section>;
}

function CaseRoute({ user }) {
  const { caseId } = useParams();
  return <CaseDetail key={caseId} caseId={caseId} user={user} />;
}

function CaseDetail({ caseId, user }) {
  const resource = useResource(`/cases/${caseId}`);
  const lawyers = useResource(user.role === "BANCO" ? "/bank/lawyers" : null);
  const action = useAction();
  const detail = resource.data;
  const recommendation = detail?.analyses?.[0];
  const decision = detail?.lawyer_decisions?.[0];
  const busy = action.pending || resource.loading;
  const processingDocuments = detail?.documents.some((document) => ["UPLOADED", "EXTRACTING"].includes(document.status));
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
      <div className="case-title"><div><p className="eyebrow">PROCESSO</p><h2>{detail.case.case_number}</h2><p>{detail.case.uf} · {money(detail.case.value_of_claim)}</p></div>
        {user.role === "ADVOGADO_EXTERNO" && <button className="primary" disabled={busy} onClick={analyze}><Icon name="spark" />Avaliar risco e recomendação</button>}
      </div>
      {user.role === "BANCO" && <article className="panel"><h3>Advogado responsável</h3>
        <select aria-label="Advogado responsável" value={detail.case.assigned_lawyer_id || ""} disabled={busy || lawyers.loading || Boolean(lawyers.error)} onChange={assign}>
          <option value="">Sem responsável</option>
          {detail.case.assigned_lawyer_id && !(lawyers.data || []).some((lawyer) => lawyer.id === detail.case.assigned_lawyer_id) && <option value={detail.case.assigned_lawyer_id}>Responsável indisponível</option>}
          {(lawyers.data || []).map((lawyer) => <option key={lawyer.id} value={lawyer.id}>{lawyer.name} · {lawyer.email}</option>)}
        </select>
        <ErrorNotice message={lawyers.error} onRetry={lawyers.reload} />
      </article>}
      <div className="cards"><DocumentPanel caseId={caseId} documents={detail.documents} canUpload={user.role === "BANCO"} onUploaded={resource.reload} />
      <article className="panel analysis"><h3>Saída da ferramenta</h3>
        {recommendation ? <>
          <div className={`recommendation ${recommendationClass[recommendation.recommendation] || "defense"}`}><span><Icon name="spark" />Recomendação da política</span><strong>{labels[recommendation.recommendation] || recommendation.recommendation}</strong></div>
          <p><b>Ação indicada:</b> {actionText[recommendation.recommendation] || recommendation.recommendation}</p>
          {recommendation.policy_output?.recuperacao && <div className="price-block"><span>Documento a solicitar · ganho esperado</span><strong>{labels[recommendation.policy_output.recuperacao.documento.toUpperCase()] || recommendation.policy_output.recuperacao.documento} · {money(recommendation.policy_output.recuperacao.ganho_estimado)}</strong></div>}
          {recommendation.pricing?.target_value != null && <div className="price-block"><span>{recommendation.pricing.negotiable === false ? "Valor único de acordo" : "Faixa de negociação"}</span><strong>{recommendation.pricing.negotiable === false ? money(recommendation.pricing.target_value) : `${money(recommendation.pricing.opening_value)} a ${money(recommendation.pricing.walk_away_value)}`}</strong>{recommendation.pricing.negotiable !== false && <small>Alvo {money(recommendation.pricing.target_value)} · acima de {money(recommendation.pricing.walk_away_value)} é defesa</small>}</div>}
          <ul>{recommendation.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
        </> : <p className="muted">Aguardando avaliação do advogado.</p>}
      </article></div>
      {user.role === "ADVOGADO_EXTERNO" && recommendation && <article className="panel decision"><h3>Registrar decisão</h3>
        <form key={recommendation.id} onSubmit={decide}>
          <fieldset className="form-fields" disabled={busy}>
            <label>Ação<select aria-label="Ação" name="action" defaultValue={recommendation.recommendation}><option value="ACORDO">Acordo</option><option value="DEFESA">Defesa</option><option value="RECUPERAR">Recuperar documento</option></select></label>
            <label>Valor proposto<input name="value" type="number" min="0" step="0.01" /></label>
            <label>Justificativa<textarea name="reason" maxLength="2000" /></label>
            <button>Registrar decisão</button>
          </fieldset>
        </form>
      </article>}
      {decision && <p className="registered"><Icon name="check" />Decisão registrada pelo advogado: {labels[decision.action] || decision.action}</p>}
    </>}
  </section>;
}

function Monitoring() {
  const resource = useResource("/monitoring");
  const data = resource.data;
  return <article className="panel"><h2>Monitoramento do Banco</h2>
    <ErrorNotice message={resource.error} onRetry={resource.reload} />
    {resource.loading && <p role="status">Carregando…</p>}
    {data && <div className="monitor"><Metric label="Análises" value={data.total_analyses} /><Metric label="Decisões" value={data.total_lawyer_decisions} /><Metric label="Aderência" value={data.adherence_rate == null ? "—" : `${(data.adherence_rate * 100).toFixed(1)}%`} /></div>}
  </article>;
}

function Metric({ label, value }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
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
  return <article className="panel contract-panel"><h2>Contrato banco–escritório</h2>
    <p className="muted">Só entram termos que mudam o custo entre acordar e defender. Mensalidade e valor fixo por caso novo são pagos em qualquer desfecho e não afetam a decisão.</p>
    <label>Banco<select aria-label="Banco do contrato" value={selected} onChange={(event) => { setBankId(event.target.value); setPreview(null); }}>
      {(banks || []).map((bank) => <option key={bank.id} value={bank.id}>{bank.name}</option>)}
    </select></label>
    <ErrorNotice message={contract.error} onRetry={contract.reload} />
    <ErrorNotice message={save.error} />
    <ErrorNotice message={simulate.error} />
    {contract.loading && <p role="status">Carregando contrato…</p>}
    {parameters && <form key={`${selected}-${contract.data.version}`} onSubmit={onSave}><fieldset className="form-fields" disabled={save.pending || simulate.pending}>
      <p className="eyebrow">{contract.data.version === 0 ? "CONTRATO PADRÃO · NENHUMA VERSÃO CADASTRADA" : `VERSÃO VIGENTE · V${contract.data.version}`}</p>
      {HONORARIOS.map(([key, label]) => <div className="contract-row" key={key}>
        <label>{label}<select name={`${key}.tipo`} defaultValue={parameters[key].tipo}>{TIPOS_HONORARIO.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
        <label>Valor (R$ ou %)<input name={`${key}.valor`} type="number" min="0" step="0.01" defaultValue={initialValue(parameters[key])} /></label>
      </div>)}
      <div className="contract-row">
        <label>Custo do tempo (% ao mês)<input name="custo_mensal_tempo" type="number" min="0" max="10" step="0.1" defaultValue={percent(parameters.custo_mensal_tempo)} /></label>
        <label>Duração esperada (meses)<input name="duracao_meses" type="number" min="0" max="120" step="1" defaultValue={parameters.duracao_meses} /></label>
      </div>
      <label>Teto de alçada (% do valor da causa, opcional)<input name="teto_alcada_fator" type="number" min="1" max="100" step="1" defaultValue={percent(parameters.teto_alcada_fator)} /></label>
      <div className="contract-row">
        <button type="button" onClick={onSimulate}>{simulate.pending ? "Simulando…" : "Simular impacto na carteira"}</button>
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
  return <section className="role-layout"><article className="panel"><h2>Bancos</h2>
    <ErrorNotice message={banks.error} onRetry={banks.reload} />
    <ErrorNotice message={bankAction.error} />
    <form onSubmit={addBank}><fieldset className="form-fields" disabled={bankAction.pending}>
      <label>Nome<input name="name" required minLength="2" maxLength="120" /></label><button>{bankAction.pending ? "Salvando…" : "Cadastrar banco"}</button>
    </fieldset></form>
    {banks.loading && <p role="status">Carregando bancos…</p>}
    <ul>{(banks.data || []).map((bank) => <li key={bank.id}>{bank.name}</li>)}</ul>
  </article><article className="panel"><h2>Cadastro de advogados e usuários</h2>
    <ErrorNotice message={users.error} onRetry={users.reload} />
    <ErrorNotice message={userAction.error} />
    <form onSubmit={addUser}><fieldset className="form-fields" disabled={userAction.pending}>
      <label>Nome<input name="name" required minLength="2" maxLength="120" /></label>
      <label>E-mail<input name="email" type="email" required maxLength="254" autoComplete="off" /></label>
      <label>Senha inicial (15+ caracteres)<input name="password" type="password" minLength="15" maxLength="128" required autoComplete="new-password" /></label>
      <label>Perfil<select name="role" value={role} onChange={(event) => setRole(event.target.value)}><option value="ADVOGADO_EXTERNO">Advogado externo</option><option value="BANCO">Banco</option><option value="ADMIN_GLOBAL">Admin global</option></select></label>
      <label>Banco<select aria-label="Banco" name="bank_id" value={bankId ?? banks.data?.[0]?.id ?? ""} onChange={(event) => setBankId(event.target.value)} required={role !== "ADMIN_GLOBAL"} disabled={role === "ADMIN_GLOBAL" || banks.loading}>
        <option value="">Selecione o banco</option>{(banks.data || []).map((bank) => <option key={bank.id} value={bank.id}>{bank.name}</option>)}
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
      <Route path="/banco/monitoramento" element={user.role === "BANCO" ? <Monitoring /> : <Navigate to={base} replace />} />
      <Route path="/advogado" element={user.role === "ADVOGADO_EXTERNO" ? <Cases user={user} /> : <Navigate to={base} replace />} />
      <Route path="/advogado/casos/:caseId" element={user.role === "ADVOGADO_EXTERNO" ? <CaseRoute user={user} /> : <Navigate to={base} replace />} />
      <Route path="/admin" element={user.role === "ADMIN_GLOBAL" ? <Admin /> : <Navigate to={base} replace />} />
      <Route path="*" element={<Navigate to={base} replace />} />
    </Routes>
  </Shell>;
}
