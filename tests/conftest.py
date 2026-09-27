import numpy as np
import pandas as pd
import pytest


def make_frame(closes, start="2020-01-01", spread=0.01, volume=1e9):
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range(start, periods=len(closes), freq="D")
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) * (1 + spread),
            "low": np.minimum(opens, closes) * (1 - spread),
            "close": closes,
            "volume": volume / closes,
        },
        index=idx,
    )


@pytest.fixture
def frame():
    return make_frame
