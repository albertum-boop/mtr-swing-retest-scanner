from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .alerts import GRADE_ORDER
from .weekly import MULTITEMPORAL_METHOD_VERSION, WEEKLY_METHOD_VERSION

SOURCE_ORDER = {"monthly": 0, "weekly": 1}
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
    source_method = (
        "MTR-Swing-Retest-v1.0" if source == "monthly" else WEEKLY_METHOD_VERSION
    )
    if source == "weekly":
        result["signal_id"] = (
            f"{WEEKLY_METHOD_VERSION}:{result['ticker']}:{result['event_date']}"
        )
    result.update(
        method_version=MULTITEMPORAL_METHOD_VERSION,
        source=source,
        signal_sources=[source],
        is_confluence=False,
        monthly_grade=source_grade if source == "monthly" else None,
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
    elif "weekly" in signal_ids:
        primary["signal_id"] = signal_ids["weekly"]
        primary["formation_date"] = formation_dates.get("weekly")
    return primary


def merge_signal_records(signals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for signal in signals:
        grouped.setdefault(signal_key(signal), []).append(signal)
    return [merge_signal_group(records) for records in grouped.values()]
