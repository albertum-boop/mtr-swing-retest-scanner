from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mtr_scanner.alerts import GRADE_ORDER
from mtr_scanner.lm2 import LM2_METHOD_VERSION
from mtr_scanner.storage import write_json
from mtr_scanner.weekly import MULTITEMPORAL_METHOD_VERSION, WEEKLY_METHOD_VERSION

ROOT = Path(__file__).resolve().parents[1]
MONTHLY_METHOD_VERSION = "MTR-Swing-Retest-v2.0"
SOURCE_METHODS = {
    "monthly": MONTHLY_METHOD_VERSION,
    "lm2": LM2_METHOD_VERSION,
    "weekly": WEEKLY_METHOD_VERSION,
}
SOURCE_ORDER = {"monthly": 0, "lm2": 1, "weekly": 2}
METRICS = ["r5", "mfe5", "mae5", "r10", "mfe10", "mae10"]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _clean(value: Any) -> Any:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _source_grades(text: str) -> dict[str, str]:
    return {
        source.strip(): grade.strip()
        for item in str(text).split(";")
        for source, grade in [item.split("=", 1)]
    }


def _source_list(text: str) -> list[str]:
    return sorted(str(text).split("+"), key=SOURCE_ORDER.get)


def _source_detail(row: pd.Series) -> dict[str, Any]:
    return {
        "formation_date": row["formation_date"],
        "formation_close": _clean(row["formation_close"]),
        "atr_abs20": _clean(row["atr_abs20"]),
        "universe_momentum_percentile": _clean(row["rank_pct"]),
        "swing_score": _clean(row["swing_score"]),
        "swing_rank_percentile": _clean(row["swing_rank_pct"]),
        "momentum_percentile_d10": _clean(row["mom12_1_pct"]),
        "atr_percentile_d10": _clean(row["atr_pct20_pct"]),
        "return_volume_percentile_d10": _clean(row["return_volume_corr20_pct"]),
        "sma200_slope_percentile_d10": _clean(row["sma200_slope20_pct"]),
        "close_vs_level_atr": _clean(row["close_vs_level_atr"]),
        "close_location": _clean(row["close_location"]),
        "event_volume_ratio": _clean(row["event_volume_ratio"]),
    }


def _historical_lookup(history: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(signal["ticker"]), str(signal["event_date"])): signal
        for signal in history
    }


