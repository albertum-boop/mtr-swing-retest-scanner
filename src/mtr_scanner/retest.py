from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .market_data import adjusted_prices


def candidate_monitor(
    candidate: dict[str, Any], config: StrategyConfig | None = None
) -> dict[str, Any]:
    """Build the immutable formation levels shown by the operational monitor."""

    cfg = config or StrategyConfig()
    level = float(candidate["formation_close"])
    atr = float(candidate["atr_abs20"])
    prior_volume = float(candidate["prior_adj_volume20"])
    return {
        "ticker": str(candidate["ticker"]),
        "candidate_rank": candidate.get("candidate_rank"),
        "formation_date": str(candidate["formation_date"]),
        "swing_score": float(candidate["swing_score"]),
        "swing_rank_percentile": float(candidate["swing_rank_pct"]),
        "universe_momentum_percentile": float(candidate["rank_pct"]),
        "sma200_slope_percentile_d10": float(candidate["sma200_slope20_pct"]),
        "formation_close": level,
        "atr_abs20": atr,
        "prior_adj_volume20": prior_volume,
        "expansion_threshold": level + cfg.expansion_atr * atr,
        "contact_band_low": level - cfg.contact_band_atr * atr,
        "contact_band_high": level + cfg.contact_band_atr * atr,
        "max_valid_close": level + cfg.max_close_extension_atr * atr,
        "max_event_volume": cfg.max_event_volume_ratio * prior_volume,
        "status": "waiting",
        "complete_days": 0,
        "sessions_remaining": cfg.last_retest_day,
        "expansion_seen": False,
        "expansion_date": None,
        "expansion_peak": None,
        "expansion_peak_atr": None,
        "first_contact_date": None,
        "latest_session": None,
        "checks": None,
        "failed_conditions": [],
        "grade": None,
        "event_date": None,
        "entry_date": None,
        "entry_open": None,
        "next_step": "Esperando las sesiones posteriores a la formación",
    }


