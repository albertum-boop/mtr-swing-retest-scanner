from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from mtr_scanner.alerts import GRADE_ORDER
from mtr_scanner.lm2 import LM2_METHOD_VERSION
from mtr_scanner.signals import annotate_signal, apply_signal_cooldown
from mtr_scanner.storage import write_json
from mtr_scanner.weekly import MULTITEMPORAL_METHOD_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _clean(value: Any) -> Any:
    return None if pd.isna(value) else value


def _lm2_signal(row: pd.Series) -> dict[str, Any]:
    checks = {
        "non_negative_formation_gap": bool(row["formation_gap"] >= 0.0),
        "high_atr_percentile": bool(row["atr_pct20_pct"] >= 0.85),
        "strong_sma200_slope": bool(row["sma200_slope20_raw"] >= 0.075),
    }
    signal = {
        "signal_id": f"research:{row['ticker']}:{row['event_date']}",
        "method_version": "MTR-Swing-Retest-v1.0",
        "grade": row["late_grade"],
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
        "lm2_quality_points": int(row["quality_points"]),
        "lm2_quality_checks": checks,
        "formation_gap": row["formation_gap"],
        "formation_atr_percentile_d10": row["atr_pct20_pct"],
        "formation_sma200_slope20": row["sma200_slope20_raw"],
    }
    return annotate_signal({key: _clean(value) for key, value in signal.items()}, "lm2")


def _strip_lm2(signal: dict[str, Any]) -> dict[str, Any] | None:
    sources = list(signal.get("signal_sources") or [signal.get("source", "monthly")])
    if "lm2" not in sources:
        return signal
    remaining = [source for source in sources if source != "lm2"]
    if not remaining:
        return None
    result = dict(signal)
    for field in [
        "source_grades",
        "formation_dates",
        "source_method_versions",
        "source_signal_ids",
        "source_details",
    ]:
        result[field] = {
            key: value for key, value in result.get(field, {}).items() if key != "lm2"
        }
    result["signal_sources"] = remaining
    result["source"] = "+".join(remaining)
    result["is_confluence"] = len(remaining) > 1
    result["lm2_grade"] = None
    result["grade"] = min(
        result["source_grades"].values(), key=lambda grade: GRADE_ORDER.get(grade, 9)
    )
    primary = "monthly" if "monthly" in remaining else "weekly"
    result["signal_id"] = result["source_signal_ids"][primary]
    result["formation_date"] = result["formation_dates"][primary]
    return result


def _reference_union(base: pd.DataFrame, lm2: pd.DataFrame) -> pd.DataFrame:
    records = {
        (str(row["ticker"]), str(row["event_date"])): row.to_dict()
        for _, row in base.iterrows()
    }
    for _, row in lm2.loc[lm2["late_grade"].isin(["A+", "A"])].iterrows():
        key = str(row["ticker"]), str(row["event_date"])
        if key in records:
            record = records[key]
            record["origin"] = "weekly_lm2_confluence"
            record["lm2_grade"] = row["late_grade"]
            record["lm2_formation_date"] = row["formation_date"]
            record["lm2_quality_points"] = int(row["quality_points"])
            record["master_grade"] = min(
                [record["master_grade"], row["late_grade"]],
                key=lambda grade: GRADE_ORDER.get(grade, 9),
            )
            record["is_exact_confluence"] = True
            continue
        records[key] = {
            "ticker": row["ticker"],
            "origin": "lm2_incremental",
            "monthly_reference_id": None,
            "weekly_reference_id": None,
            "monthly_grade": None,
            "weekly_grade": None,
            "monthly_formation_date": None,
            "weekly_formation_date": None,
            "event_date": row["event_date"],
            "entry_date": row["entry_date"],
            "r5": row["r5"],
            "mfe5": row["mfe5"],
            "mae5": row["mae5"],
            "r10": row["r10"],
            "mfe10": row["mfe10"],
            "mae10": row["mae10"],
            "master_grade": row["late_grade"],
            "signal_id": f"{LM2_METHOD_VERSION}:{row['ticker']}:{row['event_date']}",
            "year": row["year"],
            "sample": row["sample"],
            "is_exact_confluence": False,
            "lm2_grade": row["late_grade"],
            "lm2_formation_date": row["formation_date"],
            "lm2_quality_points": int(row["quality_points"]),
        }
    union = pd.DataFrame(records.values())
    for column in ["lm2_grade", "lm2_formation_date", "lm2_quality_points"]:
        if column not in union:
            union[column] = None
    return union.sort_values(
        ["master_grade", "event_date", "ticker"],
        key=lambda column: (
            column.map(GRADE_ORDER) if column.name == "master_grade" else column
        ),
    )


