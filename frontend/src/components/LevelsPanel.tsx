import type {
  AnalysisResponse,
  FVGZone,
  OrderBlock,
  EqualLevel,
  StrongWeakLevel,
  PremiumDiscountZone,
  RangeZone,
} from "../api/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmt(n: number): string {
  return n < 100
    ? n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

interface Props { analysis: AnalysisResponse | null }

// ─── Small row atoms ──────────────────────────────────────────────────────────
function FVGRow({ f, lastClose }: { f: FVGZone; lastClose: number }) {
  const isBull    = f.bias === 1;
  const mid       = (f.top + f.bottom) / 2;
  const mitigated = !f.active;
  return (
    <div className={`lvl-row ${isBull ? "bull" : "bear"} ${mitigated ? "mitigated" : ""}`}>
      <span className={`lvl-dot ${isBull ? "bull" : "bear"}`} />
      <span className="lvl-type">{isBull ? "Bull FVG" : "Bear FVG"}</span>
      <span className="lvl-range">{fmt(f.bottom)} – {fmt(f.top)}</span>
      <span className="lvl-mid">mid {fmt(mid)}</span>
      {mitigated && <span className="lvl-tag">filled</span>}
    </div>
  );
}

function OBRow({ ob }: { ob: OrderBlock }) {
  const isBull = ob.bias === 1;
  const tag    = ob.scope === "swing" ? (isBull ? "Bull OB" : "Bear OB") : (isBull ? "iBull OB" : "iBear OB");
  return (
    <div className={`lvl-row ${isBull ? "bull" : "bear"} ${!ob.active ? "mitigated" : ""}`}>
      <span className={`lvl-dot ${isBull ? "bull" : "bear"} ${ob.scope === "internal" ? "dot-small" : ""}`} />
      <span className="lvl-type">{tag}</span>
      <span className="lvl-range">{fmt(ob.bottom)} – {fmt(ob.top)}</span>
      {!ob.active && <span className="lvl-tag">violated</span>}
    </div>
  );
}

function EQLRow({ el }: { el: EqualLevel }) {
  const isEQH = el.label === "EQH";
  return (
    <div className={`lvl-row ${isEQH ? "bear" : "bull"}`}>
      <span className={`lvl-dot ${isEQH ? "bear" : "bull"}`} />
      <span className="lvl-type">{el.label}</span>
      <span className="lvl-range">{fmt(el.level)}</span>
    </div>
  );
}

function SWRow({ sw }: { sw: StrongWeakLevel }) {
  const isStrong = sw.label.startsWith("Strong");
  const isHigh   = sw.label.includes("High");
  const cls      = isHigh ? (isStrong ? "bear" : "bear-dim") : (isStrong ? "bull" : "bull-dim");
  return (
    <div className={`lvl-row sw-row ${cls}`}>
      <span className={`lvl-dot ${isHigh ? "bear" : "bull"}`} />
      <span className="lvl-type">{sw.label}</span>
      <span className="lvl-range">{fmt(sw.level)}</span>
      {isStrong && <span className="lvl-tag strong">★</span>}
    </div>
  );
}

function PDRow({ z }: { z: PremiumDiscountZone }) {
  const cls  = z.zone_type === "premium" ? "bear" : z.zone_type === "discount" ? "bull" : "neutral";
  const icon = z.zone_type === "premium" ? "↑" : z.zone_type === "discount" ? "↓" : "≡";
  return (
    <div className={`lvl-row pd-row ${cls}`}>
      <span className="lvl-dot-icon">{icon}</span>
      <span className="lvl-type">{z.zone_type.charAt(0).toUpperCase() + z.zone_type.slice(1)}</span>
      <span className="lvl-range">{fmt(z.bottom)} – {fmt(z.top)}</span>
    </div>
  );
}