def _session_snapshot(
    *,
    row: pd.Series,
    date: pd.Timestamp,
    day: int,
    level: float,
    atr: float,
    prior_volume: float,
    expansion_seen_before: bool,
    config: StrategyConfig,
) -> dict[str, Any]:
    event_range = float(row["AdjHigh"] - row["AdjLow"])
    close_location = (
        float((row["AdjClose"] - row["AdjLow"]) / event_range)
        if event_range > 0
        else None
    )
    close_extension = float((row["AdjClose"] - level) / atr)
    volume_ratio = float(row["AdjVolume"] / prior_volume)
    contact = bool(
        row["AdjHigh"] >= level - config.contact_band_atr * atr
        and row["AdjLow"] <= level + config.contact_band_atr * atr
    )
    checks = {
        "contact": contact,
        "hold": bool(row["AdjClose"] >= level),
        "strong_close": bool(
            close_location is not None
            and np.isfinite(close_location)
            and close_location >= config.min_close_location
        ),
        "not_extended": bool(close_extension <= config.max_close_extension_atr),
        "volume_contraction": bool(volume_ratio < config.max_event_volume_ratio),
    }
    return {
        "date": pd.Timestamp(date).date().isoformat(),
        "day": day,
        "open": float(row["AdjOpen"]),
        "high": float(row["AdjHigh"]),
        "low": float(row["AdjLow"]),
        "close": float(row["AdjClose"]),
        "volume": float(row["AdjVolume"]),
        "close_location": close_location,
        "close_vs_level_atr": close_extension,
        "volume_ratio": volume_ratio,
        "expansion_seen_before": expansion_seen_before,
        "expansion_reached_today": bool(
            row["AdjHigh"] >= level + config.expansion_atr * atr
        ),
        "eligible_retest_day": bool(
            expansion_seen_before
            and config.first_retest_day <= day <= config.last_retest_day
        ),
        "checks": checks,
    }


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
    monitor = candidate_monitor(candidate, cfg)
    data = adjusted_prices(raw_prices, ticker)
    if cutoff is not None:
        data = data.loc[data.index <= pd.Timestamp(cutoff).normalize()]
    formation_date = pd.Timestamp(candidate["formation_date"]).normalize()
    positions = np.flatnonzero(data.index == formation_date)
    if len(positions) != 1:
        monitor.update(
            status="missing_formation",
            next_step="No se puede evaluar: falta la sesión de formación",
        )
        return {
            "ticker": ticker,
            "status": "missing_formation",
            "signal": None,
            "monitor": monitor,
        }
    i = int(positions[0])
    level = float(candidate["formation_close"])
    atr = float(candidate["atr_abs20"])
    prior_volume = float(candidate["prior_adj_volume20"])
    if not np.isfinite([level, atr, prior_volume]).all() or atr <= 0 or prior_volume <= 0:
        monitor.update(
            status="invalid_formation",
            next_step="No se puede evaluar: niveles de formación inválidos",
        )
        return {
            "ticker": ticker,
            "status": "invalid_formation",
            "signal": None,
            "monitor": monitor,
        }

    future_positions = list(range(i + 1, min(i + cfg.last_retest_day, len(data) - 1) + 1))
    if not future_positions:
        return {"ticker": ticker, "status": "waiting", "signal": None, "monitor": monitor}
    expansion_seen = False
    expansion_peak = -np.inf
    expansion_date: str | None = None
    latest_session: dict[str, Any] | None = None
    rejection_reasons: list[dict[str, Any]] = []

    def complete_monitor(status: str, complete_days: int, **updates: Any) -> dict[str, Any]:
        peak = float(expansion_peak) if np.isfinite(expansion_peak) and expansion_seen else None
        next_steps = {
            "waiting": "Esperando las sesiones posteriores a la formación",
            "waiting_expansion": "Falta alcanzar el nivel mínimo de expansión",
            "expanded_waiting_retest": "Expansión confirmada; falta el primer contacto válido",
            "signal": "Señal confirmada; entrada en la próxima apertura",
            "rejected_first_contact": "Primer contacto rechazado; no puede reactivarse este ciclo",
            "expired": "Ventana de días 2–5 cerrada sin señal",
        }
        if status == "expired":
            next_steps["expired"] = (
                "Ventana cerrada: no hubo contacto con la banda"
                if expansion_seen
                else "Ventana cerrada: no hubo expansión"
            )
        terminal = status in {"signal", "rejected_first_contact", "expired"}
        result = {
            **monitor,
            "status": status,
            "complete_days": complete_days,
            "sessions_remaining": 0 if terminal else max(0, cfg.last_retest_day - complete_days),
            "expansion_seen": expansion_seen,
            "expansion_date": expansion_date,
            "expansion_peak": peak,
            "expansion_peak_atr": float((peak - level) / atr) if peak is not None else None,
            "latest_session": latest_session,
            "next_step": next_steps[status],
            **updates,
        }
        return result

    for j in future_positions:
        day = j - i
        row = data.iloc[j]
        latest_session = _session_snapshot(
            row=row,
            date=data.index[j],
            day=day,
            level=level,
            atr=atr,
            prior_volume=prior_volume,
            expansion_seen_before=expansion_seen,
            config=cfg,
        )
        if expansion_seen and day >= cfg.first_retest_day:
            close_location = latest_session["close_location"]
            close_extension = latest_session["close_vs_level_atr"]
            volume_ratio = latest_session["volume_ratio"]
            conditions = latest_session["checks"]
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
                signal_monitor = complete_monitor(
                    "signal",
                    day,
                    first_contact_date=event_date,
                    checks=conditions,
                    failed_conditions=[],
                    grade=grade,
                    event_date=event_date,
                    entry_date=signal["entry_date"],
                    entry_open=signal["entry_open"],
                )
                if signal["entry_date"] is not None:
                    signal_monitor["next_step"] = "Señal del ciclo; entrada de apertura ya registrada"
                return {
                    "ticker": ticker,
                    "status": "signal",
                    "signal": signal,
                    "rejections_before_signal": rejection_reasons,
                    "monitor": signal_monitor,
                }
            if conditions["contact"]:
                failed = [key for key, value in conditions.items() if not value]
                rejection = {
                    "date": data.index[j].date().isoformat(),
                    "day": day,
                    "failed": failed,
                }
                return {
                    "ticker": ticker,
                    "status": "rejected_first_contact",
                    "signal": None,
                    "complete_days": day,
                    "rejections": [rejection],
                    "monitor": complete_monitor(
                        "rejected_first_contact",
                        day,
                        first_contact_date=rejection["date"],
                        checks=conditions,
                        failed_conditions=failed,
                    ),
                }
        expansion_peak = max(expansion_peak, float(row["AdjHigh"]))
        if row["AdjHigh"] >= level + cfg.expansion_atr * atr:
            if not expansion_seen:
                expansion_date = data.index[j].date().isoformat()
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
        "monitor": complete_monitor(status, complete_days),
    }
