export const moeda = (valor) => valor == null ? "—" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(valor);
export const data = (valor) => valor ? new Date(valor).toLocaleDateString("pt-BR") : "—";

export const TOM_DA_FASE = {
  AGUARDANDO_AVALIACAO: "amber", REAVALIAR: "amber", PRONTO_PARA_DECIDIR: "amber", CONTRAPROPOSTA: "amber",
  AGUARDANDO_DOCUMENTO: "info", EM_NEGOCIACAO: "info", EM_DEFESA: "info", ENCERRADO: "",
};

export const ACOES = {
  ACORDO: { titulo: "Propor acordo", ajuda: "Oferecer um valor ao autor para encerrar o processo" },
  DEFESA: { titulo: "Seguir com a defesa", ajuda: "Contestar e esperar a sentença" },
  RECUPERAR: { titulo: "Pedir documento à empresa", ajuda: "Esperar o documento que falta antes de decidir" },
};

export const DOCUMENTOS = {
  AUTOS: "Petição e autos", CONTRATO: "Contrato", EXTRATO: "Extrato", COMPROVANTE_CREDITO: "Comprovante de crédito",
  DOSSIE: "Dossiê", DEMONSTRATIVO_DIVIDA: "Evolução da dívida", LAUDO_REFERENCIADO: "Laudo", OUTRO: "Outro",
};
export const ORDEM_DOCUMENTOS = Object.keys(DOCUMENTOS);
export const DOCUMENTO_DO_PLANO = { contrato: "CONTRATO", extrato: "EXTRATO", comprovante_credito: "COMPROVANTE_CREDITO" };

export const MOTIVOS_DIVERGENCIA = [
  ["FATO_NOVO", "Há fato ou documento que a recomendação não considerou"],
  ["ENTENDIMENTO_LOCAL", "O juízo ou a comarca costuma decidir diferente"],
  ["PROVA_MAIS_FRACA", "A prova da empresa é mais fraca do que parece"],
  ["PROVA_MAIS_FORTE", "A prova da empresa é mais forte do que parece"],
  ["SINAL_DO_AUTOR", "O autor sinalizou outro valor"],
  ["OUTRO", "Outro motivo"],
];

/** Nos extremos, em cada 100: "0 em cada 10" esconderia um risco pequeno, mas real. */
export function frequencia(p) {
  const valor = Math.min(1, Math.max(0, p));
  return valor < 0.1 || valor > 0.9 ? `${Math.round(valor * 100)} em cada 100` : `${Math.round(valor * 10)} em cada 10`;
}
export const nivelDeRisco = (p) => p < 0.25 ? "baixa" : p < 0.5 ? "média" : p < 0.75 ? "alta" : "muito alta";

export function descreverCaso(segmento) {
  const partes = /^C(\d) E(\d) CC(\d) (\w+)$/.exec(segmento || "");
  if (!partes) return null;
  const marca = (tem, nome) => `${tem === "1" ? "com" : "sem"} ${nome}`;
  return [marca(partes[1], "contrato"), marca(partes[2], "extrato"), marca(partes[3], "comprovante"),
    partes[4] === "Golpe" ? "alegação de golpe" : "sem alegação de golpe"].join(", ");
}
