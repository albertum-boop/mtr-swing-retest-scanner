from __future__ import annotations

import time
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


def validate_raw_prices(frame: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    data = frame.copy()
    if "Date" in data.columns:
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
        data = data.set_index("Date")
    data.index = pd.to_datetime(data.index, errors="coerce")
    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_localize(None)
    missing = set(REQUIRED_COLUMNS) - set(data.columns)
    if missing:
        raise ValueError(f"{ticker}: faltan columnas {sorted(missing)}")
    data = data[REQUIRED_COLUMNS].apply(pd.to_numeric, errors="coerce")
    data = data.loc[~data.index.isna()].dropna().sort_index()
    data = data.loc[~data.index.duplicated(keep="last")]
    invalid = (
        (data[["Open", "High", "Low", "Close", "Adj Close"]] <= 0).any(axis=1)
        | (data["Volume"] < 0)
        | (data["High"] < data[["Open", "Close", "Low"]].max(axis=1))
        | (data["Low"] > data[["Open", "Close", "High"]].min(axis=1))
    )
    data = data.loc[~invalid]
    if data.empty:
        raise ValueError(f"{ticker}: OHLCV vacío después de validar")
    return data


def adjusted_prices(frame: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    data = validate_raw_prices(frame, ticker)
    factor = (data["Adj Close"] / data["Close"]).replace([np.inf, -np.inf, 0], np.nan)
    data = data.loc[factor.notna()].copy()
    factor = factor.loc[data.index]
    data["AdjOpen"] = data["Open"] * factor
    data["AdjHigh"] = data["High"] * factor
    data["AdjLow"] = data["Low"] * factor
    data["AdjClose"] = data["Adj Close"]
    data["AdjVolume"] = data["Volume"] / factor
    return data


def load_price_directory(
    directory: Path,
    tickers: Iterable[str],
    *,
    start: pd.Timestamp | None = None,
    cutoff: pd.Timestamp | None = None,
) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        path = directory / f"{ticker}.csv"
        if not path.exists():
            continue
        data = validate_raw_prices(pd.read_csv(path), ticker)
        if start is not None:
            data = data.loc[data.index >= pd.Timestamp(start).normalize()]
        if cutoff is not None:
            data = data.loc[data.index <= pd.Timestamp(cutoff).normalize()]
        if not data.empty:
            result[ticker] = data
    return result


def _split_download(downloaded: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    if len(tickers) == 1 and not isinstance(downloaded.columns, pd.MultiIndex):
        result[tickers[0]] = downloaded
        return result
    if not isinstance(downloaded.columns, pd.MultiIndex):
        return result
    level0 = set(map(str, downloaded.columns.get_level_values(0)))
    level1 = set(map(str, downloaded.columns.get_level_values(1)))
    for ticker in tickers:
        if ticker in level0:
            result[ticker] = downloaded[ticker]
        elif ticker in level1:
            result[ticker] = downloaded.xs(ticker, axis=1, level=1)
    return result


def download_histories(
    tickers: Iterable[str],
    *,
    start: pd.Timestamp,
    cutoff: pd.Timestamp,
    batch_size: int = 80,
    retries: int = 3,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Download without Yahoo ``end`` and crop complete sessions locally."""

    symbols = sorted(dict.fromkeys(str(t).upper() for t in tickers))
    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for offset in range(0, len(symbols), batch_size):
        batch = symbols[offset : offset + batch_size]
        last_error = ""
        pieces: dict[str, pd.DataFrame] = {}
        for attempt in range(1, retries + 1):
            try:
                downloaded = yf.download(
                    tickers=batch,
                    start=pd.Timestamp(start).date().isoformat(),
                    interval="1d",
                    auto_adjust=False,
                    actions=False,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                    timeout=30,
                )
                pieces = _split_download(downloaded, batch)
                if pieces:
                    break
                last_error = "Yahoo devolvió un lote vacío"
            except Exception as exc:  # noqa: BLE001 - Yahoo raises release-specific exceptions.
                last_error = str(exc)
            if attempt < retries:
                time.sleep(2 ** (attempt - 1))
        for ticker in batch:
            raw = pieces.get(ticker)
            if raw is None:
                errors[ticker] = last_error or "Ticker ausente en la descarga"
                continue
            try:
                valid = validate_raw_prices(raw, ticker)
                valid = valid.loc[valid.index <= pd.Timestamp(cutoff).normalize()]
                if valid.empty:
                    raise ValueError("sin sesiones completas hasta el corte")
                frames[ticker] = valid
            except (KeyError, TypeError, ValueError) as exc:
                errors[ticker] = str(exc)
    return frames, errors
