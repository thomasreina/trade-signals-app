from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import List

from app.core.market_structure_analyzer import run_analyzer
from app.core.backtest_smc_sl_tp import run_smc_backtest

app = FastAPI(title="Trade Signals API")


class Signal(BaseModel):
    timestamp: datetime
    side: str
    close: float
    ml_bias: float
    ml_conviction: str
    sl: float
    tp1: float
    tp2: float
    reasons: str


class TradeBacktest(BaseModel):
    entry_time: datetime
    exit_time: datetime
    side: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    exit_price: float
    exit_reason: str
    R: float


@app.get("/signals/latest", response_model=List[Signal])
def get_latest_signals():
    try:
        df = run_analyzer()
    except Exception as e:
        print("Error in run_analyzer():", repr(e))
        raise HTTPException(status_code=500, detail=f"run_analyzer failed: {e}")

    if df is None or df.empty:
        return []

    # Don't assume 'timestamp' exists for sorting; just take the last 25 rows
    last = df.tail(25)

    results: List[Signal] = []
    for _, row in last.iterrows():
        # row is a pandas Series; use .get() with fallbacks
        ts = row.get("timestamp", datetime.utcnow())
        side = row.get("side", "")
        close = float(row.get("close", 0.0))
        ml_bias = float(row.get("ml_bias", 0.0))
        ml_conviction = str(row.get("ml_conviction", ""))
        sl = float(row.get("sl", 0.0))
        tp1 = float(row.get("tp1", 0.0))
        tp2 = float(row.get("tp2", 0.0))
        reasons = str(row.get("reasons", ""))

        results.append(
            Signal(
                timestamp=ts,
                side=side,
                close=close,
                ml_bias=ml_bias,
                ml_conviction=ml_conviction,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                reasons=reasons,
            )
        )

    return results


@app.get("/backtest/smc", response_model=List[TradeBacktest])
def get_smc_backtest():
    try:
        trades = run_smc_backtest()
    except Exception as e:
        print("Error in run_smc_backtest():", repr(e))
        raise HTTPException(status_code=500, detail=f"run_smc_backtest failed: {e}")

    if trades is None or trades.empty:
        return []

    return [
        TradeBacktest(
            entry_time=row.get("entry_time", datetime.utcnow()),
            exit_time=row.get("exit_time", datetime.utcnow()),
            side=row.get("side", ""),
            entry=float(row.get("entry", 0.0)),
            sl=float(row.get("sl", 0.0)),
            tp1=float(row.get("tp1", 0.0)),
            tp2=float(row.get("tp2", 0.0)),
            exit_price=float(row.get("exit_price", 0.0)),
            exit_reason=str(row.get("exit_reason", "")),
            R=float(row.get("R", 0.0)),
        )
        for _, row in trades.iterrows()
    ]

