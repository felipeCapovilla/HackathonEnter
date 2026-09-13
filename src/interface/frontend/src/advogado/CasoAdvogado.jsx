import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../api";
import { useAction, useResource } from "../hooks";
import { Icon } from "../Brand";
import { useActiveTime } from "../useActiveTime";
import { LinhaDoTempo, PainelDaFase } from "./PainelDaFase";
import { Recomendacao } from "./Recomendacao";
import { VisualizadorDocumentos } from "./VisualizadorDocumentos";
import { TOM_DA_FASE, moeda } from "./textos";
import "./advogado.css";

export function CasoAdvogado({ caseId }) {
  const recurso = useResource(`/cases/${caseId}`);
  const acao = useAction();
  useActiveTime(caseId, true);
  const detalhe = recurso.data;
  const fase = detalhe?.fase;
  const recomendacao = detalhe?.analyses?.[0];
  const processando = detalhe?.documents.some((documento) => ["UPLOADED", "EXTRACTING"].includes(documento.status));
  useEffect(() => {
    if (!processando || recurso.loading) return undefined;
    const timer = window.setTimeout(recurso.reload, 2000);
    return () => window.clearTimeout(timer);
  }, [processando, recurso.loading, recurso.reload]);
  const avaliar = () => acao.run(async () => {
    await request(`/cases/${caseId}/analyses`, { method: "POST" });
    recurso.reload();
  });
  const precisaAvaliar = fase && (fase.codigo === "REAVALIAR" || (fase.documentos_novos && fase.codigo !== "ENCERRADO"));
  return <section className="caso-advogado">
    <Link className="voltar" to="/advogado">← Minha fila</Link>
    {recurso.error && <div className="warning" role="alert"><p>{recurso.error}</p><button type="button" onClick={recurso.reload}>Tentar novamente</button></div>}
    {acao.error && <div className="warning" role="alert"><p>{acao.error}</p></div>}
    {!detalhe && recurso.loading && <p role="status">Carregando processo…</p>}
    {detalhe && <>
      <header className="caso-topo">
        <div>
          <p className="eyebrow">Processo</p>
          <h2>{detalhe.case.case_number}</h2>
          <p className="muted">{detalhe.case.uf} · {moeda(detalhe.case.value_of_claim)}{detalhe.case.sub_subject ? ` · ${detalhe.case.sub_subject}` : ""}</p>
        </div>
        <div className="caso-fase">
          <span className={`pill ${TOM_DA_FASE[fase.codigo]} dot`}>{fase.rotulo}</span>
          <strong>{fase.proxima_acao}</strong>
        </div>
      </header>
      {fase.documentos_novos && <p className="aviso-mudanca"><Icon name="spark" />Chegaram documentos depois da última avaliação. Reavalie para ver se a recomendação muda.</p>}
      <div className="caso-grade">
        <VisualizadorDocumentos documentos={detalhe.documents} leituras={detalhe.document_readings} />
        <div className="caso-coluna">
          <Recomendacao recomendacao={recomendacao} precisaAvaliar={precisaAvaliar} onAvaliar={avaliar} ocupado={acao.pending} />
          <PainelDaFase caseId={caseId} detalhe={detalhe} fase={fase} recomendacao={recomendacao} onChange={recurso.reload} />
          <LinhaDoTempo detalhe={detalhe} />
        </div>
      </div>
    </>}
  </section>;
}

export default function CasoAdvogadoRota() {
  const { caseId } = useParams();
  return <CasoAdvogado key={caseId} caseId={caseId} />;
}
