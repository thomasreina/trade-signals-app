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

# --------- ENV DEFAULTS (mirror your CLI setup) ---------

# Core market config
os.environ.setdefault("SYMBOL_SPOT", "BTC/USDT")
os.environ.setdefault("SYMBOL_FUT", "BTCUSDT")
os.environ.setdefault("OKX_UNDERLYING", "BTC-USDT")
os.environ.setdefault("TIMEFRAME", "1h")
os.environ.setdefault("CANDLES", "1000")
os.environ.setdefault("TZ_NAME", "Europe/Madrid")

# ML config
os.environ.setdefault("USE_ML", "true")
os.environ.setdefault("ML_BIAS_TH", "0.20")
os.environ.setdefault("ML_BIAS_HIGH_TH", "0.25")

# Score weights
os.environ.setdefault("W_SMC", "0.45")
os.environ.setdefault("W_RSI", "0.20")
os.environ.setdefault("W_OI", "0.20")
os.environ.setdefault("W_FUND", "0.15")

# Model path: use the model under /trade-signals/models
symbol_fut = os.getenv("SYMBOL_FUT", "BTCUSDT")
tf = os.getenv("TIMEFRAME", "1h")
model_path = os.path.join(PROJECT_ROOT, "models", f"rf_{symbol_fut}_{tf}.pkl")
os.environ.setdefault("MODEL_PATH", model_path)

# Where to save signals if the core script writes them
os.environ.setdefault("SAVE_SIGNALS_PATH", f"signals_{symbol_fut}_{tf}.csv")

# --------- Import the real analyzer from the project root ---------
from market_structure_analyzer import run_analyzer as _run_analyzer  # type: ignore  # noqa: E402


def run_analyzer() -> pd.DataFrame:
    """
    Thin wrapper used by the FastAPI backend.

    Delegates to the root-level `market_structure_analyzer.run_analyzer()`
    so we don't duplicate complex trading logic inside the backend package.
    """
    df: Any = _run_analyzer()
    if df is None:
        return pd.DataFrame()
    if not isinstance(df, pd.DataFrame):
        raise TypeError("run_analyzer() did not return a pandas DataFrame")
    return df
