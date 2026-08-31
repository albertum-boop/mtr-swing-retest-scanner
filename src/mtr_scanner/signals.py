from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from .alerts import GRADE_ORDER
from .lm2 import LM2_METHOD_VERSION
from .market_calendar import session_ordinals
from .weekly import MULTITEMPORAL_METHOD_VERSION, WEEKLY_METHOD_VERSION

SOURCE_ORDER = {"monthly": 0, "lm2": 1, "weekly": 2}
SOURCE_METHODS = {
    "monthly": "MTR-Swing-Retest-v1.0",
    "lm2": LM2_METHOD_VERSION,
    "weekly": WEEKLY_METHOD_VERSION,
}
SNAPSHOT_FIELDS = [
    "formation_date",
    "formation_close",
    "atr_abs20",
    "adv20",
    "universe_momentum_percentile",
    "swing_score",
    "swing_rank_percentile",
    "momentum_percentile_d10",
    "atr_percentile_d10",
    "return_volume_percentile_d10",
    "sma200_slope_percentile_d10",
    "formation_relative_volume5_20",
    "weekly_quality_points",
    "weekly_quality_checks",
    "weekly_formation_volume_confirmation",
    "lm2_quality_points",
    "lm2_quality_checks",
    "formation_gap",
    "formation_atr_percentile_d10",
    "formation_sma200_slope20",
    "close_vs_level_atr",
    "close_location",
    "event_volume_ratio",
]
DYNAMIC_FIELDS = [
    "entry_date",
    "entry_open",
    "r5",
    "mfe5",
    "mae5",
    "r10",
    "mfe10",
    "mae10",
]


def signal_key(signal: dict[str, Any]) -> tuple[str, str]:
    """An event is known at its close, before the next-session entry exists."""

    return str(signal["ticker"]), str(signal["event_date"])


def _source_snapshot(signal: dict[str, Any]) -> dict[str, Any]:
    return {field: signal.get(field) for field in SNAPSHOT_FIELDS if field in signal}


def annotate_signal(signal: dict[str, Any], source: str) -> dict[str, Any]:
    if source not in SOURCE_ORDER:
        raise ValueError(f"Fuente de señal desconocida: {source}")
    result = dict(signal)
    source_grade = str(result["grade"])
    source_method = SOURCE_METHODS[source]
    if source in {"weekly", "lm2"}:
        result["signal_id"] = (
            f"{source_method}:{result['ticker']}:{result['event_date']}"
        )
    result.update(
        method_version=MULTITEMPORAL_METHOD_VERSION,
        source=source,
        signal_sources=[source],
        is_confluence=False,
        monthly_grade=source_grade if source == "monthly" else None,
        lm2_grade=source_grade if source == "lm2" else None,
        weekly_grade=source_grade if source == "weekly" else None,
        source_grades={source: source_grade},
        formation_dates={source: result.get("formation_date")},
        source_method_versions={source: source_method},
        source_signal_ids={source: result["signal_id"]},
        source_details={source: _source_snapshot(result)},
    )
    return result


def normalize_signal(signal: dict[str, Any]) -> dict[str, Any]:
    sources = signal.get("signal_sources")
    if not sources:
        source = str(signal.get("source") or "monthly")
        if "+" not in source:
            return annotate_signal(signal, source)
    result = dict(signal)
    result["signal_sources"] = sorted(
        result.get("signal_sources") or str(result["source"]).split("+"),
        key=SOURCE_ORDER.get,
    )
    result["source"] = "+".join(result["signal_sources"])
    result["is_confluence"] = len(result["signal_sources"]) > 1
    result["method_version"] = MULTITEMPORAL_METHOD_VERSION
    return result


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _master_grade(source_grades: dict[str, str]) -> str:
    return min(source_grades.values(), key=lambda grade: GRADE_ORDER.get(grade, 9))


def merge_signal_group(records: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_signal(record) for record in records]
    monthly_records = [
        record for record in normalized if "monthly" in record["signal_sources"]
    ]
    primary = dict((monthly_records or normalized)[-1])

    source_grades: dict[str, str] = {}
    formation_dates: dict[str, str | None] = {}
    method_versions: dict[str, str] = {}
    signal_ids: dict[str, str] = {}
    source_details: dict[str, dict[str, Any]] = {}
    for record in normalized:
        source_grades.update(record.get("source_grades") or {})
        formation_dates.update(record.get("formation_dates") or {})
        method_versions.update(record.get("source_method_versions") or {})
        signal_ids.update(record.get("source_signal_ids") or {})
        source_details.update(record.get("source_details") or {})
        for field in DYNAMIC_FIELDS:
            if _present(record.get(field)):
                primary[field] = record[field]

    sources = sorted(source_grades, key=SOURCE_ORDER.get)
    grade = _master_grade(source_grades)
    primary.update(
        method_version=MULTITEMPORAL_METHOD_VERSION,
        source="+".join(sources),
        signal_sources=sources,
        is_confluence=len(sources) > 1,
        grade=grade,
        monthly_grade=source_grades.get("monthly"),
        lm2_grade=source_grades.get("lm2"),
        weekly_grade=source_grades.get("weekly"),
        source_grades=source_grades,
        formation_dates=formation_dates,
        source_method_versions=method_versions,
        source_signal_ids=signal_ids,
        source_details=source_details,
    )
    if "monthly" in signal_ids:
        primary["signal_id"] = signal_ids["monthly"]
        primary["formation_date"] = formation_dates.get("monthly")
    elif "lm2" in signal_ids:
        primary["signal_id"] = signal_ids["lm2"]
        primary["formation_date"] = formation_dates.get("lm2")
    elif "weekly" in signal_ids:
        primary["signal_id"] = signal_ids["weekly"]
        primary["formation_date"] = formation_dates.get("weekly")
    return primary


def merge_signal_records(signals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for signal in signals:
        grouped.setdefault(signal_key(signal), []).append(signal)
    return [merge_signal_group(records) for records in grouped.values()]


def apply_signal_cooldown(
    signals: Iterable[dict[str, Any]],
    *,
    cooldown_sessions: int = 10,
) -> list[dict[str, Any]]:
    """Mark later same-ticker events as non-actionable while preserving every record.

    Exact-event confluence is merged first. The earliest actionable event owns the
    cooldown; a suppressed event never extends it.
    """

    merged = merge_signal_records(signals)
    ordinals = session_ordinals(
        [pd.Timestamp(signal["event_date"]) for signal in merged]
    )
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for signal in merged:
        by_ticker.setdefault(str(signal["ticker"]), []).append(signal)

    result: list[dict[str, Any]] = []
    for records in by_ticker.values():
        records.sort(key=lambda row: (str(row["event_date"]), str(row["signal_id"])))
        last_actionable: dict[str, Any] | None = None
        for original in records:
            signal = dict(original)
            signal["cooldown_sessions"] = cooldown_sessions
            signal["suppressed_by_cooldown"] = None
            signal["actionable"] = bool(signal.get("actionable", True))
            if last_actionable is not None:
                gap = (
                    ordinals[str(signal["event_date"])]
                    - ordinals[str(last_actionable["event_date"])]
                )
                if gap <= cooldown_sessions:
                    signal["actionable"] = False
                    signal["suppressed_by_cooldown"] = last_actionable["signal_id"]
                    signal["cooldown_gap_sessions"] = gap
            if signal["actionable"]:
                last_actionable = signal
            result.append(signal)
    return result
