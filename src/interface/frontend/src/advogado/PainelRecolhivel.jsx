import { createContext, useContext, useEffect, useId, useState } from "react";
import { Icon } from "../Brand";

const PanelContext = createContext(null);

export function PaineisDoCaso({ children, reveal }) {
  const [command, setCommand] = useState({ version: 0, collapsed: null });
  useEffect(() => {
    if (reveal) setCommand({ version: reveal.version, collapsed: false, group: reveal.group });
  }, [reveal]);
  return <PanelContext.Provider value={command}>
    <div className="case-panel-controls" role="group" aria-label="Visualização dos cards">
      <span>Área de trabalho</span>
      <button type="button" className="subtle" onClick={() => setCommand((old) => ({ version: old.version + 1, collapsed: true }))}>Recolher todos</button>
      <button type="button" className="subtle" onClick={() => setCommand((old) => ({ version: old.version + 1, collapsed: false }))}>Expandir todos</button>
    </div>
    {children}
  </PanelContext.Provider>;
}

/** Oculta sem desmontar: preserva formulários, seleção do leitor e requisições em curso. */
export function PainelRecolhivel({ titulo, resumo, children, afterHeader, initiallyCollapsed = false, group }) {
  const command = useContext(PanelContext);
  const [collapsed, setCollapsed] = useState(initiallyCollapsed);
  const id = useId();
  useEffect(() => {
    if (command?.collapsed != null && (!command.group || command.group === group)) setCollapsed(command.collapsed);
  }, [command, group]);
  return <section className={`case-panel ${collapsed ? "is-collapsed" : ""}`} aria-label={titulo}>
    <button type="button" className="case-panel-toggle" aria-expanded={!collapsed} aria-controls={id}
      aria-label={`${collapsed ? "Expandir" : "Recolher"} ${titulo}`} onClick={() => setCollapsed((value) => !value)}>
      <span><strong>{titulo}</strong>{collapsed && resumo && <small>{resumo}</small>}</span>
      <Icon name="chevronDown" />
    </button>
    {afterHeader}
    <div id={id} className="case-panel-body" hidden={collapsed}>{children}</div>
  </section>;
}
