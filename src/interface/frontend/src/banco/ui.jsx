import { useState } from "react";
import { sendJson } from "../api";
import { useAction } from "../hooks";

/** Ação inline de redefinir senha, usada tanto pelo admin quanto pelo gestor do banco. */
export function ResetPasswordAction({ endpoint }) {
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  const action = useAction();
  const submit = (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    action.run(async () => {
      await sendJson(endpoint, { new_password: form.get("new_password") }, "PATCH");
      setDone(true);
    });
  };
  if (done) return <span className="muted">Senha redefinida.</span>;
  if (!open) return <button type="button" className="subtle" onClick={() => setOpen(true)}>Redefinir senha</button>;
  return <form className="inline-reset" onSubmit={submit}>
    <input name="new_password" type="password" placeholder="Nova senha (15+ caracteres)" minLength="15" maxLength="128" required autoComplete="new-password" disabled={action.pending} />
    <button className="subtle" disabled={action.pending}>{action.pending ? "Salvando…" : "Confirmar"}</button>
    <button type="button" className="subtle" disabled={action.pending} onClick={() => setOpen(false)}>Cancelar</button>
    {action.error && <span className="warning">{action.error}</span>}
  </form>;
}

export function Kpi({ label, value, hint, tone = "neutral" }) {
  return <div className={`kpi tone-${tone}`}><span>{label}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</div>;
}

export function Notice({ message, onRetry }) {
  if (!message) return null;
  return <div className="bank-notice" role="alert"><span>{message}</span>{onRetry && <button type="button" className="ghost" onClick={onRetry}>Tentar novamente</button>}</div>;
}

export function Bar({ label, value, max, caption, display, tone = "primary" }) {
  const width = max > 0 ? Math.max(2, Math.min(100, (Math.max(0, value) / max) * 100)) : 0;
  return <div className="hbar">
    <div className="hbar-head"><span>{label}</span><strong>{display ?? value}</strong></div>
    <div className="hbar-track"><div className={`hbar-fill fill-${tone}`} style={{ width: `${width}%` }} /></div>
    {caption && <small>{caption}</small>}
  </div>;
}

export function Pill({ tone = "neutral", children }) {
  return <span className={`pill tone-${tone}`}>{children}</span>;
}

export function SectionHeader({ eyebrow, title, children }) {
  return <header className="section-header">{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2>{children && <p>{children}</p>}</header>;
}
