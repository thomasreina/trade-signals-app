import { useEffect, useState } from "react";
import axios from "axios";

// -------------------------------------------------------
// Types — match your backend FastAPI models
// -------------------------------------------------------

export interface Signal {
  timestamp: string;
  side: string;
  close: number;
  m_bias: number;
  m_conviction: string;
  sl: number;
  tp1: number;
  tp2: number;
  reasons: string;
}

export interface TradeBacktest {
  entry_time: string;
  exit_time: string;
  side: string;
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  exit_price: number;
  exit_reason: string;
  R: number;
}

// -------------------------------------------------------
// API base — Always /api inside Docker
// -------------------------------------------------------

const API_BASE = "/api";

// -------------------------------------------------------
// Main Component
// -------------------------------------------------------

function App() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [backtests, setBacktests] = useState<TradeBacktest[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [signalsRes, backtestsRes] = await Promise.all([
          axios.get<Signal[]>(`${API_BASE}/signals/latest`),
          axios.get<TradeBacktest[]>(`${API_BASE}/backtest/smc`),
        ]);

        setSignals(signalsRes.data);
        setBacktests(backtestsRes.data);
      } catch (err) {
        console.error("Error fetching API data:", err);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, []);

  if (loading) return <div style={{ padding: 20 }}>Loading...</div>;

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h1>Trade Signals Dashboard</h1>

      <h2>Latest Signals</h2>
      <ul>
        {signals.map((s, i) => (
          <li key={i}>
            <strong>{s.timestamp}</strong> — {s.side} @ {s.close}  
            (TP1 {s.tp1}, TP2 {s.tp2}, SL {s.sl})
          </li>
        ))}
      </ul>

      <h2>Backtests (SMC)</h2>
      <ul>
        {backtests.map((b, i) => (
          <li key={i}>
            <strong>{b.entry_time}</strong> → {b.exit_time}  
            | {b.side} | Entry {b.entry} | Exit {b.exit_price}  
            | R: {b.R}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default App;