function RangeCard({ r }: { r: RangeZone }) {
  const spread    = r.high - r.low;
  const spreadPct = r.low ? ((spread / r.low) * 100).toFixed(1) : "–";
  return (
    <div className="range-card">
      <div className="range-header">
        <span className="range-label">Consolidation Range</span>
        <span className="range-spread">{spreadPct}% spread</span>
      </div>
      <div className="range-levels">
        <div className="range-level bear"><span>High</span><span className="range-price">{fmt(r.high)}</span></div>
        <div className="range-level neutral"><span>Mid</span><span className="range-price">{fmt(r.mid)}</span></div>
        <div className="range-level bull"><span>Low</span><span className="range-price">{fmt(r.low)}</span></div>
      </div>
    </div>
  );
}

// ─── Main panel ───────────────────────────────────────────────────────────────
export function LevelsPanel({ analysis }: Props) {
  if (!analysis) {
    return <section className="levels-panel"><p className="panel-empty">Select an asset to load levels.</p></section>;
  }

  const lastClose = analysis.candles.at(-1)?.close ?? 0;

  // Counts for stats strip
  const swingBOS   = analysis.swing_structure.filter((b) => b.break_type.startsWith("bos")).length;
  const swingCHoCH = analysis.swing_structure.filter((b) => b.break_type.startsWith("choch")).length;
  const intBOS     = analysis.internal_structure.filter((b) => b.break_type.startsWith("bos")).length;
  const intCHoCH   = analysis.internal_structure.filter((b) => b.break_type.startsWith("choch")).length;
  const activeOBs  = analysis.order_blocks.filter((o) => o.active).length;
  const activeFVGs = analysis.fvgs.filter((f) => f.active).length;
  const eqCount    = analysis.equal_levels.length;

  // FVGs: active only, nearest to price
  const activeFVGList = analysis.fvgs.filter((f) => f.active);
  const bullFVGs = [...activeFVGList.filter((f) => f.bias === 1)].sort((a, b) => a.bottom - b.bottom).slice(-4).reverse();
  const bearFVGs = [...activeFVGList.filter((f) => f.bias === -1)].sort((a, b) => b.top - a.top).slice(0, 4);

  // OBs: active only, swing first then internal, nearest to price
  const activeOBList = analysis.order_blocks.filter((o) => o.active);
  const bullOBs = [...activeOBList.filter((o) => o.bias === 1)].sort((a, b) => b.bottom - a.bottom).slice(0, 4);
  const bearOBs = [...activeOBList.filter((o) => o.bias === -1)].sort((a, b) => a.top - b.top).slice(0, 4);

  // Equal levels
  const eqhs = analysis.equal_levels.filter((e) => e.label === "EQH").slice(-3).reverse();
  const eqls = analysis.equal_levels.filter((e) => e.label === "EQL").slice(-3).reverse();

  // Range
  const lastRange = analysis.ranges.at(-1);

  return (
    <section className="levels-panel">

      {/* ── Stats strip ───────────────────────────────────────────── */}
      <div className="structure-stats">
        <div className="stat-chip">
          <span className="stat-val blue">{swingBOS}</span>
          <span className="stat-lbl">S.BOS</span>
        </div>
        <div className="stat-chip">
          <span className="stat-val orange">{swingCHoCH}</span>
          <span className="stat-lbl">S.CHoCH</span>
        </div>
        <div className="stat-chip">
          <span className="stat-val" style={{ color: "#58a6ff80" }}>{intBOS}</span>
          <span className="stat-lbl">i.BOS</span>
        </div>
        <div className="stat-chip">
          <span className="stat-val" style={{ color: "#f0883e80" }}>{intCHoCH}</span>
          <span className="stat-lbl">i.CHoCH</span>
        </div>
        <div className="stat-chip">
          <span className="stat-val green">{activeFVGs}</span>
          <span className="stat-lbl">FVGs</span>
        </div>
        <div className="stat-chip">
          <span className="stat-val green">{activeOBs}</span>
          <span className="stat-lbl">OBs</span>
        </div>
        <div className="stat-chip">
          <span className="stat-val" style={{ color: "var(--yellow)" }}>{eqCount}</span>
          <span className="stat-lbl">EQH/L</span>
        </div>
      </div>

      {/* ── Five-column grid ─────────────────────────────────────────── */}
      <div className="levels-columns">

        {/* Fair Value Gaps */}
        <div className="levels-col">
          <h4 className="levels-col-title">Fair Value Gaps <span className="col-subtitle">(active)</span></h4>
          {bearFVGs.length === 0 && bullFVGs.length === 0 && <p className="panel-empty">None active.</p>}
          {bearFVGs.map((f, i) => <FVGRow key={`bf${i}`} f={f} lastClose={lastClose} />)}
          {bullFVGs.map((f, i) => <FVGRow key={`uf${i}`} f={f} lastClose={lastClose} />)}
        </div>

        {/* Order Blocks */}
        <div className="levels-col">
          <h4 className="levels-col-title">Order Blocks <span className="col-subtitle">(active)</span></h4>
          {bearOBs.length === 0 && bullOBs.length === 0 && <p className="panel-empty">None active.</p>}
          {bearOBs.map((o, i) => <OBRow key={`bo${i}`} ob={o} />)}
          {bullOBs.map((o, i) => <OBRow key={`uo${i}`} ob={o} />)}
        </div>

        {/* Equal Highs / Lows + Strong/Weak */}
        <div className="levels-col">
          <h4 className="levels-col-title">Equal Highs / Lows</h4>
          {eqhs.length === 0 && eqls.length === 0
            ? <p className="panel-empty">None detected.</p>
            : [...eqhs, ...eqls].map((el, i) => <EQLRow key={i} el={el} />)}

          <h4 className="levels-col-title" style={{ marginTop: 14 }}>Strong / Weak</h4>
          {analysis.strong_weak.map((sw, i) => <SWRow key={i} sw={sw} />)}
        </div>

        {/* Range + Premium/Discount */}
        <div className="levels-col">
          <h4 className="levels-col-title">Range Analysis</h4>
          {lastRange ? <RangeCard r={lastRange} /> : <p className="panel-empty">No active range.</p>}

          <h4 className="levels-col-title" style={{ marginTop: 14 }}>Premium / Discount</h4>
          {analysis.premium_discount.map((z, i) => <PDRow key={i} z={z} />)}
        </div>

        {/* Recent structure events */}
        <div className="levels-col">
          <h4 className="levels-col-title">Recent Structure</h4>
          {[...analysis.swing_structure].reverse().slice(0, 6).map((b, i) => {
            const isBull = b.break_type.includes("up");
            const isBOS  = b.break_type.startsWith("bos");
            return (
              <div key={i} className={`lvl-row ${isBull ? "bull" : "bear"}`}>
                <span className={`lvl-dot ${isBull ? "bull" : "bear"}`} />
                <span className="lvl-type" style={{ color: isBOS ? "var(--blue)" : "var(--orange)" }}>
                  {isBOS ? "BOS" : "CHoCH"} {isBull ? "↑" : "↓"}
                </span>
                <span className="lvl-range">{fmt(b.level)}</span>
              </div>
            );
          })}
          {[...analysis.internal_structure].reverse().slice(0, 4).map((b, i) => {
            const isBull = b.break_type.includes("up");
            const isBOS  = b.break_type.startsWith("bos");
            return (
              <div key={`i${i}`} className={`lvl-row ${isBull ? "bull" : "bear"} mitigated`}>
                <span className={`lvl-dot ${isBull ? "bull" : "bear"} dot-small`} />
                <span className="lvl-type" style={{ color: isBOS ? "#58a6ff80" : "#f0883e80" }}>
                  {isBOS ? "iBOS" : "iCHoCH"} {isBull ? "↑" : "↓"}
                </span>
                <span className="lvl-range">{fmt(b.level)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
