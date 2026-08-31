from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .market_data import adjusted_prices

RAW_FEATURES = ["mom12_1", "atr_pct20", "return_volume_corr20", "sma200_slope20"]


def _formation_observation(
    ticker: str,
    raw: pd.DataFrame,
    formation_date: pd.Timestamp,
    config: StrategyConfig,
) -> dict[str, object] | None:
    data = adjusted_prices(raw, ticker)
    formation_date = pd.Timestamp(formation_date).normalize()
    matches = np.flatnonzero(data.index == formation_date)
    if len(matches) != 1:
        return None
    i = int(matches[0])
    if i < max(config.momentum_lookback_sessions, 220):
        return None
    close = data["AdjClose"]
    ret = close.pct_change(fill_method=None)
    log_volume = np.log1p(data["AdjVolume"])
    prev = close.shift(1)
    true_range = pd.concat(
        [
            data["AdjHigh"] - data["AdjLow"],
            (data["AdjHigh"] - prev).abs(),
            (data["AdjLow"] - prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_abs = true_range.rolling(config.atr_sessions, min_periods=config.atr_sessions).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    corr = ret.rolling(20, min_periods=20).corr(log_volume)
    raw_dollar_volume = data["Close"] * data["Volume"]
    adv20 = raw_dollar_volume.rolling(20, min_periods=20).mean()
    prior_adj_volume20 = data["AdjVolume"].rolling(20, min_periods=20).mean()
    prior_adj_volume5 = data["AdjVolume"].rolling(5, min_periods=5).mean()
    mom = (
        close.iloc[i - config.momentum_skip_sessions]
        / close.iloc[i - config.momentum_lookback_sessions]
        - 1
    )
    average_volume20 = float(prior_adj_volume20.iloc[i])
    relative_volume5_20 = (
        float(prior_adj_volume5.iloc[i] / average_volume20 - 1)
        if np.isfinite(average_volume20) and average_volume20 > 0
        else np.nan
    )
    values = {
        "ticker": ticker,
        "formation_date": formation_date,
        "formation_close_raw": float(data["Close"].iloc[i]),
        "formation_close": float(close.iloc[i]),
        "adv20": float(adv20.iloc[i]),
        "atr_abs20": float(atr_abs.iloc[i]),
        "atr_pct20": float(atr_abs.iloc[i] / close.iloc[i]),
        "prior_adj_volume20": average_volume20,
        "relative_volume5_20": relative_volume5_20,
        "mom12_1": float(mom),
        "return_volume_corr20": float(corr.iloc[i]),
        "sma200_slope20": float(sma200.iloc[i] / sma200.iloc[i - 20] - 1),
    }
    numeric = [
        values[key]
        for key in ["adv20", "atr_abs20", "relative_volume5_20", *RAW_FEATURES]
    ]
    if not all(np.isfinite(numeric)) or values["atr_abs20"] <= 0:
        return None
    return values


def build_ranked_candidates(
    prices: Mapping[str, pd.DataFrame],
    formation_date: pd.Timestamp,
    config: StrategyConfig | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    cfg = config or StrategyConfig()
    rows = [
        observation
        for ticker, raw in prices.items()
        if (observation := _formation_observation(ticker, raw, formation_date, cfg)) is not None
    ]
    panel = pd.DataFrame(rows)
    if panel.empty:
        return [], {"observed": 0, "eligible": 0, "d10": 0, "swing_top20": 0}
    eligible = panel.loc[
        panel["mom12_1"].notna()
        & panel["formation_close_raw"].ge(cfg.min_price)
        & panel["adv20"].ge(cfg.min_adv20_usd)
    ].copy()
    eligible["rank_pct"] = eligible["mom12_1"].rank(pct=True, method="average")
    d10 = eligible.loc[eligible["rank_pct"].gt(cfg.d10_rank_threshold)].copy()
    if d10.empty:
        return [], {
            "observed": len(panel), "eligible": len(eligible), "d10": 0, "swing_top20": 0
        }
    for feature in RAW_FEATURES:
        d10[f"{feature}_pct"] = d10[feature].rank(pct=True, method="average")
    d10["swing_score"] = (
        cfg.swing_atr_weight * d10["atr_pct20_pct"]
        + cfg.swing_momentum_weight * d10["mom12_1_pct"]
        + cfg.swing_return_volume_weight * d10["return_volume_corr20_pct"]
    )
    d10["swing_rank_pct"] = d10["swing_score"].rank(pct=True, method="average")
    selected = d10.loc[d10["swing_rank_pct"].gt(cfg.swing_rank_threshold)].copy()
    selected = selected.sort_values(["swing_score", "ticker"], ascending=[False, True])
    selected["candidate_rank"] = np.arange(1, len(selected) + 1)
    candidates = selected.to_dict(orient="records")
    for candidate in candidates:
        candidate["formation_date"] = pd.Timestamp(candidate["formation_date"]).date().isoformat()
        candidate["method_version"] = cfg.method_version
    stats = {
        "observed": len(panel),
        "eligible": len(eligible),
        "d10": len(d10),
        "swing_top20": len(selected),
        "coverage": float(len(panel) / max(len(prices), 1)),
    }
    return candidates, stats


def build_monthly_candidates(
    prices: Mapping[str, pd.DataFrame],
    formation_date: pd.Timestamp,
    config: StrategyConfig | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Backward-compatible name for the point-in-time ranking engine."""

    return build_ranked_candidates(prices, formation_date, config)