def _grade_profiles(frame: pd.DataFrame, grade_column: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for grade in ["A+", "A", "B"]:
        group = frame.loc[frame[grade_column].eq(grade)]
        result.append(
            {
                "grade": grade,
                "count": len(group),
                **{
                    field: float(group[field].mean())
                    for field in ["r5", "mfe5", "mae5", "r10", "mfe10", "mae10"]
                },
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the frozen LM2 reference")
    parser.add_argument("--lm2-research", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()

    lm2 = pd.read_csv(args.lm2_research)
    lm2_export = lm2.copy()
    lm2_export.insert(0, "actionable", lm2_export["late_grade"].isin(["A+", "A"]))
    lm2_export = lm2_export.rename(
        columns={"grade": "base_retest_grade", "late_grade": "grade"}
    ).sort_values(
        ["grade", "event_date", "ticker"],
        key=lambda column: column.map(GRADE_ORDER) if column.name == "grade" else column,
    )
    lm2_export.to_csv(root / "reference" / "lm2_signals_v1_0.csv", index=False)

    base = pd.read_csv(root / "reference" / "multitemporal_signals_v1_1.csv")
    union = _reference_union(base, lm2)
    union.to_csv(root / "reference" / "multitemporal_signals_v1_2.csv", index=False)

    history_path = root / "public" / "data" / "history.json"
    history_payload = json.loads(history_path.read_text(encoding="utf-8"))
    without_lm2 = [
        stripped
        for signal in history_payload.get("signals", [])
        if (stripped := _strip_lm2(signal)) is not None
    ]
    lm2_signals = [
        _lm2_signal(row)
        for _, row in lm2.loc[lm2["late_grade"].isin(["A+", "A"])].iterrows()
    ]
    history = sorted(
        apply_signal_cooldown([*without_lm2, *lm2_signals], cooldown_sessions=10),
        key=lambda row: (
            GRADE_ORDER.get(row["grade"], 9),
            row["event_date"],
            row["ticker"],
        ),
    )
    write_json(
        history_path,
        {
            "method_version": MULTITEMPORAL_METHOD_VERSION,
            "updated_at": pd.Timestamp.now(tz="UTC").floor("s").isoformat(),
            "signals": history,
        },
    )

    write_json(
        root / "public" / "data" / "metrics.json",
        {
            "method_version": MULTITEMPORAL_METHOD_VERSION,
            "sample": f"{union['event_date'].min()}/{union['event_date'].max()}",
            "signals": len(union),
            "source_counts": {
                "monthly": 154,
                "weekly_actionable": 91,
                "lm2_total_audit": len(lm2),
                "lm2_actionable": int(lm2["late_grade"].isin(["A+", "A"]).sum()),
                "lm2_incremental": int(union["origin"].eq("lm2_incremental").sum()),
                "weekly_lm2_exact_confluence": int(
                    union["origin"].eq("weekly_lm2_confluence").sum()
                ),
                "unique_total": len(union),
            },
            "weekly_b_policy": "excluded_after_comparative_validation",
            "lm2_b_policy": "excluded_after_comparative_validation",
            "cross_source_cooldown_sessions": 10,
            "grade_profiles": _grade_profiles(union, "master_grade"),
            "lm2_grade_profiles": _grade_profiles(lm2, "late_grade"),
        },
    )

    current_path = root / "public" / "data" / "current.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    current["method_version"] = MULTITEMPORAL_METHOD_VERSION
    current.setdefault("source_method_versions", {})["lm2"] = LM2_METHOD_VERSION
    current["lm2_formation_date"] = None
    current["lm2_formation_stats"] = None
    current.setdefault("source_counts", {})["lm2_candidates"] = 0
    current["source_counts"]["lm2_signals"] = 0
    current["source_counts"]["cooldown_suppressed"] = 0
    current.setdefault("scan_status_by_source", {})["lm2"] = {}
    current["lm2_b_policy"] = "computed_for_audit_but_never_published_or_alerted"
    current["cross_source_cooldown_sessions"] = 10
    current["alert_scope"] = (
        "A+, A and monthly B confirmed on cutoff; actionable after 10-session cooldown"
    )
    write_json(current_path, current)


if __name__ == "__main__":
    main()
