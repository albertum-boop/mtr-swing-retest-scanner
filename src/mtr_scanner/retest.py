from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .market_data import adjusted_prices


def classify_grade(
    *,
    sma200_slope_percentile: float,
    pullback_from_peak_atr: float,
    event_body_atr: float,
    event_body_return: float,
    close_location: float,
    config: StrategyConfig | None = None,
) -> str:
    cfg = config or StrategyConfig()
    a_plus = (
        sma200_slope_percentile >= cfg.a_plus_min_sma200_slope_percentile
        and pullback_from_peak_atr >= cfg.a_plus_min_pullback_from_peak_atr
        and event_body_atr >= cfg.a_plus_min_bull_body_atr
        and event_body_return > 0
    )
    if a_plus:
        return "A+"
    return "A" if close_location >= cfg.a_min_close_location else "B"


def _outcomes(data: pd.DataFrame, event_index: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "entry_date": None,
        "entry_open": None,
        "r5": None,
        "mfe5": None,
        "mae5": None,
        "r10": None,
        "mfe10": None,
        "mae10": None,
    }
    entry_index = event_index + 1
    if entry_index >= len(data):
        return result
    entry = float(data["AdjOpen"].iloc[entry_index])
    result["entry_date"] = data.index[entry_index].date().isoformat()
    result["entry_open"] = entry
    for horizon in (5, 10):
        last_index = entry_index + horizon - 1
        if last_index >= len(data):
            continue
        path = data.iloc[entry_index : last_index + 1]
        result[f"r{horizon}"] = float(data["AdjClose"].iloc[last_index] / entry - 1)
        result[f"mfe{horizon}"] = float(path["AdjHigh"].max() / entry - 1)
        result[f"mae{horizon}"] = float(path["AdjLow"].min() / entry - 1)
    return result


