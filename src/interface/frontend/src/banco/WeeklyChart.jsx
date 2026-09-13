import { brlCompact } from "./format";

/** Economia somada por semana de encerramento (pode ser negativa). */
export function WeeklyChart({ series }) {
  if (!series?.length) return <p className="muted">Ainda não há processos encerrados para mostrar.</p>;
  const width = 720, height = 220, pad = { top: 16, right: 12, bottom: 34, left: 64 };
  const valores = series.map((week) => week.economia);
  const max = Math.max(0, ...valores), min = Math.min(0, ...valores);
  const amplitude = Math.max(1, max - min);
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  const slot = plotW / series.length, bar = Math.min(26, slot / 1.8);
  const y = (value) => pad.top + ((max - value) / amplitude) * plotH;
  const ticks = [...new Set([max, (max + min) / 2, min, 0])];
  return <figure className="weekly-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Economia por semana">
      {ticks.map((tick) => <g key={tick}>
        <line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} className={tick === 0 ? "grid zero" : "grid"} />
        <text x={pad.left - 8} y={y(tick) + 4} textAnchor="end" className="axis">{brlCompact(tick)}</text>
      </g>)}
      {series.map((week, index) => {
        const x = pad.left + index * slot + slot / 2;
        const topo = y(Math.max(0, week.economia)), base = y(Math.min(0, week.economia));
        return <g key={week.semana}>
          <rect x={x - bar / 2} y={topo} width={bar} height={Math.max(1, base - topo)} className={week.economia >= 0 ? "bar-realized" : "bar-negative"} rx="3">
            <title>{`${week.semana}: ${brlCompact(week.economia)} em ${week.encerrados} processo(s) encerrado(s)`}</title>
          </rect>
          <text x={x} y={height - 12} textAnchor="middle" className="axis">{week.semana.split("-")[1]}</text>
        </g>;
      })}
    </svg>
    <figcaption><span className="legend legend-realized" />Economia dos processos encerrados na semana</figcaption>
  </figure>;
}
