import { useEffect, useRef } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  SeriesMarker,
  Time,
  CandlestickData,
  HistogramData,
  ColorType,
  CrosshairMode,
  LineStyle,
} from "lightweight-charts";
import type { AnalysisResponse } from "../api/types";

// ─── Colour palette ───────────────────────────────────────────────────────────
const C = {
  bg:           "#0d1117",
  grid:         "#161b22",
  text:         "#8b949e",
  border:       "#30363d",
  // Candles
  up:           "#26a69a",
  dn:           "#ef5350",
  // Structure breaks
  bosBlue:      "#58a6ff",
  chochOrange:  "#f0883e",
  // Sweeps / EQH/EQL
  sweepPurple:  "#bc8cff",
  eqYellow:     "#e3b341",
  // Swing labels (HH/HL/LH/LL)
  hhhl:         "#26a69a",
  lhlh:         "#ef5350",
  // Internal structure (smaller markers, dimmer)
  intBos:       "#58a6ff80",
  intChoch:     "#f0883e80",
  // Strong/Weak lines
  strongHigh:   "#ef5350c0",
  weakHigh:     "#ef535060",
  strongLow:    "#26a69ac0",
  weakLow:      "#26a69a60",
  // Range lines
  rangeHi:      "#ef535070",
  rangeMid:     "#f0883e70",
  rangeLo:      "#26a69a70",
  // FVG levels
  fvgBull:      "#26a69a90",
  fvgBear:      "#ef535090",
  // OB levels
  obBullSwing:  "#1848ccb0",
  obBearSwing:  "#b22833b0",
  obBullInt:    "#3179f5b0",
  obBearInt:    "#f77c80b0",
};

interface Props {
  analysis: AnalysisResponse | null;
  loading:  boolean;
}

