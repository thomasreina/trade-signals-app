import os

# Ensure ML is enabled for this backtest process BEFORE importing the analyzer
os.environ.setdefault("USE_ML", "true")
os.environ.setdefault(
    "MODEL_PATH",
    f"models/rf_{os.getenv('SYMBOL_FUT', 'BTCUSDT')}_{os.getenv('TIMEFRAME', '1h')}.pkl"
)

import numpy as np
import pandas as pd
import ccxt

from signals_core import build_features
from market_structure_analyzer import (
    SYMBOL_SPOT,
    SYMBOL_FUT,
    OKX_UNDERLYING,
    TIMEFRAME,
    CANDLES,
    TZ,
    ML_BIAS_TH,
    ML_BIAS_HIGH_TH,
    load_price_df,
    attach_aggregated_oi_and_funding,
    compute_signals,
    ml_score_row,
    _build_fvg_lists,
    _smc_sl_tp,
)

# ---------------------------------------------------
# Build full dataframe with all features + ML bias
# ---------------------------------------------------

def build_full_df():
    ex = ccxt.binance()

    df = load_price_df(ex, SYMBOL_SPOT, TIMEFRAME, CANDLES, TZ)
    df = attach_aggregated_oi_and_funding(
        df, SYMBOL_FUT, OKX_UNDERLYING, TIMEFRAME, CANDLES, TZ
    )
    df = compute_signals(df)

    # ML bias per bar (same as live)
    ml_biases = []
    for i in range(len(df)):
        mb = ml_score_row(df, i, build_features)
        ml_biases.append(mb)
    df["ml_bias"] = ml_biases

    abs_mb = df["ml_bias"].abs()
    df["ml_conviction"] = np.where(
        abs_mb >= ML_BIAS_HIGH_TH,
        "high",
        np.where(abs_mb >= ML_BIAS_TH, "normal", "low"),
    )

    return df


# ---------------------------------------------------
# Backtest trade simulation using SMC SL/TP
# ---------------------------------------------------

def simulate_trades(df: pd.DataFrame):
    """
    For every bar where |ml_bias| >= ML_BIAS_TH:
      - Entry at close[i]
      - side = LONG if ml_bias>0, else SHORT
      - SL/TP1/TP2 from _smc_sl_tp (same as live script)
      - Walk forward bar by bar:
          first touch among {SL, TP2, TP1} closes the trade
      - Result expressed in R (R = (exit-entry)/|entry-SL|)
    """
    # Prebuild FVG maps once
    fvg_bull, fvg_bear = _build_fvg_lists(df)

    trades = []
    n = len(df)

    for i in range(n):
        row = df.iloc[i]
        mb = row.get("ml_bias", 0.0)

        # Filter: only take trades with sufficient ML conviction
        if abs(mb) < ML_BIAS_TH:
            continue

        side = "LONG" if mb > 0 else "SHORT"
        entry = float(row["close"])
        atr = row.get("atr14", np.nan)

        sl, tp1, tp2 = _smc_sl_tp(side, row, entry, atr, fvg_bull, fvg_bear)

        risk = abs(entry - sl)
        if risk <= 0 or np.isnan(risk):
            continue  # skip broken trade

        entry_time = row["timestamp"]

        exit_price = None
        exit_time = None
        exit_reason = None
        R = None

        # Walk forward
        for j in range(i + 1, n):
            r2 = df.iloc[j]
            high = float(r2["high"])
            low = float(r2["low"])
            t = r2["timestamp"]

            if side == "LONG":
                hit_sl = low <= sl
                hit_tp2 = high >= tp2
                hit_tp1 = high >= tp1
            else:
                hit_sl = high >= sl
                hit_tp2 = low <= tp2
                hit_tp1 = low <= tp1

            # First-touch priority: SL -> TP2 -> TP1
            if hit_sl:
                exit_price = sl
                exit_time = t
                exit_reason = "SL"
                R = -1.0
                break

            if hit_tp2:
                exit_price = tp2
                exit_time = t
                exit_reason = "TP2"
                if side == "LONG":
                    R = (tp2 - entry) / risk
                else:
                    R = (entry - tp2) / risk
                break

            if hit_tp1:
                exit_price = tp1
                exit_time = t
                exit_reason = "TP1"
                if side == "LONG":
                    R = (tp1 - entry) / risk
                else:
                    R = (entry - tp1) / risk
                break

        # If never hit anything → close at last bar close
        if exit_price is None:
            r_last = df.iloc[-1]
            exit_price = float(r_last["close"])
            exit_time = r_last["timestamp"]
            exit_reason = "timeout"
            if side == "LONG":
                R = (exit_price - entry) / risk
            else:
                R = (entry - exit_price) / risk

        trades.append(
            {
                "entry_time": entry_time,
                "exit_time": exit_time,
                "side": side,
                "ml_bias": mb,
                "ml_conviction": row["ml_conviction"],
                "entry": entry,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "R": R,
            }
        )

    return pd.DataFrame(trades)