def _reference_signal(
    row: pd.Series,
    observations: dict[tuple[str, str, str], pd.Series],
    prior: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    sources = _source_list(row["sources"])
    source_grades = _source_grades(row["source_grades"])
    primary = next(source for source in ["monthly", "lm2", "weekly"] if source in sources)
    formation_dates = {
        source: row[f"{source}_formation_date"]
        for source in sources
        if pd.notna(row[f"{source}_formation_date"])
    }
    source_details = {
        source: _source_detail(observations[(source, row["ticker"], row["event_date"])])
        for source in sources
    }
    old = prior.get((str(row["ticker"]), str(row["event_date"])), {})
    expansion_peak_atr = float(row["close_vs_level_atr"] - row["pullback_from_peak_atr"])
    actionable = bool(row["actionable"])
    signal_id = f"{MULTITEMPORAL_METHOD_VERSION}:{row['ticker']}:{row['event_date']}"
    suppressed_date = _clean(row["suppressed_by_event"])
    signal = {
        "signal_id": signal_id,
        "reference_id": row["appendix_ref"],
        "reference_complete": True,
        "method_version": MULTITEMPORAL_METHOD_VERSION,
        "grade": row["master_grade"],
        "base_retest_grade": _clean(row[f"{primary}_base_grade"]),
        "ticker": row["ticker"],
        "formation_date": formation_dates[primary],
        "event_date": row["event_date"],
        "event_day": int(row["event_day"]),
        "formation_close": float(row["formation_close"]),
        "atr_abs20": float(row["atr_abs20"]),
        "adv20": old.get("adv20"),
        "universe_momentum_percentile": float(row["rank_pct"]),
        "swing_score": float(row["swing_score"]),
        "swing_rank_percentile": float(row["swing_rank_pct"]),
        "momentum_percentile_d10": float(row["mom12_1_pct"]),
        "atr_percentile_d10": float(row["atr_pct20_pct"]),
        "return_volume_percentile_d10": float(row["return_volume_corr20_pct"]),
        "sma200_slope_percentile_d10": float(row["sma200_slope20_pct"]),
        "expansion_peak_atr": expansion_peak_atr,
        "pullback_from_peak_atr": float(row["pullback_from_peak_atr"]),
        "close_vs_level_atr": float(row["close_vs_level_atr"]),
        "close_location": float(row["close_location"]),
        "event_volume_ratio": float(row["event_volume_ratio"]),
        "event_volume_change": float(row["event_volume_ratio"] - 1),
        "event_body_atr": float(row["event_body_atr"]),
        "event_body_return": float(row["event_body_return"]),
        "entry_rule": "Apertura ajustada de la siguiente sesión",
        "entry_date": row["entry_date"],
        "entry_open": float(row["entry_open"]),
        **{metric: float(row[metric]) for metric in METRICS},
        "source": "+".join(sources),
        "signal_sources": sources,
        "is_confluence": len(sources) > 1,
        "monthly_grade": source_grades.get("monthly"),
        "lm2_grade": source_grades.get("lm2"),
        "weekly_grade": source_grades.get("weekly"),
        "source_grades": source_grades,
        "formation_dates": formation_dates,
        "source_method_versions": {source: SOURCE_METHODS[source] for source in sources},
        "source_signal_ids": {
            source: f"{SOURCE_METHODS[source]}:{row['ticker']}:{row['event_date']}"
            for source in sources
        },
        "source_details": source_details,
        "cooldown_sessions": 10,
        "actionable": actionable,
        "suppressed_by_cooldown": (
            f"{MULTITEMPORAL_METHOD_VERSION}:{row['ticker']}:{suppressed_date}"
            if suppressed_date is not None
            else None
        ),
        "cooldown_gap_sessions": (
            int(row["cooldown_gap_sessions"])
            if pd.notna(row["cooldown_gap_sessions"])
            else None
        ),
    }
    return signal


def _upgrade_live_signal(signal: dict[str, Any]) -> dict[str, Any]:
    result = dict(signal)
    sources = sorted(
        result.get("signal_sources") or str(result.get("source", "monthly")).split("+"),
        key=SOURCE_ORDER.get,
    )
    result.update(
        signal_id=f"{MULTITEMPORAL_METHOD_VERSION}:{result['ticker']}:{result['event_date']}",
        method_version=MULTITEMPORAL_METHOD_VERSION,
        source="+".join(sources),
        signal_sources=sources,
        is_confluence=len(sources) > 1,
        source_method_versions={source: SOURCE_METHODS[source] for source in sources},
        source_signal_ids={
            source: f"{SOURCE_METHODS[source]}:{result['ticker']}:{result['event_date']}"
            for source in sources
        },
        reference_id=None,
        reference_complete=False,
        cooldown_sessions=10,
    )
    return result


def _sort(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        signals,
        key=lambda row: (
            GRADE_ORDER.get(str(row["grade"]), 9),
            str(row["event_date"]),
            str(row["ticker"]),
        ),
    )


def _profiles(frame: pd.DataFrame, grade_column: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for grade in ["A+", "A", "B"]:
        group = frame.loc[frame[grade_column].eq(grade)]
        result.append(
            {
                "grade": grade,
                "count": len(group),
                **{
                    metric: float(group[metric].mean()) if len(group) else None
                    for metric in METRICS
                },
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the audited MTR v2 signal contract")
    parser.add_argument("--unique", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    unique = pd.read_csv(args.unique)
    source = pd.read_csv(args.observations)

    history_path = root / "public/data/history.json"
    old_history = json.loads(history_path.read_text(encoding="utf-8"))["signals"]
    prior = _historical_lookup(old_history)
    observations = {
        (str(row["source"]), str(row["ticker"]), str(row["event_date"])): row
        for _, row in source.iterrows()
    }
    reference = [
        _reference_signal(row, observations, prior)
        for _, row in unique.iterrows()
    ]
    reference_keys = {(row["ticker"], row["event_date"]) for row in reference}
    last_reference_event = max(row["event_date"] for row in reference)
    live = [
        _upgrade_live_signal(row)
        for row in old_history
        if row["event_date"] > last_reference_event
        and (row["ticker"], row["event_date"]) not in reference_keys
    ]
    history = _sort([*reference, *live])

    unique.drop(columns=["stop_15pct"], errors="ignore").to_csv(
        root / "reference/signals_v2_0.csv", index=False
    )
    source.to_csv(root / "reference/source_signals_v2_0.csv", index=False)
    write_json(
        history_path,
        {
            "method_version": MULTITEMPORAL_METHOD_VERSION,
            "updated_at": _now(),
            "reference_cutoff": last_reference_event,
            "reference_signals": len(reference),
            "signals": history,
        },
    )

    actionable = unique.loc[unique["actionable"]].copy()
    write_json(
        root / "public/data/metrics.json",
        {
            "method_version": MULTITEMPORAL_METHOD_VERSION,
            "sample": f"{unique['event_date'].min()}/{unique['event_date'].max()}",
            "signals": len(unique),
            "actionable_signals": len(actionable),
            "operational_history_signals": len(history),
            "source_counts": {
                "monthly": int(source["source"].eq("monthly").sum()),
                "weekly_actionable": int(source["source"].eq("weekly").sum()),
                "lm2_actionable": int(source["source"].eq("lm2").sum()),
                "source_observations": len(source),
                "unique_total": len(unique),
                "actionable_after_cooldown": len(actionable),
                "cooldown_suppressed": int((~unique["actionable"]).sum()),
            },
            "grade_counts_unique": unique["master_grade"].value_counts().to_dict(),
            "grade_counts_actionable": actionable["master_grade"].value_counts().to_dict(),
            "weekly_b_policy": "excluded_after_comparative_validation",
            "lm2_b_policy": "excluded_after_comparative_validation",
            "cross_source_cooldown_sessions": 10,
            "outcome_definition": "Next-session adjusted open; exact 5/10-session R, MFE and MAE",
            "grade_profiles": _profiles(actionable, "master_grade"),
            "source_grade_profiles": {
                source_name: _profiles(group, "source_grade")
                for source_name, group in source.groupby("source", sort=False)
            },
        },
    )

    current_path = root / "public/data/current.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    history_by_key = {(row["ticker"], row["event_date"]): row for row in history}
    current["method_version"] = MULTITEMPORAL_METHOD_VERSION
    current["source_method_versions"] = SOURCE_METHODS
    current["weekly_b_policy"] = "computed_for_audit_but_never_published_or_alerted"
    current["lm2_b_policy"] = "computed_for_audit_but_never_published_or_alerted"
    current["cross_source_cooldown_sessions"] = 10
    current["reference_contract"] = {
        "unique_events": len(unique),
        "source_observations": len(source),
        "actionable_after_cooldown": len(actionable),
        "last_complete_outcome_event": last_reference_event,
    }
    current["signals"] = [
        history_by_key.get((row["ticker"], row["event_date"]), _upgrade_live_signal(row))
        for row in current.get("signals", [])
    ]
    write_json(current_path, current)

    print(
        json.dumps(
            {
                "reference_signals": len(reference),
                "source_observations": len(source),
                "actionable": len(actionable),
                "preserved_live_signals": len(live),
                "history_signals": len(history),
                "last_reference_event": last_reference_event,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
