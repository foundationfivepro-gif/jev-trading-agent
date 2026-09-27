"""Daily candles from Coinbase's public API (no key needed), cached as CSV.

Binance is not reachable from the US, so Coinbase is the default source.
"""

import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

API = "https://api.exchange.coinbase.com/products/{symbol}/candles?granularity=86400&start={start}&end={end}"
MAX_BARS_PER_REQUEST = 300
DEFAULT_CACHE = Path("data_cache")
COLUMNS = ["open", "high", "low", "close", "volume"]


def _fetch_window(symbol: str, start: datetime, end: datetime) -> list[list[float]]:
    url = API.format(symbol=symbol, start=start.isoformat(), end=end.isoformat())
    req = urllib.request.Request(url, headers={"User-Agent": "jev-trading-agent"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    return []


def fetch_daily(symbol: str, start: str = "2017-01-01") -> pd.DataFrame:
    """Download completed daily candles from `start` up to yesterday (UTC)."""
    cursor = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows: list[list[float]] = []
    while cursor < today:
        window_end = min(cursor + timedelta(days=MAX_BARS_PER_REQUEST - 1), today - timedelta(days=1))
        rows.extend(_fetch_window(symbol, cursor, window_end))
        cursor = window_end + timedelta(days=1)
        time.sleep(0.2)  # stay well under the public rate limit
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    # Coinbase rows are [time, low, high, open, close, volume].
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    df["date"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None)
    df = df.drop_duplicates("date").set_index("date").sort_index()
    df = df[df.index < pd.Timestamp(today.replace(tzinfo=None))]  # drop the unfinished bar
    return df[COLUMNS].astype(float)


def load(symbol: str, cache_dir: Path = DEFAULT_CACHE, refresh: bool = False) -> pd.DataFrame:
    """Load candles from cache, downloading only the days that are missing."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{symbol}.csv"
    if path.exists() and not refresh:
        cached = pd.read_csv(path, index_col="date", parse_dates=True)
        yesterday = pd.Timestamp(datetime.now(timezone.utc).date()) - pd.Timedelta(days=1)
        if cached.empty or cached.index[-1] >= yesterday:
            return cached
        fresh = fetch_daily(symbol, start=(cached.index[-1] + pd.Timedelta(days=1)).date().isoformat())
        df = pd.concat([cached, fresh])
        df = df[~df.index.duplicated(keep="last")].sort_index()
    else:
        df = fetch_daily(symbol)
    df.to_csv(path, index_label="date")
    return df


def load_universe(symbols, cache_dir: Path = DEFAULT_CACHE, refresh: bool = False) -> dict[str, pd.DataFrame]:
    return {s: load(s, cache_dir, refresh) for s in symbols}
