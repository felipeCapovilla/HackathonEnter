import { useState } from 'react'
import { ROTULO_SUBSIDIO, SEM_PESO, brl } from '../data/mock.js'

const COR = { DEFENDER: 'var(--defender)', ACORDAR: 'var(--acordar)', RECUPERAR: 'var(--recuperar)' }
const TITULO = { DEFENDER: 'Defender', ACORDAR: 'Acordar', RECUPERAR: 'Recuperar o documento' }
const RESUMO = {
  DEFENDER: 'A prova mínima está nos autos. O custo esperado de defender é menor que qualquer oferta viável.',
  ACORDAR: 'A defesa não se sustenta e o documento que falta não é recuperável. Compor é o caminho mais barato.',
  RECUPERAR: 'A defesa está fechada hoje — mas há evidência interna de que o documento existe. Recuperá-lo reabre o caso.',
}

/* Risco como escala contínua. Um caso de 54% não é "amarelo", é 54%:
   a graduação é a informação, e o salto entre segmentos é o que importa. */
function Risco({ p, segmento }) {
  return (
    <section>
      <span className="label">Risco de derrota</span>
      <div className="risk-row">
        <span className="risk-value" style={{ color: p > .6 ? 'var(--danger)' : p > .25 ? 'var(--amber)' : 'var(--ok)' }}>
          {(p * 100).toFixed(1)}%
        </span>
        <span className="risk-ctx">
          segmento <strong style={{ color: 'var(--fg-muted)' }} className="mono">{segmento}</strong>
          {' '}· medido na base de 60.000 sentenças
        </span>
      </div>
      <div className="risk-track"><div className="risk-fill" style={{ width: `${p * 100}%` }} /></div>
      <div className="risk-scale"><span>0%</span><span>50%</span><span>100%</span></div>
    </section>
  )
}

