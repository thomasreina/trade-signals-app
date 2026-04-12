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

// ─── colours (trading terminal palette) ──────────────────────────────────────
const C = {
  bg:          "#0d1117",
  grid:        "#161b22",
  text:        "#8b949e",
  border:      "#30363d",
  upGreen:     "#26a69a",
  downRed:     "#ef5350",
  bosBlue:     "#58a6ff",
  chochOrange: "#f0883e",
  sweepPurple: "#bc8cff",
  rangeHigh:   "#ef535070",
  rangeMid:    "#f0883e70",
  rangeLow:    "#26a69a70",
  fvgBull:     "#26a69a90",
  fvgBear:     "#ef535090",
  obBull:      "#26a69ab0",
  obBear:      "#ef5350b0",
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

  // ── Initialise chart once ─────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height: 530,
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
      rightPriceScale: {
        borderColor: C.border,
      },
      timeScale: {
        borderColor:     C.border,
        timeVisible:     true,
        secondsVisible:  false,
        rightOffset:     8,
        barSpacing:      8,
      },
    });

    const candles = chart.addCandlestickSeries({
      upColor:     C.upGreen,
      downColor:   C.downRed,
      borderVisible: false,
      wickUpColor:   C.upGreen,
      wickDownColor: C.downRed,
    });

    const volume = chart.addHistogramSeries({
      color:        `${C.upGreen}40`,
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

  // ── Update data whenever analysis changes ─────────────────────────────────
  useEffect(() => {
    if (!analysis || !candleRef.current || !volRef.current) return;

    // Candles
    const candleData: CandlestickData[] = analysis.candles.map((c) => ({
      time:  c.time as Time,
      open:  c.open,
      high:  c.high,
      low:   c.low,
      close: c.close,
    }));
    candleRef.current.setData(candleData);

    // Volume bars (colour by candle direction)
    const volData: HistogramData[] = analysis.candles.map((c) => ({
      time:  c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? `${C.upGreen}50` : `${C.downRed}50`,
    }));
    volRef.current.setData(volData);

    // ── Markers ──────────────────────────────────────────────────────────────
    const markers: SeriesMarker<Time>[] = [];

    // BOS / CHoCH
    for (const evt of analysis.structure_events) {
      const isBull = evt.type.includes("up");
      const isBOS  = evt.type.startsWith("bos");
      markers.push({
        time:     evt.time as Time,
        position: isBull ? "belowBar" : "aboveBar",
        color:    isBOS ? C.bosBlue : C.chochOrange,
        shape:    isBull ? "arrowUp" : "arrowDown",
        text:     isBOS ? "BOS" : "CHoCH",
        size:     1,
      });
    }

    // Sweeps
    for (const sw of analysis.sweeps) {
      const isHigh = sw.type === "sweep_high";
      markers.push({
        time:     sw.time as Time,
        position: isHigh ? "aboveBar" : "belowBar",
        color:    C.sweepPurple,
        shape:    "circle",
        text:     isHigh ? "SWP↓" : "SWP↑",
        size:     1,
      });
    }

    // Signals
    for (const sig of analysis.signals) {
      const isLong = sig.side === "LONG";
      markers.push({
        time:     sig.time as Time,
        position: isLong ? "belowBar" : "aboveBar",
        color:    isLong ? C.upGreen : C.downRed,
        shape:    isLong ? "arrowUp" : "arrowDown",
        text:     sig.side,
        size:     2,
      });
    }

    markers.sort((a, b) => (a.time as number) - (b.time as number));
    candleRef.current.setMarkers(markers);

    // ── Price lines ───────────────────────────────────────────────────────────
    // Remove old lines
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
        price,
        color,
        lineWidth: width,
        lineStyle: style,
        axisLabelVisible: true,
        title,
      });
      plinesRef.current.push(pl);
    };

    // Current range lines
    if (analysis.ranges.length > 0) {
      const r = analysis.ranges[analysis.ranges.length - 1];
      addLine(r.high, C.rangeHigh, LineStyle.Dashed,  "R.Hi");
      addLine(r.mid,  C.rangeMid,  LineStyle.Dotted,  "R.Mid");
      addLine(r.low,  C.rangeLow,  LineStyle.Dashed,  "R.Lo");
    }

    // Nearest unmitigated FVGs (one bull above price, one bear below)
    const lastClose = analysis.candles.at(-1)?.close ?? 0;

    const nearBullFVG = [...analysis.fvg_zones]
      .filter((f) => f.type === "bull" && f.high > lastClose)
      .sort((a, b) => a.low - b.low)[0];
    const nearBearFVG = [...analysis.fvg_zones]
      .filter((f) => f.type === "bear" && f.low < lastClose)
      .sort((a, b) => b.high - a.high)[0];

    if (nearBullFVG) {
      addLine(nearBullFVG.low,  C.fvgBull, LineStyle.Solid, "FVG↑ lo");
      addLine(nearBullFVG.high, C.fvgBull, LineStyle.Solid, "FVG↑ hi");
    }
    if (nearBearFVG) {
      addLine(nearBearFVG.low,  C.fvgBear, LineStyle.Solid, "FVG↓ lo");
      addLine(nearBearFVG.high, C.fvgBear, LineStyle.Solid, "FVG↓ hi");
    }

    // Nearest OBs
    const nearBullOB = [...analysis.order_blocks]
      .filter((o) => o.type === "bull" && o.high >= lastClose * 0.97)
      .sort((a, b) => b.low - a.low)[0];
    const nearBearOB = [...analysis.order_blocks]
      .filter((o) => o.type === "bear" && o.low <= lastClose * 1.03)
      .sort((a, b) => a.high - b.high)[0];

    if (nearBullOB) {
      addLine(nearBullOB.low,  C.obBull, LineStyle.Solid, "OB↑ lo", 2);
      addLine(nearBullOB.high, C.obBull, LineStyle.Solid, "OB↑ hi", 2);
    }
    if (nearBearOB) {
      addLine(nearBearOB.low,  C.obBear, LineStyle.Solid, "OB↓ lo", 2);
      addLine(nearBearOB.high, C.obBear, LineStyle.Solid, "OB↓ hi", 2);
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
      <div ref={containerRef} style={{ width: "100%", height: 530 }} />
    </div>
  );
}
