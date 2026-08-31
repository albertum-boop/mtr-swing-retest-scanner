from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

LM2_METHOD_VERSION = "MTR-LM2-v1.0"


@dataclass(frozen=True)
class LM2StrategyConfig:
    """Frozen grading parameters for the penultimate-session monthly branch."""

    method_version: str = LM2_METHOD_VERSION
    formation_gap_min: float = 0.0
    atr_percentile_min: float = 0.85
    sma200_slope20_min: float = 0.075

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def lm2_grade_details(
    candidate: dict[str, Any],
    config: LM2StrategyConfig | None = None,
) -> dict[str, Any]:
    cfg = config or LM2StrategyConfig()
    checks = {
        "non_negative_formation_gap": (
            float(candidate["formation_gap"]) >= cfg.formation_gap_min
        ),
        "high_atr_percentile": (
            float(candidate["atr_pct20_pct"]) >= cfg.atr_percentile_min
        ),
        "strong_sma200_slope": (
            float(candidate["sma200_slope20"]) >= cfg.sma200_slope20_min
        ),
    }
    quality_points = sum(checks.values())
    grade = "A+" if quality_points == 3 else "A" if quality_points == 2 else "B"
    return {
        "lm2_grade": grade,
        "lm2_quality_points": quality_points,
        "lm2_quality_checks": checks,
        "formation_gap": float(candidate["formation_gap"]),
        "formation_atr_percentile_d10": float(candidate["atr_pct20_pct"]),
        "formation_sma200_slope20": float(candidate["sma200_slope20"]),
    }


def apply_lm2_grade(
    result: dict[str, Any],
    candidate: dict[str, Any],
    config: LM2StrategyConfig | None = None,
) -> dict[str, Any]:
    """Apply LM2 quality; B is retained in the monitor but never published."""

    details = lm2_grade_details(candidate, config)
    monitor = dict(result["monitor"])
    monitor.update(details)
    signal = result.get("signal")
    if signal is None:
        return {**result, "monitor": monitor}
    graded_signal = dict(signal)
    graded_signal["base_retest_grade"] = graded_signal["grade"]
    graded_signal["grade"] = details["lm2_grade"]
    graded_signal.update(details)

    monitor["grade"] = details["lm2_grade"]
    if details["lm2_grade"] == "B":
        monitor.update(
            status="rejected_lm2_grade",
            sessions_remaining=0,
            next_step="Retest válido, pero calidad LM2 B; no genera entrada",
        )
        return {
            **result,
            "status": "rejected_lm2_grade",
            "signal": None,
            "rejected_signal": graded_signal,
            "monitor": monitor,
        }
    return {**result, "signal": graded_signal, "monitor": monitor}