function Caminhos({ r }) {
  const opcoes = [
    { id: 'DEFENDER', custo: r.custo_esperado_defesa, rotulo: 'custo esperado',
      nota: r.gate_defesa_disponivel ? 'Prova mínima presente.' : 'Gate fechado: ônus do art. 373, II não satisfeito.',
      off: !r.gate_defesa_disponivel },
    { id: 'ACORDAR', custo: r.acordo?.alvo, rotulo: 'oferta alvo',
      nota: r.acordo ? 'Faixa ancorada em 280 acordos reais da base.' : 'Não recomendado neste caso.' },
    { id: 'RECUPERAR', custo: r.recuperacao?.ganho_estimado, rotulo: 'ganho esperado',
      nota: r.recuperacao?.fundamento ?? 'Nenhum documento decisivo ausente.' },
  ]
  return (
    <section>
      <span className="label">Os três caminhos</span>
      <div className="paths">
        {opcoes.map((o) => (
          <div key={o.id} className="path" data-rec={r.acao === o.id} style={{ color: COR[o.id] }}>
            {r.acao === o.id && <span className="path-tag">recomendado</span>}
            <div className="path-name" style={{ color: o.off ? 'var(--fg-dim)' : COR[o.id] }}>{TITULO[o.id]}</div>
            <div className="path-cost" style={{ color: o.custo == null ? 'var(--fg-dim)' : undefined }}>
              {o.custo == null ? '—' : brl(o.custo)}
            </div>
            <div className="label" style={{ marginTop: 2 }}>{o.custo == null ? '' : o.rotulo}</div>
            <div className="path-note">{o.nota}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

function Subsidios({ subs, rec }) {
  const alvo = rec?.documento
  return (
    <section>
      <span className="label">Subsídios do banco</span>
      <div className="subs">
        {Object.entries(subs).map(([k, presente]) => {
          const recuperavel = !presente && k === alvo
          return (
            <div key={k} className="sub" data-state={recuperavel ? 'recuperavel' : presente ? 'presente' : 'ausente'}>
              <span className="sub-mark" style={{ color: presente ? 'var(--ok)' : recuperavel ? 'var(--recuperar)' : 'var(--fg-dim)' }}>
                {presente ? '✓' : recuperavel ? '↻' : '✗'}
              </span>
              {ROTULO_SUBSIDIO[k]}
              {recuperavel && <span className="sub-tag">recuperável</span>}
              {!recuperavel && SEM_PESO.has(k) && <span className="sub-null">não pesa</span>}
            </div>
          )
        })}
      </div>
      <p className="path-note" style={{ marginTop: 'var(--sp-3)' }}>
        Dossiê e laudo não alteram o resultado (Δ +0,03 e +0,19 pontos percentuais em 60.000 casos).
        O dossiê importa aqui por outro motivo: ele prova que o contrato existe.
      </p>
    </section>
  )
}

/* Faixa, não número: é assim que um advogado negocia de verdade. */
function Faixa({ a, valorCausa }) {
  const pos = (v) => (v / (valorCausa * 0.5)) * 100
  return (
    <section>
      <span className="label">Faixa de negociação</span>
      <div className="band">
        <div className="band-track">
          <div className="band-span" style={{ left: `${pos(a.abertura)}%`, width: `${pos(a.maximo_aceitavel) - pos(a.abertura)}%` }} />
          {[['abertura', a.abertura], ['alvo', a.alvo], ['teto', a.teto_absoluto]].map(([nome, v]) => (
            <div key={nome} className="band-pin" style={{ left: `${pos(v)}%`, opacity: nome === 'alvo' ? 1 : .5 }}>
              <span style={{ color: nome === 'alvo' ? 'var(--amber)' : 'var(--fg-dim)' }}>{brl(v)}</span>
            </div>
          ))}
        </div>
        <div className="band-legend">
          <span>Abra em {brl(a.abertura)}</span>
          <span style={{ color: 'var(--amber)' }}>Alvo {brl(a.alvo)}</span>
          <span>Nunca acima de {brl(a.teto_absoluto)}</span>
        </div>
      </div>
    </section>
  )
}

/* O registro do desfecho fica NA MESMA TELA da recomendação.
   Se o advogado precisar reportar em outro lugar, ninguém reporta —
   e sem esse dado não existe monitoramento de aderência nem calibração. */
function Decisao({ recomendada }) {
  const [escolha, setEscolha] = useState(null)
  const [nota, setNota] = useState(0)
  const [motivo, setMotivo] = useState('')
  const [salvo, setSalvo] = useState(false)
  const divergiu = escolha && escolha !== recomendada

  if (salvo) return (
    <section><div className="decide">
      <span className="label">Decisão registrada</span>
      <div className="saved">
        {escolha} registrado{divergiu ? ` · divergente da recomendação (${recomendada})` : ' · aderente à recomendação'}.
        Alimenta aderência e recalibra a taxa de aceitação do segmento.
      </div>
    </div></section>
  )

  return (
    <section>
      <div className="decide">
        <span className="label">Sua decisão</span>
        <div className="decide-row">
          {['DEFENDER', 'ACORDAR', 'RECUPERAR'].map((a) => (
            <button key={a} className="btn" data-primary={escolha === a} onClick={() => setEscolha(a)}>
              {TITULO[a]}
            </button>
          ))}
        </div>

        {divergiu && (
          <div className="diverge">
            <span className="label" style={{ color: 'var(--amber)' }}>
              Você divergiu da recomendação — nos ajude a melhorar a política
            </span>
            <div className="stars">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} className="star" data-on={n <= nota} onClick={() => setNota(n)}>★</button>
              ))}
            </div>
            <textarea placeholder="O que a política não enxergou neste caso?"
                      value={motivo} onChange={(e) => setMotivo(e.target.value)} />
          </div>
        )}

        {escolha && (
          <button className="btn" data-primary="true" style={{ marginTop: 'var(--sp-4)', width: '100%' }}
                  disabled={divergiu && (!nota || !motivo.trim())}
                  onClick={() => setSalvo(true)}>
            Registrar decisão
          </button>
        )}
      </div>
    </section>
  )
}

export default function CaseView({ caso }) {
  const r = caso.recomendacao
  return (
    <>
      <div className="case-head">
        <span className="label label-amber">
          {caso.sub_assunto === 'Golpe' ? 'Não reconhece operação · golpe' : 'Não reconhece operação'}
        </span>
        <h1 className="case-title">{caso.numero_processo}</h1>
        <div className="case-sub">{caso.autor} · {caso.uf} · valor da causa {brl(caso.valor_causa)}</div>
      </div>

      <section>
        <div className="hero" data-acao={r.acao}>
          <span className="label" style={{ color: COR[r.acao] }}>Recomendação</span>
          <div className="hero-acao" style={{ color: COR[r.acao] }}>{TITULO[r.acao]}</div>
          <p className="hero-note">{RESUMO[r.acao]}</p>
          {r.recuperacao && (
            <div className="hero-figure">
              <div>
                <span className="label">Documento</span>
                <div className="figure-v" style={{ textTransform: 'capitalize' }}>{r.recuperacao.documento}</div>
              </div>
              <div>
                <span className="label">Risco depois</span>
                <div className="figure-v">{(r.p_perda * 100).toFixed(0)}% → {(r.recuperacao.p_perda_se_recuperado * 100).toFixed(0)}%</div>
              </div>
              <div>
                <span className="label">Ganho esperado</span>
                <div className="figure-v" style={{ color: 'var(--recuperar)' }}>{brl(r.recuperacao.ganho_estimado)}</div>
              </div>
            </div>
          )}
        </div>
      </section>

      <Risco p={r.p_perda} segmento={r.segmento} />
      <Caminhos r={r} />
      {r.acordo && <Faixa a={r.acordo} valorCausa={caso.valor_causa} />}
      <Subsidios subs={caso.subsidios} rec={r.recuperacao} />

      <section>
        <span className="label">Por que esta recomendação</span>
        <ul className="why">{r.justificativa.map((j, i) => <li key={i}>{j}</li>)}</ul>
        <div className="premisses">
          <span className="label" style={{ alignSelf: 'center' }}>Premissas</span>
          {r.premissas_usadas.map((p) => <span key={p} className="pill">{p}</span>)}
        </div>
      </section>

      <Decisao recomendada={r.acao} />
    </>
  )
}
