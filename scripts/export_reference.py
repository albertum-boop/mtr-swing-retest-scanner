from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


def value(row: pd.Series, name: str):
    item = row.get(name)
    return None if pd.isna(item) else item


def signal_record(row: pd.Series) -> dict[str, object]:
    event_date = pd.Timestamp(row["EventDate"]).date().isoformat()
    ticker = str(row["Ticker"])
    return {
        "signal_id": f"MTR-Swing-Retest-v1.0:{ticker}:{event_date}",
        "reference_id": row["SignalID"],
        "method_version": "MTR-Swing-Retest-v1.0",
        "grade": row["Grade"],
        "ticker": ticker,
        "formation_date": pd.Timestamp(row["FormationDate"]).date().isoformat(),
        "event_date": event_date,
        "entry_date": pd.Timestamp(row["EntryDate"]).date().isoformat(),
        "entry_open": value(row, "EntryOpenAdj"),
        "entry_rule": "Apertura ajustada de la siguiente sesión",
        "event_day": value(row, "EventDay"),
        "formation_close": value(row, "FormationClose"),
        "atr_abs20": value(row, "ATRPct") * value(row, "FormationClose"),
        "adv20": value(row, "ADV20"),
        "universe_momentum_percentile": value(row, "RankPct"),
        "swing_score": value(row, "SwingScore"),
        "momentum_percentile_d10": value(row, "Mom12_1_Daily"),
        "atr_percentile_d10": value(row, "ATRPct20"),
        "return_volume_percentile_d10": value(row, "ReturnVolumeCorr20"),
        "sma200_slope_percentile_d10": value(row, "SMA200Slope20"),
        "expansion_peak_atr": value(row, "ExpansionPeakATR"),
        "pullback_from_peak_atr": value(row, "PullbackFromPeakATR"),
        "close_vs_level_atr": value(row, "CloseVsLevelATR"),
        "close_location": value(row, "EventCloseLocation"),
        "event_volume_change": value(row, "EventVolumeToPrior20"),
        "event_body_atr": value(row, "EventBodyATR"),
        "event_body_return": value(row, "EventBodyReturn"),
        "r5": value(row, "NextOpenR5"),
        "mfe5": value(row, "NextOpenMFE5"),
        "mae5": value(row, "NextOpenMAE5"),
        "r10": value(row, "NextOpenR10"),
        "mfe10": value(row, "NextOpenMFE10"),
        "mae10": value(row, "NextOpenMAE10"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.analysis_dir.resolve()))
    from append_full_signal_registry import build_dataset

    data = build_dataset()
    records = [signal_record(row) for _, row in data.iterrows()]
    compact_columns = [
        "reference_id", "grade", "ticker", "formation_date", "event_date", "entry_date",
        "entry_open", "r5", "mfe5", "mae5", "r10", "mfe10", "mae10",
        "sma200_slope_percentile_d10", "pullback_from_peak_atr", "event_body_atr",
        "event_body_return", "close_location",
    ]
    reference = pd.DataFrame(records)[compact_columns]
    reference_path = args.repo / "reference" / "signals_v1_0.csv"
    reference.to_csv(reference_path, index=False)
    history_path = args.repo / "public" / "data" / "history.json"
    history_path.write_text(
        json.dumps(
            {
                "method_version": "MTR-Swing-Retest-v1.0",
                "updated_at": "2026-08-27T22:00:00+00:00",
                "signals": records,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    current_signals = [row for row in records if row["formation_date"] == "2026-07-31"]
    current = {
        "method_version": "MTR-Swing-Retest-v1.0",
        "generated_at": "2026-08-27T22:00:00+00:00",
        "cutoff": "2026-08-27",
        "formation_date": "2026-07-31",
        "session_after_formation": 19,
        "formation_stats": {
            "observed": 1776,
            "eligible": 1776,
            "d10": 178,
            "swing_top20": 36,
            "coverage": 1.0,
            "download_errors": 0,
        },
        "scan_status": {"signal": len(current_signals), "expired": 36 - len(current_signals)},
        "signals": current_signals,
        "alert_result": {"status": "historical_seed", "sent": 0},
    }
    (args.repo / "public" / "data" / "current.json").write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Exportadas {len(records)} señales; actuales: {len(current_signals)}")


if __name__ == "__main__":
    main()
