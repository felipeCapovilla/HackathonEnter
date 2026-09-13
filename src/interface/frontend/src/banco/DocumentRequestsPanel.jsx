import { sendJson } from "../api";
import { useAction } from "../hooks";
import { Notice, Pill } from "./ui";
import { date } from "./format";
import "./banco.css";

const MOTIVOS = [
  ["NAO_LOCALIZADO", "Não localizado"],
  ["CONTRATO_FISICO_NAO_DIGITALIZADO", "Contrato físico não digitalizado"],
  ["CORRESPONDENTE_NAO_ENVIOU", "Correspondente não enviou"],
  ["FORA_DO_PRAZO_DE_GUARDA", "Fora do prazo de guarda"],
  ["SISTEMA_SEM_EXPORTACAO", "Sistema sem exportação"],
  ["OPERACAO_INEXISTENTE", "Operação não existe (golpe)"],
  ["OUTRO", "Outro"],
];
const MOTIVO_NOME = Object.fromEntries(MOTIVOS);
const DOCUMENTOS = { CONTRATO: "Contrato", EXTRATO: "Extrato", COMPROVANTE_CREDITO: "Comprovante de crédito", DOSSIE: "Dossiê",
  DEMONSTRATIVO_DIVIDA: "Demonstrativo da dívida", LAUDO_REFERENCIADO: "Laudo referenciado", AUTOS: "Autos", OUTRO: "Outro" };
const STATUS = { REQUESTED: ["Aguardando o banco", "warn"], SUBMITTED: ["Entregue", "good"], DECLARED_UNAVAILABLE: ["Indisponível", "bad"], CANCELLED: ["Cancelado", "neutral"] };
const FONTE = { IA: " · classificado por IA", REGRA: " · classificado automaticamente" };

export function DocumentRequestsPanel({ requests, onChanged }) {
  const action = useAction();
  if (!requests?.length) return null;
  const respond = (event, requestId) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const status = event.nativeEvent.submitter?.value || "DECLARED_UNAVAILABLE";
    action.run(async () => {
      if (status === "DECLARED_UNAVAILABLE" && !form.get("motivo")) throw new Error("Escolha o motivo da indisponibilidade.");
      await sendJson(`/document-requests/${requestId}/response`, {
        status, reason: String(form.get("reason") || "").trim(),
        ...(status === "DECLARED_UNAVAILABLE" ? { unavailability_reason: form.get("motivo") } : {}),
      });
      onChanged();
    });
  };
  return <article className="panel request-panel"><h3>Pedidos de documento do advogado</h3>
    <p className="muted">Para entregar, envie o arquivo no painel de documentos. Se não houver como entregar, informe o motivo: ele vira recomendação para a área responsável.</p>
    <Notice message={action.error} />
    <ul className="request-list">{requests.map((item) => {
      const [label, tone] = STATUS[item.status] || [item.status, "neutral"];
      return <li key={item.id}>
        <div className="request-head"><strong>{DOCUMENTOS[item.document_type] || item.document_type}</strong><Pill tone={tone}>{label}</Pill><span className="muted">{date(item.created_at)}</span></div>
        <p>{item.reason}</p>
        {item.unavailability_reason && <p className="footnote">Motivo: {MOTIVO_NOME[item.unavailability_reason] || item.unavailability_reason}{FONTE[item.unavailability_reason_source] || ""}</p>}
        {item.status === "REQUESTED" && <form onSubmit={(event) => respond(event, item.id)}>
          <fieldset className="form-fields" disabled={action.pending}>
            <label>Motivo da indisponibilidade<select name="motivo" defaultValue=""><option value="" disabled>Selecione</option>{MOTIVOS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
            <label>Detalhe<textarea name="reason" minLength="3" maxLength="1000" required /></label>
            <div className="contract-row">
              <button value="DECLARED_UNAVAILABLE">Declarar indisponível</button>
              <button className="ghost" value="CANCELLED" formNoValidate>Cancelar pedido</button>
            </div>
          </fieldset>
        </form>}
      </li>;
    })}</ul>
  </article>;
}