def scan_candidate(
    candidate: dict[str, Any],
    raw_prices: pd.DataFrame,
    cutoff: pd.Timestamp | None = None,
    config: StrategyConfig | None = None,
) -> dict[str, Any]:
    """Evaluate the first contact after an intervening expansion.

    This is the historically audited rule. If that first contact fails any
    base condition, the candidate is rejected; a later touch cannot revive it.
    """

    cfg = config or StrategyConfig()
    ticker = str(candidate["ticker"])
    data = adjusted_prices(raw_prices, ticker)
    if cutoff is not None:
        data = data.loc[data.index <= pd.Timestamp(cutoff).normalize()]
    formation_date = pd.Timestamp(candidate["formation_date"]).normalize()
    positions = np.flatnonzero(data.index == formation_date)
    if len(positions) != 1:
        return {"ticker": ticker, "status": "missing_formation", "signal": None}
    i = int(positions[0])
    level = float(candidate["formation_close"])
    atr = float(candidate["atr_abs20"])
    prior_volume = float(candidate["prior_adj_volume20"])
    if not np.isfinite([level, atr, prior_volume]).all() or atr <= 0 or prior_volume <= 0:
        return {"ticker": ticker, "status": "invalid_formation", "signal": None}

    future_positions = list(range(i + 1, min(i + cfg.last_retest_day, len(data) - 1) + 1))
    if not future_positions:
        return {"ticker": ticker, "status": "waiting", "signal": None}
    expansion_seen = False
    expansion_peak = -np.inf
    rejection_reasons: list[dict[str, Any]] = []

    for j in future_positions:
        day = j - i
        row = data.iloc[j]
        if expansion_seen and day >= cfg.first_retest_day:
            event_range = float(row["AdjHigh"] - row["AdjLow"])
            close_location = (
                float((row["AdjClose"] - row["AdjLow"]) / event_range)
                if event_range > 0
                else np.nan
            )
            close_extension = float((row["AdjClose"] - level) / atr)
            volume_ratio = float(row["AdjVolume"] / prior_volume)
            conditions = {
                "contact": bool(
                    row["AdjHigh"] >= level - cfg.contact_band_atr * atr
                    and row["AdjLow"] <= level + cfg.contact_band_atr * atr
                ),
                "hold": bool(row["AdjClose"] >= level),
                "strong_close": bool(
                    np.isfinite(close_location) and close_location >= cfg.min_close_location
                ),
                "not_extended": bool(close_extension <= cfg.max_close_extension_atr),
                "volume_contraction": bool(volume_ratio < cfg.max_event_volume_ratio),
            }
            if all(conditions.values()):
                event_body_atr = float(abs(row["AdjClose"] - row["AdjOpen"]) / atr)
                event_body_return = float(row["AdjClose"] / row["AdjOpen"] - 1)
                pullback_atr = float((row["AdjClose"] - expansion_peak) / atr)
                grade = classify_grade(
                    sma200_slope_percentile=float(candidate["sma200_slope20_pct"]),
                    pullback_from_peak_atr=pullback_atr,
                    event_body_atr=event_body_atr,
                    event_body_return=event_body_return,
                    close_location=close_location,
                    config=cfg,
                )
                event_date = data.index[j].date().isoformat()
                signal = {
                    "signal_id": f"{cfg.method_version}:{ticker}:{event_date}",
                    "method_version": cfg.method_version,
                    "grade": grade,
                    "ticker": ticker,
                    "formation_date": formation_date.date().isoformat(),
                    "event_date": event_date,
                    "event_day": day,
                    "formation_close": level,
                    "atr_abs20": atr,
                    "adv20": float(candidate["adv20"]),
                    "universe_momentum_percentile": float(candidate["rank_pct"]),
                    "swing_score": float(candidate["swing_score"]),
                    "swing_rank_percentile": float(candidate["swing_rank_pct"]),
                    "momentum_percentile_d10": float(candidate["mom12_1_pct"]),
                    "atr_percentile_d10": float(candidate["atr_pct20_pct"]),
                    "return_volume_percentile_d10": float(candidate["return_volume_corr20_pct"]),
                    "sma200_slope_percentile_d10": float(candidate["sma200_slope20_pct"]),
                    "expansion_peak_atr": float((expansion_peak - level) / atr),
                    "pullback_from_peak_atr": pullback_atr,
                    "close_vs_level_atr": close_extension,
                    "close_location": close_location,
                    "event_volume_ratio": volume_ratio,
                    "event_volume_change": volume_ratio - 1,
                    "event_body_atr": event_body_atr,
                    "event_body_return": event_body_return,
                    "event_open": float(row["AdjOpen"]),
                    "event_high": float(row["AdjHigh"]),
                    "event_low": float(row["AdjLow"]),
                    "event_close": float(row["AdjClose"]),
                    "entry_rule": "Apertura ajustada de la siguiente sesión",
                }
                signal.update(_outcomes(data, j))
                return {
                    "ticker": ticker,
                    "status": "signal",
                    "signal": signal,
                    "rejections_before_signal": rejection_reasons,
                }
            if conditions["contact"]:
                rejection = {
                    "date": data.index[j].date().isoformat(),
                    "day": day,
                    "failed": [key for key, value in conditions.items() if not value],
                }
                return {
                    "ticker": ticker,
                    "status": "rejected_first_contact",
                    "signal": None,
                    "complete_days": day,
                    "rejections": [rejection],
                }
        expansion_peak = max(expansion_peak, float(row["AdjHigh"]))
        if row["AdjHigh"] >= level + cfg.expansion_atr * atr:
            expansion_seen = True

    complete_days = len(future_positions)
    if complete_days >= cfg.last_retest_day:
        status = "expired"
    elif expansion_seen:
        status = "expanded_waiting_retest"
    else:
        status = "waiting_expansion"
    return {
        "ticker": ticker,
        "status": status,
        "signal": None,
        "complete_days": complete_days,
        "rejections": rejection_reasons,
    }
