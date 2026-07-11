import {
  MARKET_INDICATORS,
  SPARKLINE_DATA,
  VOLUME_BARS,
} from "@/lib/mock-data";
import { Card } from "@/components/ui/Card";

function FearGreedGauge({ score }: { score: number }) {
  return (
    <div className="mt-1">
      <div className="relative h-1.5 overflow-hidden rounded-full">
        <div className="absolute inset-0 flex">
          <div className="h-full flex-1 bg-negative/35" />
          <div className="h-full flex-1 bg-warning/35" />
          <div className="h-full flex-1 bg-mint/40" />
        </div>
        <div
          className="absolute top-1/2 h-2 w-2 rounded-full border border-white/70 bg-bg-card-alt"
          style={{ left: `${score}%`, transform: "translate(-50%, -50%)" }}
        />
      </div>
    </div>
  );
}

function MiniBarChart({ data }: { data: number[] }) {
  const max = Math.max(...data);
  return (
    <div className="mt-1 flex h-6 items-end gap-0.5">
      {data.map((val, i) => (
        <div
          key={i}
          className="flex-1 rounded-t-sm bg-mint/35"
          style={{ height: `${Math.max(18, (val / max) * 100)}%` }}
        />
      ))}
    </div>
  );
}

function Sparkline({ data }: { data: number[] }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * 100;
      const y = 100 - ((v - min) / range) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg viewBox="0 0 100 20" className="mt-1 h-5 w-full" preserveAspectRatio="none">
      <polyline
        fill="none"
        stroke="#42d98b"
        strokeWidth="1.5"
        points={points}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function MarketCards() {
  return (
    <div className="chart-panel market-stack flex min-w-0">
      {MARKET_INDICATORS.map((indicator) => (
        <Card key={indicator.id} padding="sm" className="flex min-w-0 flex-1 flex-col justify-center">
          <p className="text-[11px] uppercase tracking-[0.05em] text-text-muted">
            {indicator.label}
          </p>

          {indicator.id === "regime" && (
            <>
              <p className="mt-1 text-[14px] font-medium leading-none text-text-primary">
                {indicator.value}
              </p>
              <FearGreedGauge score={indicator.score ?? 68} />
              <p className="mt-1 text-[11px] leading-none text-text-muted">
                Position Size:{" "}
                <span className="font-mono text-text-secondary">
                  {indicator.positionSize}
                </span>
              </p>
            </>
          )}

          {indicator.id === "volume" && (
            <>
              <p className="mt-1 text-[16px] font-medium leading-none text-mint">
                {indicator.value}
              </p>
              <MiniBarChart data={VOLUME_BARS} />
              <p className="mt-1 text-[11px] leading-none text-text-muted">
                Volumen Ratio:{" "}
                <span className="font-mono text-text-secondary">
                  {indicator.volumeRatio}
                </span>
              </p>
            </>
          )}

          {indicator.id === "volatility" && (
            <>
              <p className="mt-1 font-mono text-[15px] leading-none text-text-primary">
                {indicator.value}
              </p>
              <Sparkline data={SPARKLINE_DATA} />
            </>
          )}
        </Card>
      ))}
    </div>
  );
}