export function TradingChart({ analysis, loading }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<IChartApi | null>(null);
  const candleRef    = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef       = useRef<ISeriesApi<"Histogram"> | null>(null);
  const plinesRef    = useRef<ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[]>([]);

  // ── Initialise chart ─────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height: 540,
      layout: {
        background: { type: ColorType.Solid, color: C.bg },
        textColor:  C.text,
      },
      grid: {
        vertLines: { color: C.grid },
        horzLines: { color: C.grid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: C.border, labelBackgroundColor: "#21262d" },
        horzLine: { color: C.border, labelBackgroundColor: "#21262d" },
      },
      rightPriceScale: { borderColor: C.border },
      timeScale: {
        borderColor:    C.border,
        timeVisible:    true,
        secondsVisible: false,
        rightOffset:    8,
        barSpacing:     8,
      },
    });

    const candles = chart.addCandlestickSeries({
      upColor:      C.up,
      downColor:    C.dn,
      borderVisible: false,
      wickUpColor:   C.up,
      wickDownColor: C.dn,
    });

    const volume = chart.addHistogramSeries({
      color:        `${C.up}40`,
      priceFormat:  { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chartRef.current  = chart;
    candleRef.current = candles;
    volRef.current    = volume;

    const onResize = () => {
      if (containerRef.current)
        chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
    };
  }, []);

  // ── Update when analysis changes ─────────────────────────────────
  useEffect(() => {
    if (!analysis || !candleRef.current || !volRef.current) return;

    // Candle data
    const cData: CandlestickData[] = analysis.candles.map((c) => ({
      time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close,
    }));
    candleRef.current.setData(cData);

    // Volume bars
    const vData: HistogramData[] = analysis.candles.map((c) => ({
      time:  c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? `${C.up}50` : `${C.dn}50`,
    }));
    volRef.current.setData(vData);

    // ── Build markers ─────────────────────────────────────────────
    const markers: SeriesMarker<Time>[] = [];

    // Swing structure breaks (larger markers)
    for (const b of analysis.swing_structure) {
      const isBull = b.break_type.includes("up");
      const isBOS  = b.break_type.startsWith("bos");
      markers.push({
        time:     b.time as Time,
        position: isBull ? "belowBar" : "aboveBar",
        color:    isBOS ? C.bosBlue : C.chochOrange,
        shape:    isBull ? "arrowUp" : "arrowDown",
        text:     isBOS ? "BOS" : "CHoCH",
        size:     2,
      });
    }

    // Internal structure breaks (smaller, dimmer)
    for (const b of analysis.internal_structure) {
      const isBull = b.break_type.includes("up");
      const isBOS  = b.break_type.startsWith("bos");
      markers.push({
        time:     b.time as Time,
        position: isBull ? "belowBar" : "aboveBar",
        color:    isBOS ? C.intBos : C.intChoch,
        shape:    isBull ? "arrowUp" : "arrowDown",
        text:     isBOS ? "iBOS" : "iCHoCH",
        size:     1,
      });
    }

    // Equal Highs / Lows
    for (const el of analysis.equal_levels) {
      const isEQH = el.label === "EQH";
      markers.push({
        time:     el.time2 as Time,
        position: isEQH ? "aboveBar" : "belowBar",
        color:    C.eqYellow,
        shape:    "circle",
        text:     el.label,
        size:     1,
      });
    }

    // Swing point labels (HH / HL / LH / LL) — only swing, not internal
    for (const p of [...analysis.swing_highs, ...analysis.swing_lows]) {
      const isHigh   = p.pivot_type === "high";
      const isBullLabel = p.label === "HL" || p.label === "HH";
      markers.push({
        time:     p.time as Time,
        position: isHigh ? "aboveBar" : "belowBar",
        color:    isBullLabel ? C.hhhl : C.lhlh,
        shape:    "circle",
        text:     p.label,
        size:     1,
      });
    }

    // Signals (prominent arrows)
    for (const sig of analysis.signals) {
      const isLong = sig.side === "LONG";
      markers.push({
        time:     sig.time as Time,
        position: isLong ? "belowBar" : "aboveBar",
        color:    isLong ? C.up : C.dn,
        shape:    isLong ? "arrowUp" : "arrowDown",
        text:     sig.side,
        size:     3,
      });
    }

    markers.sort((a, b) => (a.time as number) - (b.time as number));
    candleRef.current.setMarkers(markers);

    // ── Remove stale price lines ──────────────────────────────────
    for (const pl of plinesRef.current) {
      try { candleRef.current.removePriceLine(pl); } catch { /* ignore */ }
    }
    plinesRef.current = [];

    const addLine = (
      price: number,
      color: string,
      style: LineStyle,
      title: string,
      width: 1 | 2 = 1,
    ) => {
      if (!candleRef.current || !price || !isFinite(price)) return;
      const pl = candleRef.current.createPriceLine({
        price, color, lineWidth: width, lineStyle: style,
        axisLabelVisible: true, title,
      });
      plinesRef.current.push(pl);
    };

    const lastClose = analysis.candles.at(-1)?.close ?? 0;

    // ── Strong / Weak levels (dashed lines) ───────────────────────
    for (const sw of analysis.strong_weak) {
      const isStrong = sw.label.startsWith("Strong");
      const isHigh   = sw.label.includes("High");
      const color    = isHigh
        ? (isStrong ? C.strongHigh : C.weakHigh)
        : (isStrong ? C.strongLow  : C.weakLow);
      addLine(sw.level, color, LineStyle.Dashed, sw.label, 2);
    }

    // ── Current consolidation range ────────────────────────────────
    if (analysis.ranges.length > 0) {
      const r = analysis.ranges.at(-1)!;
      addLine(r.high, C.rangeHi,  LineStyle.Dashed, "R.Hi");
      addLine(r.mid,  C.rangeMid, LineStyle.Dotted, "R.Mid");
      addLine(r.low,  C.rangeLo,  LineStyle.Dashed, "R.Lo");
    }

    // ── Nearest active FVG above and below ─────────────────────────
    const activeFVGs = analysis.fvgs.filter((f) => f.active);
    const nearBullFVG = activeFVGs
      .filter((f) => f.bias === 1 && f.bottom > lastClose * 0.98)
      .sort((a, b) => a.bottom - b.bottom)[0];
    const nearBearFVG = activeFVGs
      .filter((f) => f.bias === -1 && f.top < lastClose * 1.02)
      .sort((a, b) => b.top - a.top)[0];

    if (nearBullFVG) {
      addLine(nearBullFVG.bottom, C.fvgBull, LineStyle.Solid, "FVG↑lo");
      addLine(nearBullFVG.top,    C.fvgBull, LineStyle.Solid, "FVG↑hi");
    }
    if (nearBearFVG) {
      addLine(nearBearFVG.bottom, C.fvgBear, LineStyle.Solid, "FVG↓lo");
      addLine(nearBearFVG.top,    C.fvgBear, LineStyle.Solid, "FVG↓hi");
    }

    // ── Nearest active OBs ─────────────────────────────────────────
    const activeOBs = analysis.order_blocks.filter((o) => o.active);
    const nearBullSwingOB = activeOBs
      .filter((o) => o.bias === 1 && o.scope === "swing" && o.top >= lastClose * 0.95)
      .sort((a, b) => b.bottom - a.bottom)[0];
    const nearBearSwingOB = activeOBs
      .filter((o) => o.bias === -1 && o.scope === "swing" && o.bottom <= lastClose * 1.05)
      .sort((a, b) => a.top - b.top)[0];
    const nearBullIntOB = activeOBs
      .filter((o) => o.bias === 1 && o.scope === "internal" && o.top >= lastClose * 0.97)
      .sort((a, b) => b.bottom - a.bottom)[0];
    const nearBearIntOB = activeOBs
      .filter((o) => o.bias === -1 && o.scope === "internal" && o.bottom <= lastClose * 1.03)
      .sort((a, b) => a.top - b.top)[0];

    if (nearBullSwingOB) {
      addLine(nearBullSwingOB.bottom, C.obBullSwing, LineStyle.Solid, "OB↑lo", 2);
      addLine(nearBullSwingOB.top,    C.obBullSwing, LineStyle.Solid, "OB↑hi", 2);
    }
    if (nearBearSwingOB) {
      addLine(nearBearSwingOB.bottom, C.obBearSwing, LineStyle.Solid, "OB↓lo", 2);
      addLine(nearBearSwingOB.top,    C.obBearSwing, LineStyle.Solid, "OB↓hi", 2);
    }
    if (nearBullIntOB) {
      addLine(nearBullIntOB.bottom, C.obBullInt, LineStyle.Dotted, "iOB↑lo");
      addLine(nearBullIntOB.top,    C.obBullInt, LineStyle.Dotted, "iOB↑hi");
    }
    if (nearBearIntOB) {
      addLine(nearBearIntOB.bottom, C.obBearInt, LineStyle.Dotted, "iOB↓lo");
      addLine(nearBearIntOB.top,    C.obBearInt, LineStyle.Dotted, "iOB↓hi");
    }

    chartRef.current?.timeScale().fitContent();
  }, [analysis]);

  return (
    <div className="chart-wrapper">
      {loading && (
        <div className="chart-loading">
          <span>Loading chart…</span>
        </div>
      )}
      <div ref={containerRef} style={{ width: "100%", height: 540 }} />
    </div>
  );
}
