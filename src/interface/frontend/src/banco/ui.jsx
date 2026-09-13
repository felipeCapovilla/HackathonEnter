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

/** Ícone "i" com a explicação da métrica ao passar o mouse ou focar pelo teclado. */
export function InfoTip({ texto }) {
  return <span className="info-tip" tabIndex={0} aria-label={texto}>
    <span aria-hidden="true">i</span>
    <span className="info-tip-texto" role="tooltip">{texto}</span>
  </span>;
}
