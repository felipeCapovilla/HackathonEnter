import { useState } from 'react'
import { CASOS } from './data/mock.js'
import CaseView from './components/CaseView.jsx'

const ACAO_LABEL = { RECUPERAR: 'Recuperar', ACORDAR: 'Acordar', DEFENDER: 'Defender' }

export default function App() {
  const [sel, setSel] = useState(0)
  const caso = CASOS[sel]

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          <span className="label">Enter · Política de Acordos</span>
        </div>
        <nav className="nav">
          <button data-active="true">Meus casos</button>
          <button>Aderência</button>
          <button>Efetividade</button>
        </nav>
      </header>

      <aside className="queue">
        <div className="queue-head">
          <span className="label">Fila · {CASOS.length}</span>
          <span className="mock-badge">dados de exemplo</span>
        </div>
        {CASOS.map((c, i) => (
          <button key={c.numero_processo} className="queue-item"
                  data-active={i === sel} data-acao={c.recomendacao.acao}
                  onClick={() => setSel(i)}>
            <div className="queue-num">{c.numero_processo}</div>
            <div className="queue-meta">
              <span style={{ color: 'var(--fg-muted)' }}>{ACAO_LABEL[c.recomendacao.acao]}</span>
              <span className="mono" style={{ color: 'var(--fg-dim)' }}>
                {(c.recomendacao.p_perda * 100).toFixed(1)}%
              </span>
            </div>
          </button>
        ))}
      </aside>

      <main className="case"><CaseView key={caso.numero_processo} caso={caso} /></main>
    </div>
  )
}