# ---------------------------------------------------
# Stats / reporting
# ---------------------------------------------------

def summarize_backtest(trades: pd.DataFrame):
    if trades.empty:
        print("No trades generated for backtest.")
        return

    total = len(trades)
    wins = (trades["R"] > 0).sum()
    losses = (trades["R"] < 0).sum()
    winrate = wins / total if total > 0 else 0.0

    avg_R = trades["R"].mean()
    med_R = trades["R"].median()
    best_R = trades["R"].max()
    worst_R = trades["R"].min()

    # Simple equity curve in R
    trades_sorted = trades.sort_values("entry_time")
    trades_sorted["equity_R"] = trades_sorted["R"].cumsum()
    max_equity = trades_sorted["equity_R"].cummax()
    dd = trades_sorted["equity_R"] - max_equity
    max_dd = dd.min()  # most negative

    print("=== SMC+ML Backtest (per-trade in R) ===")
    print(f"Symbol / TF : {SYMBOL_FUT} / {TIMEFRAME}")
    print(f"Candles     : {CANDLES}")
    print(f"Trades      : {total}")
    print(f"Wins        : {wins}")
    print(f"Losses      : {losses}")
    print(f"Winrate     : {winrate*100:.2f}%")
    print(f"Avg R       : {avg_R:.3f}")
    print(f"Median R    : {med_R:.3f}")
    print(f"Best R      : {best_R:.3f}")
    print(f"Worst R     : {worst_R:.3f}")
    print(f"Max DD (R)  : {max_dd:.3f}")
    print()

    by_side = trades.groupby("side")["R"].agg(["count", "mean", "median"])
    print("By side (R stats):")
    print(by_side)
    print()

    by_reason = trades.groupby("exit_reason")["R"].agg(["count", "mean"])
    print("By exit reason:")
    print(by_reason)
    print()

    # Save trades to CSV for deeper analysis
    out_path = f"backtest_smc_{SYMBOL_FUT}_{TIMEFRAME}.csv"
    trades_sorted.to_csv(out_path, index=False)
    print(f"Saved detailed trades -> {out_path}")


def main():
    print("Building dataframe with price + OI + funding + SMC + ML bias...")
    df = build_full_df()
    print(f"Dataframe length: {len(df)} rows")

    # Small debug on ML bias distribution
    print("\nML bias stats:")
    print(df["ml_bias"].describe())
    n_strong = (df["ml_bias"].abs() >= ML_BIAS_TH).sum()
    print(f"Bars with |ml_bias| >= {ML_BIAS_TH}: {n_strong}\n")

    print("Simulating trades with SMC-based SL/TP...")
    trades = simulate_trades(df)
    print(f"Generated {len(trades)} trades\n")

    summarize_backtest(trades)


if __name__ == "__main__":
    main()
