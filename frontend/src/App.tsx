import { useEffect, useState, useCallback } from "react";
import "./App.css";
import { fetchAnalysis } from "./api/client";
import type { AnalysisResponse, Asset, Timeframe } from "./api/types";
import { TradingChart } from "./components/TradingChart";
import { SignalPanel }  from "./components/SignalPanel";
import { LevelsPanel }  from "./components/LevelsPanel";

// ─── constants ────────────────────────────────────────────────────────────────
const ASSETS:     Asset[]     = ["BTC", "ETH"];
const TIMEFRAMES: Timeframe[] = ["15m", "1h", "4h", "1d"];
const TF_LABELS: Record<Timeframe, string> = {
  "15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D",
};
const TF_LIMIT: Record<Timeframe, number> = {
  "15m": 200, "1h": 200, "4h": 150, "1d": 120,
};

// ─── helpers ──────────────────────────────────────────────────────────────────
function fmtPrice(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function PriceChange({ analysis }: { analysis: AnalysisResponse | null }) {
  if (!analysis || analysis.candles.length < 2) return null;
  const last  = analysis.candles.at(-1)!;
  const prev  = analysis.candles.at(-2)!;
  const pct   = ((last.close - prev.close) / prev.close) * 100;
  const color = pct >= 0 ? "var(--green)" : "var(--red)";
  return (
    <span className="price-change" style={{ color }}>
      {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
    </span>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [asset,     setAsset]     = useState<Asset>("BTC");
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const [analysis,  setAnalysis]  = useState<AnalysisResponse | null>(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const load = useCallback(async (a: Asset, tf: Timeframe) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAnalysis(a, tf, TF_LIMIT[tf]);
      setAnalysis(data);
      setLastUpdate(new Date());
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Failed to load ${a} ${tf}: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load on mount and whenever asset/timeframe changes
  useEffect(() => {
    load(asset, timeframe);
  }, [asset, timeframe, load]);

  const lastClose = analysis?.candles.at(-1)?.close ?? 0;

  const handleAssetChange = (a: Asset) => {
    setAsset(a);
    setAnalysis(null);
  };

  const handleTfChange = (tf: Timeframe) => {
    setTimeframe(tf);
    setAnalysis(null);
  };

  return (
    <div className="app">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="app-header">
        <div className="header-left">
          <span className="logo">⬡ SMC Analyzer</span>

          {/* Asset tabs */}
          <div className="tab-group">
            {ASSETS.map((a) => (
              <button
                key={a}
                className={`tab-btn ${a === asset ? "active" : ""}`}
                onClick={() => handleAssetChange(a)}
              >
                {a}/USDT
              </button>
            ))}
          </div>

          {/* Price */}
          {lastClose > 0 && (
            <div className="live-price">
              <span className="price-value">${fmtPrice(lastClose)}</span>
              <PriceChange analysis={analysis} />
            </div>
          )}
        </div>

        <div className="header-right">
          {/* Timeframe tabs */}
          <div className="tab-group tf-group">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                className={`tab-btn ${tf === timeframe ? "active" : ""}`}
                onClick={() => handleTfChange(tf)}
              >
                {TF_LABELS[tf]}
              </button>
            ))}
          </div>

          {/* Refresh */}
          <button
            className="refresh-btn"
            onClick={() => load(asset, timeframe)}
            disabled={loading}
            title="Refresh"
          >
            {loading ? "⟳" : "↺"}
          </button>

          {lastUpdate && (
            <span className="last-update">
              {lastUpdate.toLocaleTimeString("en-US", { hour12: false })}
            </span>
          )}
        </div>
      </header>

      {/* ── Error banner ────────────────────────────────────────────── */}
      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* ── Main content ────────────────────────────────────────────── */}
      <main className="app-main">
        <div className="chart-col">
          <TradingChart analysis={analysis} loading={loading} />
        </div>
        <div className="signal-col">
          <SignalPanel analysis={analysis} />
        </div>
      </main>

      {/* ── Levels panel (bottom) ────────────────────────────────────── */}
      <LevelsPanel analysis={analysis} />
    </div>
  );
}
