import os
import sys
from typing import Any

import pandas as pd

# PROJECT_ROOT should be /Users/thomasreina/trade-signals
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --------- ENV DEFAULTS for backtest (mirror your CLI setup) ---------
os.environ.setdefault("SYMBOL_SPOT", "BTC/USDT")
os.environ.setdefault("SYMBOL_FUT", "BTCUSDT")
os.environ.setdefault("OKX_UNDERLYING", "BTC-USDT")
os.environ.setdefault("TIMEFRAME", "1h")
os.environ.setdefault("CANDLES", "1000")
os.environ.setdefault("TZ_NAME", "Europe/Madrid")

# Label / backtest params (you used these in CLI)
os.environ.setdefault("LBL_TP", "0.006")
os.environ.setdefault("LBL_SL", "0.005")
os.environ.setdefault("LBL_HZN", "8")

# ML settings
os.environ.setdefault("USE_ML", "true")
os.environ.setdefault("ML_BIAS_TH", "0.20")
os.environ.setdefault("ML_BIAS_HIGH_TH", "0.25")

symbol_fut = os.getenv("SYMBOL_FUT", "BTCUSDT")
tf = os.getenv("TIMEFRAME", "1h")
model_path = os.path.join(PROJECT_ROOT, "models", f"rf_{symbol_fut}_{tf}.pkl")
os.environ.setdefault("MODEL_PATH", model_path)

# --------- Import the real SMC backtest from the project root ---------
from backtest_smc_sl_tp import run_smc_backtest as _run_smc_backtest  # type: ignore  # noqa: E402


def run_smc_backtest() -> pd.DataFrame:
    """
    Thin wrapper for SMC+ML backtest used by the FastAPI backend.
    Delegates to root-level backtest_smc_sl_tp.run_smc_backtest().
    """
    trades: Any = _run_smc_backtest()
    if trades is None:
        return pd.DataFrame()
    if not isinstance(trades, pd.DataFrame):
        raise TypeError("run_smc_backtest() did not return a pandas DataFrame")
    return trades
