from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

WEEKLY_METHOD_VERSION = "MTR-Weekly-Cross-v2.0"
MULTITEMPORAL_METHOD_VERSION = "MTR-Multitemporal-v2.0"


@dataclass(frozen=True)
class WeeklyStrategyConfig:
    """Frozen parameters for the incremental weekly branch."""

    method_version: str = WEEKLY_METHOD_VERSION
    momentum_percentile_min: float = 0.75
    atr_percentile_max: float = 0.85
    swing_rank_min: float = 0.86
    close_extension_atr_max: float = 0.45
    formation_relative_volume_min: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def weekly_crossing_candidates(
    current_selected: list[dict[str, Any]],
    previous_selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only stocks selected now that were outside at the prior weekly close."""

    previous_tickers = {str(row["ticker"]) for row in previous_selected}
    crossings = [
        dict(row)
        for row in current_selected
        if str(row["ticker"]) not in previous_tickers
    ]
    for candidate in crossings:
        candidate["formation_frequency"] = "weekly"
        candidate["method_version"] = WEEKLY_METHOD_VERSION
    return crossings


def weekly_grade_details(
    candidate: dict[str, Any],
    signal: dict[str, Any],
    config: WeeklyStrategyConfig | None = None,
) -> dict[str, Any]:
    cfg = config or WeeklyStrategyConfig()
    checks = {
        "momentum": float(candidate["mom12_1_pct"]) >= cfg.momentum_percentile_min,
        "controlled_atr": float(candidate["atr_pct20_pct"]) <= cfg.atr_percentile_max,
        "swing_rank": float(candidate["swing_rank_pct"]) >= cfg.swing_rank_min,
        "retest_extension": (
            float(signal["close_vs_level_atr"]) <= cfg.close_extension_atr_max
        ),
    }
    quality_points = sum(checks.values())
    formation_relative_volume = float(candidate["relative_volume5_20"])
    volume_confirmation = formation_relative_volume >= cfg.formation_relative_volume_min
    if quality_points >= 3 and volume_confirmation:
        grade = "A+"
    elif quality_points == 2 or (quality_points >= 3 and not volume_confirmation):
        grade = "A"
    else:
        grade = "B"
    return {
        "weekly_grade": grade,
        "weekly_quality_points": quality_points,
        "weekly_quality_checks": checks,
        "weekly_formation_volume_confirmation": volume_confirmation,
        "formation_relative_volume5_20": formation_relative_volume,
    }


def apply_weekly_grade(
    result: dict[str, Any],
    candidate: dict[str, Any],
    config: WeeklyStrategyConfig | None = None,
) -> dict[str, Any]:
    """Apply the weekly grade and turn B into a terminal rejected monitor state."""

    signal = result.get("signal")
    if signal is None:
        return result
    details = weekly_grade_details(candidate, signal, config)
    graded_signal = dict(signal)
    graded_signal["base_retest_grade"] = graded_signal["grade"]
    graded_signal["grade"] = details["weekly_grade"]
    graded_signal.update(details)

    monitor = dict(result["monitor"])
    monitor.update(details)
    monitor["grade"] = details["weekly_grade"]
    if details["weekly_grade"] == "B":
        monitor.update(
            status="rejected_weekly_grade",
            sessions_remaining=0,
            next_step="Retest válido, pero calidad semanal B; no genera entrada",
        )
        return {
            **result,
            "status": "rejected_weekly_grade",
            "signal": None,
            "rejected_signal": graded_signal,
            "monitor": monitor,
        }
    return {**result, "signal": graded_signal, "monitor": monitor}
