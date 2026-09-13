const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const moedaCentavos = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export const brl = (value, cents = false) => value == null ? "—" : (cents ? moedaCentavos : moeda).format(value);

export function brlCompact(value) {
  if (value == null) return "—";
  const absolute = Math.abs(value);
  if (absolute >= 1e6) return `R$ ${(value / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi`;
  if (absolute >= 1e4) return `R$ ${(value / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} mil`;
  return brl(value);
}

export const pct = (value, digits = 1) => value == null ? "—"
  : `${(value * 100).toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;

export const num = (value, digits = 0) => value == null ? "—" : Number(value).toLocaleString("pt-BR", { maximumFractionDigits: digits });

export const index = (value) => value == null ? "—" : Number(value).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const minutes = (value) => value == null ? "—" : `${num(value, 1)} min`;

export const date = (value) => value ? new Date(value).toLocaleDateString("pt-BR") : "—";

// "C1 E0 CC1 Golpe" -> "com contrato · sem extrato · com comprovante · golpe"
export function segmentLabel(segment) {
  const match = /^C(\d) E(\d) CC(\d) (\w+)$/.exec(segment || "");
  if (!match) return segment;
  const mark = (flag, name) => `${flag === "1" ? "com" : "sem"} ${name}`;
  return [mark(match[1], "contrato"), mark(match[2], "extrato"), mark(match[3], "comprovante"),
    match[4] === "Golpe" ? "golpe" : "genérico"].join(" · ");
}

export const indexTone = (index) => index == null ? "neutral" : index >= 0.9 ? "good" : index >= 0.6 ? "warn" : "bad";
