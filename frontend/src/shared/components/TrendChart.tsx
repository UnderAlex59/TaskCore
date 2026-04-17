type TrendSeries = {
  color: string;
  label: string;
  points: Array<{ label: string; value: number }>;
};

interface Props {
  emptyLabel: string;
  height?: number;
  series: TrendSeries[];
}

function buildPath(
  points: Array<{ label: string; value: number }>,
  maxValue: number,
  width: number,
  height: number,
) {
  if (points.length === 0) {
    return "";
  }

  const stepX = points.length === 1 ? width / 2 : width / (points.length - 1);
  return points
    .map((point, index) => {
      const x = index * stepX;
      const y = height - (point.value / maxValue) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function TrendChart({ emptyLabel, height = 180, series }: Props) {
  const labels = series[0]?.points.map((point) => point.label) ?? [];
  const maxValue = Math.max(
    1,
    ...series.flatMap((item) => item.points.map((point) => point.value)),
  );
  const width = 480;

  if (series.length === 0 || labels.length === 0) {
    return (
      <div className="flex min-h-40 items-center justify-center rounded-[24px] border border-dashed border-black/10 bg-white/60 p-6 text-sm text-ink/55">
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <svg
        aria-label="График динамики"
        className="h-auto w-full overflow-visible rounded-[24px] border border-black/10 bg-white/70 p-3"
        viewBox={`0 0 ${width} ${height + 12}`}
      >
        {[0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = height - height * ratio;
          return (
            <line
              key={ratio}
              stroke="rgba(16,17,20,0.08)"
              strokeDasharray="4 6"
              strokeWidth="1"
              x1="0"
              x2={width}
              y1={y}
              y2={y}
            />
          );
        })}
        {series.map((item) => (
          <path
            key={item.label}
            d={buildPath(item.points, maxValue, width, height)}
            fill="none"
            stroke={item.color}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="3"
          />
        ))}
      </svg>

      <div className="flex flex-wrap gap-3">
        {series.map((item) => (
          <div key={item.label} className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-ink/60">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
            {item.label}
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 text-xs text-ink/50">
        {labels.map((label) => (
          <span key={label} className="rounded-full bg-black/5 px-2 py-1">
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
