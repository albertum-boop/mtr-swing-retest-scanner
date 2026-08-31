from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from mtr_scanner.alerts import GRADE_ORDER
from mtr_scanner.signals import annotate_signal, merge_signal_records
from mtr_scanner.storage import write_json
from mtr_scanner.weekly import MULTITEMPORAL_METHOD_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _clean(value: Any) -> Any:
    return None if pd.isna(value) else value


def _weekly_signal(row: pd.Series) -> dict[str, Any]:
    signal = {
        "signal_id": f"research:{row['ticker']}:{row['event_date']}",
        "method_version": "MTR-Swing-Retest-v1.0",
        "grade": row["weekly_grade"],
        "base_retest_grade": row["grade"],
        "ticker": row["ticker"],
        "formation_date": row["formation_date"],
        "event_date": row["event_date"],
        "event_day": row["event_day"],
        "formation_close": row["formation_close"],
        "atr_abs20": row["atr_abs20"],
        "adv20": row["adv20"],
        "universe_momentum_percentile": row["rank_pct"],
        "swing_score": row["swing_score"],
        "swing_rank_percentile": row["swing_rank_pct"],
        "momentum_percentile_d10": row["mom12_1_pct"],
        "atr_percentile_d10": row["atr_pct20_pct"],
        "return_volume_percentile_d10": row["return_volume_corr20_pct"],
        "sma200_slope_percentile_d10": row["sma200_slope20_pct"],
        "formation_relative_volume5_20": row["relative_volume5_20"],
        "expansion_peak_atr": row["expansion_peak_atr"],
        "pullback_from_peak_atr": row["pullback_from_peak_atr"],
        "close_vs_level_atr": row["close_vs_level_atr"],
        "close_location": row["close_location"],
        "event_volume_ratio": row["event_volume_ratio"],
        "event_volume_change": row["event_volume_ratio"] - 1,
        "event_body_atr": row["event_body_atr"],
        "event_body_return": row["event_body_return"],
        "entry_rule": "Apertura ajustada de la siguiente sesión",
        "entry_date": row["entry_date"],
        "entry_open": row["entry_open"],
        "r5": row["r5"],
        "mfe5": row["mfe5"],
        "mae5": row["mae5"],
        "r10": row["r10"],
        "mfe10": row["mfe10"],
        "mae10": row["mae10"],
        "weekly_quality_points": row["weekly_quality_points"],
        "weekly_quality_checks": {
            "momentum": bool(row["weekly_pass_momentum"]),
            "controlled_atr": bool(row["weekly_pass_controlled_atr"]),
            "swing_rank": bool(row["weekly_pass_swing_rank"]),
            "retest_extension": bool(row["weekly_pass_retest_extension"]),
        },
        "weekly_formation_volume_confirmation": bool(row["weekly_pass_formation_volume"]),
    }
    return annotate_signal({key: _clean(value) for key, value in signal.items()}, "weekly")


def _sort(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        signals,
        key=lambda row: (
            GRADE_ORDER.get(row["grade"], 9),
            row["event_date"],
            row["ticker"],
        ),
    )


def _monthly_signals(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    multitemporal_fields = {
        "source",
        "signal_sources",
        "is_confluence",
        "monthly_grade",
        "weekly_grade",
        "source_grades",
        "formation_dates",
        "source_method_versions",
        "source_signal_ids",
        "source_details",
    }
    for signal in history:
        sources = signal.get("signal_sources") or [signal.get("source", "monthly")]
        if "monthly" not in sources:
            continue
        monthly = {key: value for key, value in signal.items() if key not in multitemporal_fields}
        monthly["grade"] = signal.get("monthly_grade") or signal["grade"]
        monthly["signal_id"] = signal.get("source_signal_ids", {}).get(
            "monthly", signal["signal_id"]
        )
        result.append(annotate_signal(monthly, "monthly"))
    return result


def _grade_profiles(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(signals)
    profiles: list[dict[str, Any]] = []
    for grade in ["A+", "A", "B"]:
        group = frame.loc[frame["grade"].eq(grade)]
        profiles.append(
            {
                "grade": grade,
                "count": len(group),
                **{
                    field: float(group[field].mean())
                    for field in ["r5", "mfe5", "mae5", "r10", "mfe10", "mae10"]
                },
            }
        )
    return profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the audited multitemporal reference")
    parser.add_argument("--weekly-research", type=Path, required=True)
    parser.add_argument("--multitemporal-research", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()

    weekly = pd.read_csv(args.weekly_research)
    weekly_export = weekly.copy()
    weekly_export.insert(0, "base_retest_grade", weekly_export["grade"])
    weekly_export["grade"] = weekly_export["weekly_grade"]
    weekly_export.insert(0, "actionable", weekly_export["grade"].isin(["A+", "A"]))
    weekly_export = weekly_export.sort_values(
        ["grade", "event_date", "ticker"],
        key=lambda column: column.map(GRADE_ORDER) if column.name == "grade" else column,
    )
    weekly_export.to_csv(root / "reference" / "weekly_signals_v1_0.csv", index=False)

    multitemporal = pd.read_csv(args.multitemporal_research)
    multitemporal["origin"] = multitemporal["origin"].replace(
        {"monthly": "monthly_only", "monthly+weekly": "exact_confluence"}
    )
    multitemporal = multitemporal.sort_values(
        ["master_grade", "event_date", "ticker"],
        key=lambda column: column.map(GRADE_ORDER) if column.name == "master_grade" else column,
    )
    multitemporal.to_csv(
        root / "reference" / "multitemporal_signals_v1_1.csv", index=False
    )

    history_path = root / "public" / "data" / "history.json"
    history = json.loads(history_path.read_text(encoding="utf-8"))["signals"]
    monthly = _monthly_signals(history)
    weekly_signals = [
        _weekly_signal(row)
        for _, row in weekly.loc[weekly["weekly_grade"].isin(["A+", "A"])].iterrows()
    ]
    combined = _sort(merge_signal_records([*monthly, *weekly_signals]))

    counts = pd.Series([row["grade"] for row in combined]).value_counts().to_dict()
    sources = pd.Series([row["source"] for row in combined]).value_counts().to_dict()
    assert len(combined) == 232
    assert counts == {"A": 132, "A+": 75, "B": 25}
    assert sources == {"monthly": 141, "weekly": 78, "monthly+weekly": 13}
    write_json(
        history_path,
        {
            "method_version": MULTITEMPORAL_METHOD_VERSION,
            "updated_at": pd.Timestamp.now(tz="UTC").floor("s").isoformat(),
            "signals": combined,
        },
    )
    write_json(
        root / "public" / "data" / "metrics.json",
        {
            "method_version": MULTITEMPORAL_METHOD_VERSION,
            "sample": f"{min(row['event_date'] for row in combined)}/{max(row['event_date'] for row in combined)}",
            "signals": len(combined),
            "source_counts": {
                "monthly": 154,
                "weekly_actionable": 91,
                "exact_confluence": 13,
                "weekly_incremental": 78,
                "unique_total": 232,
            },
            "weekly_b_policy": "excluded_after_comparative_validation",
            "grade_profiles": _grade_profiles(combined),
        },
    )


if __name__ == "__main__":
    main()
