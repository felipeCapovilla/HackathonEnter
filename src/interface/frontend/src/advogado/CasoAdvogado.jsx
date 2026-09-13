import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../api";
import { useAction, useResource } from "../hooks";
import { Icon } from "../Brand";
import { LinhaDoTempo, PainelDaFase } from "./PainelDaFase";
import { Recomendacao } from "./Recomendacao";
import { VisualizadorDocumentos } from "./VisualizadorDocumentos";
import { ChatDocumentos } from "./ChatDocumentos";
import { PaineisDoCaso, PainelRecolhivel } from "./PainelRecolhivel";
import { TOM_DA_FASE, moeda } from "./textos";
import "./advogado.css";
import "./caso-workspace.css";

const WORK_TABS = [
  ["evaluation", "Avaliação"],
  ["action", "Próximo passo"],
  ["history", "Histórico"],
];
const NEXT_LABEL = {
  AGUARDANDO_AVALIACAO: "Começar avaliação", REAVALIAR: "Revisar avaliação",
  PRONTO_PARA_DECIDIR: "Ir para decisão", AGUARDANDO_DOCUMENTO: "Ver solicitação",
  EM_NEGOCIACAO: "Registrar retorno", CONTRAPROPOSTA: "Ver contraproposta",
  EM_DEFESA: "Registrar sentença", ENCERRADO: "Ver resultado",
};

