import { brlCompact } from "./format";

export function WeeklyChart({ series }) {
  if (!series?.length) return <p className="muted">Ainda não há decisões com resultado para mostrar.</p>;
  const width = 720, height = 220, pad = { top: 16, right: 12, bottom: 34, left: 64 };
  const max = Math.max(1, ...series.flatMap((week) => [week.economia_esperada, week.economia_realizada]));
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  const slot = plotW / series.length, bar = Math.min(18, slot / 2.6);
  const y = (value) => pad.top + plotH - (Math.max(0, value) / max) * plotH;
  const ticks = [0, 0.5, 1].map((fraction) => max * fraction);
  return <figure className="weekly-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Economia esperada e realizada por semana">
      {ticks.map((tick) => <g key={tick}>
        <line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} className="grid" />
        <text x={pad.left - 8} y={y(tick) + 4} textAnchor="end" className="axis">{brlCompact(tick)}</text>
      </g>)}
      {series.map((week, index) => {
        const x = pad.left + index * slot + slot / 2;
        return <g key={week.semana}>
          <rect x={x - bar - 1} y={y(week.economia_esperada)} width={bar} height={pad.top + plotH - y(week.economia_esperada)} className="bar-expected" rx="3">
            <title>{`${week.semana}: esperada ${brlCompact(week.economia_esperada)}`}</title>
          </rect>
          <rect x={x + 1} y={y(week.economia_realizada)} width={bar} height={pad.top + plotH - y(week.economia_realizada)} className="bar-realized" rx="3">
            <title>{`${week.semana}: realizada ${brlCompact(week.economia_realizada)}`}</title>
          </rect>
          <text x={x} y={height - 12} textAnchor="middle" className="axis">{week.semana.split("-")[1]}</text>
        </g>;
      })}
    </svg>
    <figcaption><span className="legend legend-expected" />Esperada pela política<span className="legend legend-realized" />Realizada</figcaption>
  </figure>;
}
