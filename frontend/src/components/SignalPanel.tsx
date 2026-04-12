import type { AnalysisResponse, SignalItem } from "../api/types";

interface Props {
  analysis: AnalysisResponse | null;
}

function fmt(n: number, digits = 0): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function rr(sig: SignalItem): string {
  const risk   = Math.abs(sig.entry - sig.sl);
  const reward = Math.abs(sig.tp1  - sig.entry);
  if (!risk) return "–";
  return (reward / risk).toFixed(2);
}

function fmtTime(unix: number): string {
  return new Date(unix * 1000).toLocaleString("en-US", {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
    hour12: false,
  });
}

function ConvictionBadge({ value }: { value: string }) {
  const cls =
    value === "high"   ? "badge-high" :
    value === "normal" ? "badge-normal" :
                         "badge-low";
  return <span className={`conviction-badge ${cls}`}>{value.toUpperCase()}</span>;
}

function SignalCard({ sig }: { sig: SignalItem }) {
  const isLong = sig.side === "LONG";
  const risk   = Math.abs(sig.entry - sig.sl);

  const tp1Pct = risk ? ((Math.abs(sig.tp1 - sig.entry) / sig.entry) * 100).toFixed(2) : "–";
  const tp2Pct = risk ? ((Math.abs(sig.tp2 - sig.entry) / sig.entry) * 100).toFixed(2) : "–";
  const slPct  = sig.entry ? ((risk / sig.entry) * 100).toFixed(2) : "–";

  return (
    <div className={`signal-card ${isLong ? "signal-long" : "signal-short"}`}>
      <div className="signal-card-header">
        <span className={`side-badge ${isLong ? "long" : "short"}`}>
          {isLong ? "▲ LONG" : "▼ SHORT"}
        </span>
        <ConvictionBadge value={sig.conviction} />
        <span className="signal-time">{fmtTime(sig.time)}</span>
      </div>

      <div className="signal-price">
        <span className="price-label">Entry</span>
        <span className="price-value">${fmt(sig.entry)}</span>
      </div>

      <div className="signal-levels">
        <div className="level-row tp">
          <span>TP1</span>
          <span>${fmt(sig.tp1)}</span>
          <span className="pct">+{tp1Pct}%</span>
          <span className="rr-tag">R {rr(sig)}</span>
        </div>
        <div className="level-row tp">
          <span>TP2</span>
          <span>${fmt(sig.tp2)}</span>
          <span className="pct">+{tp2Pct}%</span>
        </div>
        <div className="level-row sl">
          <span>SL</span>
          <span>${fmt(sig.sl)}</span>
          <span className="pct">−{slPct}%</span>
        </div>
      </div>

      <div className="signal-ml">
        <span className="ml-label">ML Bias</span>
        <span
          className={`ml-value ${sig.ml_bias > 0 ? "ml-bull" : "ml-bear"}`}
        >
          {sig.ml_bias > 0 ? "+" : ""}{sig.ml_bias.toFixed(3)}
        </span>
      </div>

      {sig.reasons && (
        <div className="signal-reasons">
          {sig.reasons.split(",").map((r, i) => (
            <span key={i} className="reason-tag">{r.trim()}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function SignalPanel({ analysis }: Props) {
  const signals = analysis?.signals ?? [];
  const recent  = [...signals].reverse().slice(0, 5);

  if (!analysis) {
    return (
      <aside className="signal-panel">
        <h3 className="panel-title">Signals</h3>
        <p className="panel-empty">Select an asset to load signals.</p>
      </aside>
    );
  }

  if (recent.length === 0) {
    return (
      <aside className="signal-panel">
        <h3 className="panel-title">Signals</h3>
        <p className="panel-empty">No signals above threshold.</p>
      </aside>
    );
  }

  const last = recent[0];
  const longCount  = signals.filter((s) => s.side === "LONG").length;
  const shortCount = signals.filter((s) => s.side === "SHORT").length;
  const bullBias   = signals.length ? Math.round((longCount / signals.length) * 100) : 50;

  return (
    <aside className="signal-panel">
      <h3 className="panel-title">Signals</h3>

      {/* Bias bar */}
      <div className="bias-bar-wrap">
        <div className="bias-bar">
          <div className="bias-fill-bull" style={{ width: `${bullBias}%` }} />
          <div className="bias-fill-bear" style={{ width: `${100 - bullBias}%` }} />
        </div>
        <div className="bias-labels">
          <span className="bull">{bullBias}% Bull</span>
          <span className="bear">{100 - bullBias}% Bear</span>
        </div>
      </div>

      {/* Latest signal highlight */}
      <div className="latest-signal-label">Latest Setup</div>
      <SignalCard sig={last} />

      {/* Recent signals list */}
      {recent.length > 1 && (
        <>
          <div className="latest-signal-label" style={{ marginTop: 16 }}>Recent</div>
          <div className="recent-signals">
            {recent.slice(1).map((sig, i) => (
              <div key={i} className="recent-row">
                <span className={`side-dot ${sig.side === "LONG" ? "long" : "short"}`} />
                <span className="recent-side">{sig.side}</span>
                <span className="recent-price">${fmt(sig.entry)}</span>
                <span className="recent-time">{fmtTime(sig.time)}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}