export function CasoAdvogado({ caseId }) {
  const recurso = useResource(`/cases/${caseId}`);
  const acao = useAction();
  const [tabChoice, setTabChoice] = useState(null);
  const [mobileView, setMobileView] = useState("documents");
  const [reveal, setReveal] = useState(null);
  const [copyStatus, setCopyStatus] = useState("");
  const workArea = useRef(null);
  const workTabs = useRef({});
  const detalhe = recurso.data;
  const fase = detalhe?.fase;
  const recomendacao = detalhe?.analyses?.[0];
  const processando = detalhe?.documents.some((d) => ["UPLOADED", "EXTRACTING"].includes(d.status));
  const precisaAvaliar = fase && fase.documentos_novos && fase.codigo !== "ENCERRADO";
  const needsEvaluation = !recomendacao || ["AGUARDANDO_AVALIACAO", "REAVALIAR"].includes(fase?.codigo);
  const preferredTab = needsEvaluation && fase?.codigo !== "ENCERRADO" ? "evaluation" : "action";
  // Ao abrir o processo começa na avaliação; se a fase mudar depois, segue a etapa atual.
  const faseAoAbrir = useRef({});
  if (fase && !(caseId in faseAoAbrir.current)) faseAoAbrir.current[caseId] = fase.codigo;
  const abaInicial = faseAoAbrir.current[caseId] === fase?.codigo ? "evaluation" : preferredTab;
  const activeTab = tabChoice && tabChoice.phase === fase?.codigo ? tabChoice.tab : abaInicial;
  const phaseHasAction = fase && !["AGUARDANDO_AVALIACAO", "REAVALIAR"].includes(fase.codigo);
  useEffect(() => {
    if (!processando || recurso.loading) return undefined;
    const timer = window.setTimeout(recurso.reload, 2000);
    return () => window.clearTimeout(timer);
  }, [processando, recurso.loading, recurso.reload]);

  const selectTab = (tab) => {
    setTabChoice({ phase: fase.codigo, tab });
    setReveal((old) => ({ group: tab, version: (old?.version || 0) + 1 }));
  };
  const goToWork = (tab = preferredTab) => {
    selectTab(tab);
    setMobileView("work");
    requestAnimationFrame(() => {
      workArea.current?.scrollIntoView({ block: "start", behavior: "instant" });
      workTabs.current[tab]?.focus({ preventScroll: true });
    });
  };
  const avaliar = () => acao.run(async () => {
    await request(`/cases/${caseId}/analyses`, { method: "POST" });
    recurso.reload();
  });
  const copyNumber = async () => {
    try {
      await navigator.clipboard.writeText(detalhe.case.case_number);
      setCopyStatus("Número copiado");
    } catch {
      setCopyStatus("Selecione o número para copiar.");
    }
  };
  const readyCount = detalhe?.documents.filter((d) => ["COMPLETED", "COMPLETED_WITH_WARNINGS"].includes(d.status)).length || 0;
  const pendingCount = detalhe?.documents.filter((d) => ["UPLOADED", "EXTRACTING"].includes(d.status)).length || 0;

  // O advogado não aperta botão para ver a recomendação: sem avaliação (ou com documentos novos antes da
  // decisão), a tela pede sozinha, uma vez por mudança de documentos.
  const tentativa = useRef(null);
  useEffect(() => {
    if (!detalhe || processando || acao.pending) return;
    const chave = `${detalhe.fase.codigo}-${detalhe.analyses.length}-${detalhe.documents.length}`;
    if (["AGUARDANDO_AVALIACAO", "REAVALIAR"].includes(detalhe.fase.codigo) && detalhe.documents.length > 0 && tentativa.current !== chave) {
      tentativa.current = chave;
      avaliar();
    }
  }, [detalhe, processando, acao.pending]);
  return <section className="caso-advogado case-workspace">
    <nav className="case-breadcrumb" aria-label="Localização"><Link className="voltar" to="/advogado"><Icon name="chevronLeft" />Minha fila</Link><span>/</span><span>Detalhe do processo</span></nav>
    {recurso.error && <div className="warning" role="alert"><p>{recurso.error}</p><button type="button" onClick={recurso.reload}>Tentar novamente</button></div>}
    {acao.error && <div className="warning" role="alert"><p>{acao.error}</p></div>}
    {!detalhe && recurso.loading && <p role="status">Carregando processo…</p>}
    {detalhe && <>
      <header className="case-overview-header">
        <div className="case-identity">
          <span className={`pill ${TOM_DA_FASE[fase.codigo] || ""} dot`}>{fase.rotulo}</span>
          <div className="case-number"><h1>{detalhe.case.case_number}</h1><button type="button" className="case-copy" aria-label="Copiar número do processo" title="Copiar número do processo" onClick={copyNumber}><Icon name="copy" /></button></div>
          <div className="case-facts"><span><b>{detalhe.case.uf}</b></span><span>Valor da causa <b>{moeda(detalhe.case.value_of_claim)}</b></span>
            <span>{detalhe.documents.length} {detalhe.documents.length === 1 ? "documento" : "documentos"}{pendingCount > 0 ? ` · ${pendingCount} em processamento` : ""}</span></div>
          {detalhe.case.sub_subject && <p className="case-subject">{detalhe.case.sub_subject}</p>}
          {copyStatus && <span role="status" className="case-copy-status">{copyStatus}</span>}
        </div>
        <div className="case-next-action">
          <span>PRÓXIMO PASSO</span><strong>{fase.proxima_acao}</strong>
          <button type="button" onClick={() => goToWork()}>{NEXT_LABEL[fase.codigo] || "Ver próxima ação"}<Icon name="arrow" /></button>
        </div>
      </header>
      {precisaAvaliar && <div className="case-update"><Icon name="spark" /><p>Novos documentos disponíveis. Confira o que mudou e atualize a avaliação.</p>
        <button type="button" className="subtle" onClick={() => goToWork("evaluation")}>Ver avaliação</button></div>}
      <PaineisDoCaso reveal={reveal}>
        <div className="case-mobile-views" role="group" aria-label="Área do processo">
          <button type="button" aria-pressed={mobileView === "documents"} onClick={() => setMobileView("documents")}><Icon name="files" />Documentos</button>
          <button type="button" aria-pressed={mobileView === "work"} onClick={() => setMobileView("work")}><Icon name="scale" />Análise e decisão</button>
        </div>
        <div className={`caso-grade case-work-grid mobile-${mobileView}`}>
          <div className="caso-documentos-coluna">
            <VisualizadorDocumentos documentos={detalhe.documents} leituras={detalhe.document_readings}>
              <ChatDocumentos caseId={caseId} caseNumber={detalhe.case.case_number} documentos={detalhe.documents} />
            </VisualizadorDocumentos>
          </div>
          <section className="case-work-area" ref={workArea} aria-label="Análise e decisão">
            <div className="case-work-tabs" role="tablist" aria-label="Etapas de trabalho">
              {WORK_TABS.map(([tab, label], index) => <button key={tab} type="button" role="tab" id={`case-tab-${tab}`}
                ref={(element) => { workTabs.current[tab] = element; }} aria-controls={`case-view-${tab}`} aria-selected={activeTab === tab}
                tabIndex={activeTab === tab ? 0 : -1} onClick={() => selectTab(tab)} onKeyDown={(event) => {
                  let next;
                  if (event.key === "ArrowRight") next = (index + 1) % WORK_TABS.length;
                  if (event.key === "ArrowLeft") next = (index + WORK_TABS.length - 1) % WORK_TABS.length;
                  if (event.key === "Home") next = 0;
                  if (event.key === "End") next = WORK_TABS.length - 1;
                  if (next !== undefined) { event.preventDefault(); const key = WORK_TABS[next][0]; selectTab(key); workTabs.current[key]?.focus(); }
                }}>{label}{tab === preferredTab && <span className="case-tab-dot" aria-label="Etapa atual" />}</button>)}
            </div>
            <div role="tabpanel" id="case-view-evaluation" aria-labelledby="case-tab-evaluation" hidden={activeTab !== "evaluation"} className="case-work-view">
              <Recomendacao recomendacao={recomendacao} precisaAvaliar={precisaAvaliar} onAvaliar={avaliar} ocupado={acao.pending} />
              {fase.codigo === "PRONTO_PARA_DECIDIR" && recomendacao && <button type="button" className="case-continue" onClick={() => goToWork("action")}>Continuar para a decisão<Icon name="arrow" /></button>}
            </div>
            <div role="tabpanel" id="case-view-action" aria-labelledby="case-tab-action" hidden={activeTab !== "action"} className="case-work-view">
              {phaseHasAction ? <PainelDaFase caseId={caseId} detalhe={detalhe} fase={fase} recomendacao={recomendacao} onChange={recurso.reload} />
                : <PainelRecolhivel group="action" titulo="Próximo passo" resumo="Avaliar antes de decidir"><article className="panel case-empty-panel"><Icon name="scale" /><h3>{precisaAvaliar ? "Atualize a avaliação" : "Primeiro, avalie o processo"}</h3>
                  <p>{readyCount ? "Confira os documentos e a recomendação para registrar sua decisão." : "A avaliação usa os documentos disponíveis. Confira o envio e o processamento antes de prosseguir."}</p>
                  <button type="button" className="subtle" onClick={() => goToWork("evaluation")}>Ir para avaliação<Icon name="arrow" /></button></article></PainelRecolhivel>}
            </div>
            <div role="tabpanel" id="case-view-history" aria-labelledby="case-tab-history" hidden={activeTab !== "history"} className="case-work-view">
              <LinhaDoTempo detalhe={detalhe} initiallyCollapsed={false} />
            </div>
          </section>
        </div>
      </PaineisDoCaso>
    </>}
  </section>;
}

export default function CasoAdvogadoRota() {
  const { caseId } = useParams();
  return <CasoAdvogado key={caseId} caseId={caseId} />;
}
