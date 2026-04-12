import type { AnalysisResponse, FVGZone, OrderBlock, RangeZone } from "../api/types";

interface Props {
  analysis: AnalysisResponse | null;
}

function fmt(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fmtFull(n: number): string {
  // Use more decimals for small-price assets
  return n < 100
    ? n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function FVGRow({ zone, lastClose }: { zone: FVGZone; lastClose: number }) {
  const isBull    = zone.type === "bull";
  const isAbove   = zone.low > lastClose;
  const isBelow   = zone.high < lastClose;
  const mitigated = isBull ? isBelow : isAbove;
  const mid       = (zone.low + zone.high) / 2;

  return (
    <div className={`level-row-item ${isBull ? "bull" : "bear"} ${mitigated ? "mitigated" : ""}`}>
      <span className={`level-type-dot ${isBull ? "bull" : "bear"}`} />
      <span className="level-type">{isBull ? "Bull FVG" : "Bear FVG"}</span>
      <span className="level-range">{fmtFull(zone.low)} – {fmtFull(zone.high)}</span>
      <span className="level-mid">mid {fmtFull(mid)}</span>
      {mitigated && <span className="mitigated-tag">filled</span>}
    </div>
  );
}

function OBRow({ ob, lastClose }: { ob: OrderBlock; lastClose: number }) {
  const isBull   = ob.type === "bull";
  const violated = isBull ? lastClose < ob.low : lastClose > ob.high;

  return (
    <div className={`level-row-item ${isBull ? "bull" : "bear"} ${violated ? "mitigated" : ""}`}>
      <span className={`level-type-dot ${isBull ? "bull" : "bear"}`} />
      <span className="level-type">{isBull ? "Bull OB" : "Bear OB"}</span>
      <span className="level-range">{fmtFull(ob.low)} – {fmtFull(ob.high)}</span>
      {violated && <span className="mitigated-tag">violated</span>}
    </div>
  );
}

function RangeRow({ range }: { range: RangeZone }) {
  const spread    = range.high - range.low;
  const spreadPct = range.low ? ((spread / range.low) * 100).toFixed(1) : "–";

  return (
    <div className="range-card">
      <div className="range-header">
        <span className="range-label">Consolidation Range</span>
        <span className="range-spread">{spreadPct}% spread</span>
      </div>
      <div className="range-levels">
        <div className="range-level bear">
          <span>High</span><span className="range-price">${fmt(range.high)}</span>
        </div>
        <div className="range-level neutral">
          <span>Mid</span><span className="range-price">${fmt(range.mid)}</span>
        </div>
        <div className="range-level bull">
          <span>Low</span><span className="range-price">${fmt(range.low)}</span>
        </div>
      </div>
    </div>
  );
}

export function LevelsPanel({ analysis }: Props) {
  if (!analysis) {
    return (
      <section className="levels-panel">
        <p className="panel-empty">No data loaded.</p>
      </section>
    );
  }

  const lastClose = analysis.candles.at(-1)?.close ?? 0;

  // Show last 8 FVGs, grouped bull/bear
  const recentFVGs  = analysis.fvg_zones.slice(-16);
  const bullFVGs    = recentFVGs.filter((f) => f.type === "bull").reverse().slice(0, 4);
  const bearFVGs    = recentFVGs.filter((f) => f.type === "bear").reverse().slice(0, 4);

  // Show last 6 OBs
  const recentOBs   = analysis.order_blocks.slice(-12);
  const bullOBs     = recentOBs.filter((o) => o.type === "bull").reverse().slice(0, 3);
  const bearOBs     = recentOBs.filter((o) => o.type === "bear").reverse().slice(0, 3);

  // Most recent range
  const lastRange   = analysis.ranges.at(-1);

  // Structure stats
  const bosCount    = analysis.structure_events.filter((e) => e.type.startsWith("bos")).length;
  const chochCount  = analysis.structure_events.filter((e) => e.type.startsWith("choch")).length;
  const sweepCount  = analysis.sweeps.length;

  return (
    <section className="levels-panel">
      {/* ── Structure stats strip ───────────────────────────────────── */}
      <div className="structure-stats">
        <div className="stat-chip">
          <span className="stat-val blue">{bosCount}</span>
          <span className="stat-lbl">BOS</span>
        </div>
        <div className="stat-chip">
          <span className="stat-val orange">{chochCount}</span>
          <span className="stat-lbl">CHoCH</span>
        </div>
        <div className="stat-chip">
          <span className="stat-val purple">{sweepCount}</span>
          <span className="stat-lbl">Sweeps</span>
        </div>
        <div className="stat-chip">
          <span className="stat-val green">{analysis.fvg_zones.length}</span>
          <span className="stat-lbl">FVGs</span>
        </div>
        <div className="stat-chip">
          <span className="stat-val green">{analysis.order_blocks.length}</span>
          <span className="stat-lbl">OBs</span>
        </div>
      </div>

      {/* ── Three columns ───────────────────────────────────────────── */}
      <div className="levels-columns">

        {/* Fair Value Gaps */}
        <div className="levels-col">
          <h4 className="levels-col-title">Fair Value Gaps</h4>
          {bullFVGs.length === 0 && bearFVGs.length === 0 && (
            <p className="panel-empty">None detected.</p>
          )}
          {bearFVGs.map((f, i) => (
            <FVGRow key={`bf${i}`} zone={f} lastClose={lastClose} />
          ))}
          {bullFVGs.map((f, i) => (
            <FVGRow key={`uf${i}`} zone={f} lastClose={lastClose} />
          ))}
        </div>

        {/* Order Blocks */}
        <div className="levels-col">
          <h4 className="levels-col-title">Order Blocks</h4>
          {bullOBs.length === 0 && bearOBs.length === 0 && (
            <p className="panel-empty">None detected.</p>
          )}
          {bearOBs.map((o, i) => (
            <OBRow key={`bo${i}`} ob={o} lastClose={lastClose} />
          ))}
          {bullOBs.map((o, i) => (
            <OBRow key={`uo${i}`} ob={o} lastClose={lastClose} />
          ))}
        </div>

        {/* Range */}
        <div className="levels-col">
          <h4 className="levels-col-title">Range Analysis</h4>
          {lastRange ? (
            <RangeRow range={lastRange} />
          ) : (
            <p className="panel-empty">No active range detected.</p>
          )}

          {/* Recent sweeps */}
          {analysis.sweeps.length > 0 && (
            <>
              <h4 className="levels-col-title" style={{ marginTop: 16 }}>
                Recent Sweeps
              </h4>
              {analysis.sweeps.slice(-4).reverse().map((sw, i) => (
                <div key={i} className={`level-row-item ${sw.type === "sweep_high" ? "bear" : "bull"}`}>
                  <span className={`level-type-dot ${sw.type === "sweep_high" ? "bear" : "bull"}`} />
                  <span className="level-type">
                    {sw.type === "sweep_high" ? "High Sweep" : "Low Sweep"}
                  </span>
                  <span className="level-range">${fmtFull(sw.level)}</span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
