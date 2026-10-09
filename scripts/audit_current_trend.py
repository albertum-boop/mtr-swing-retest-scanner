"""Reproduce the trend overlay from the original OHLCV archive, never from outcomes.

Usage: python scripts/audit_current_trend.py --prices-zip /path/to/prices.zip
The v2.0 reference/grades/returns remain immutable. Later event-close fixtures
are used only for ALM/HUT diagnostics, never to assess complete-sample returns.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from mtr_scanner.pipeline import REFERENCE_CONTRACT
from mtr_scanner.trend import (
    OPERATIONAL_VERSION,
    TREND_PARAMETERS,
    TREND_POLICY_VERSION,
    annotate_trend,
    apply_operational_cooldown,
)

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("r5", "mfe5", "mae5", "r10", "mfe10", "mae10")


def profile(rows: list[dict]) -> dict:
    data = pd.DataFrame(rows)
    result = {"count": len(rows)}
    for metric in METRICS:
        result[metric] = float(data[metric].mean()) if rows else None
    result.update(
        median_r10=float(data.r10.median()) if rows else None,
        win_rate10=float(data.r10.gt(0).mean()) if rows else None,
        adverse_15pct_rate=float(data.mae10.le(-0.15).mean()) if rows else None,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices-zip", type=Path, required=True)
    args = parser.parse_args()
    history_path = ROOT / "public/data/history.json"
    history = json.loads(history_path.read_text())
    reference = pd.read_csv(ROOT / "reference/signals_v2_0.csv")
    keys = set(zip(reference.ticker, reference.event_date, strict=False))
    fixture = pd.read_csv(ROOT / "tests/fixtures/october_2026_trend_closes.csv")
    frames = {}
    with zipfile.ZipFile(args.prices_zip) as archive:
        for ticker in {s["ticker"] for s in history["signals"]}:
            path = f"prices/{ticker}.csv"
            if path in archive.namelist():
                frames[ticker] = pd.read_csv(archive.open(path), parse_dates=["Date"])
            special = fixture.loc[fixture.ticker.eq(ticker), ["Date", "Adj Close"]]
            if not special.empty:
                original = frames[ticker][["Date", "Adj Close"]].copy()
                special = special.copy()
                special["Date"] = pd.to_datetime(special.Date)
                frames[ticker] = pd.concat([original, special]).drop_duplicates("Date", keep="last")
    annotated = [annotate_trend(s, frames.get(s["ticker"])) for s in history["signals"]]
    annotated = apply_operational_cooldown(annotated)
    for signal in annotated:
        signal["reference_complete"] = (signal["ticker"], signal["event_date"]) in keys

    complete = [s for s in annotated if s["reference_complete"]]
    if len(complete) != 323 or any(s["trend_gate"]["status"] == "unknown" for s in complete):
        raise RuntimeError("Incomplete reference coverage: refusing to publish an audit")
    # Independently reproduce every recorded return from next-session adjusted open.
    max_return_difference = 0.0
    for s in complete:
        raw = frames[s["ticker"]]
        if not {"Open", "Close"}.issubset(raw):
            # ALM/HUT have a close-only supplement; reload full historic OHLCV.
            with zipfile.ZipFile(args.prices_zip) as archive:
                raw = pd.read_csv(archive.open(f"prices/{s['ticker']}.csv"))
        raw = raw.copy().sort_values("Date")
        dates = pd.to_datetime(raw.Date)
        i = int(np.flatnonzero(dates.eq(pd.Timestamp(s["event_date"])))[0])
        entry = float(raw.Open.iloc[i + 1] * raw["Adj Close"].iloc[i + 1] / raw.Close.iloc[i + 1])
        for horizon in (5, 10):
            actual = float(raw["Adj Close"].iloc[i + horizon] / entry - 1)
            max_return_difference = max(max_return_difference, abs(actual - s[f"r{horizon}"]))
    if max_return_difference > 1e-5:
        raise RuntimeError(f"Reference return mismatch: {max_return_difference}")

    baseline = [s for s in complete if s.get("actionable", True)]
    corrected = [s for s in complete if s["operational_actionable"]]
    retained = [s for s in baseline if s["operational_actionable"]]
    periods = []
    for label, start, end in [
        ("2019–2023", "2019-01-01", "2023-12-31"),
        ("2024–2026", "2024-01-01", "2026-08-05"),
    ]:
        periods.append({
            "period": label,
            "baseline": profile([s for s in baseline if start <= s["event_date"] <= end]),
            "corrected": profile([s for s in corrected if start <= s["event_date"] <= end]),
        })
    audit = {
        "policy_version": TREND_POLICY_VERSION,
        "operational_version": OPERATIONAL_VERSION,
        "parameters": TREND_PARAMETERS,
        "audited_on": "2026-10-08",
        "event_period": {"start": "2019-01-10", "end": "2026-08-05"},
        "status": "exploratory_structure_filter_not_independent_validation",
        "reference_coverage": len(complete),
        "maximum_return_reproduction_difference": max_return_difference,
        "baseline": profile(baseline),
        "corrected": profile(corrected),
        "retained_original": profile(retained),
        "readmitted_after_cooldown": len(corrected) - len(retained),
        "periods": periods,
        "grade_profiles": [
            {"grade": grade, **profile([s for s in corrected if s["grade"] == grade])}
            for grade in ("A+", "A", "B")
        ],
        "confluence_profiles": {
            "overall": {
                **profile([s for s in corrected if s.get("is_confluence")]),
                "grade_counts": {g: sum(s["grade"] == g and s.get("is_confluence", False) for s in corrected) for g in ("A+", "A", "B")},
                "grade_profiles": [{"grade": g, **profile([s for s in corrected if s.get("is_confluence") and s["grade"] == g])} for g in ("A+", "A", "B")],
            },
            "combinations": [{
                "source_key": key,
                "sources": key.split("+"),
                **profile([s for s in corrected if s["source"] == key]),
                "grade_counts": {g: sum(s["source"] == key and s["grade"] == g for s in corrected) for g in ("A+", "A", "B")},
                "grade_profiles": [{"grade": g, **profile([s for s in corrected if s["source"] == key and s["grade"] == g])} for g in ("A+", "A", "B")],
            } for key in ("monthly+lm2", "monthly+weekly", "lm2+weekly", "monthly+lm2+weekly")],
        },
        "interpretation": "Filtro de estructura: reduce entradas y retorno medio; no prueba una mejora de rentabilidad ni elimina pérdidas. Los periodos son descriptivos, no validación independiente.",
        "examples": [
            {"ticker": s["ticker"], "event_date": s["event_date"], "base_grade": s["grade"], "trend_gate": s["trend_gate"]}
            for s in annotated if s["ticker"] in {"ALM", "HUT"} and s["event_date"] == "2026-10-05"
        ],
    }
    history.update(operational_version=OPERATIONAL_VERSION, reference_signals=323, signals=annotated)
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n")
    current_path = ROOT / "public/data/current.json"
    current = json.loads(current_path.read_text())
    lookup = {(s["ticker"], s["event_date"]): s for s in annotated}
    current["signals"] = [lookup[(s["ticker"], s["event_date"])] for s in current["signals"]]
    for candidate in current["candidates"]:
        key = (candidate["ticker"], candidate.get("event_date"))
        if key in lookup:
            candidate["trend_gate"] = lookup[key]["trend_gate"]
            if not candidate["trend_gate"]["passed"]:
                candidate.update(status="rejected_current_trend", next_step="Retest registrado; entrada bloqueada por tendencia insuficiente")
    current.update(
        operational_version=OPERATIONAL_VERSION,
        trend_policy={"version": TREND_POLICY_VERSION, **TREND_PARAMETERS},
        reference_contract=REFERENCE_CONTRACT,
        alert_scope="Confirmed on cutoff; trend gate passed and operational cooldown cleared",
    )
    current["source_counts"].update(
        trend_blocked=sum(not s["trend_gate"]["passed"] for s in current["signals"]),
        operational_signals=sum(s["operational_actionable"] for s in current["signals"]),
        cooldown_suppressed=sum(s["operational_reason"] == "cooldown" for s in current["signals"]),
    )
    current_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "public/data/trend_metrics.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    export = [{
        "ticker": s["ticker"], "event_date": s["event_date"], "base_grade": s["grade"],
        "base_actionable": s.get("actionable", True), "operational_actionable": s["operational_actionable"],
        "trend_status": s["trend_gate"]["status"], "failed_conditions": ";".join(s["trend_gate"]["failed_conditions"]),
        **{k: s["trend_gate"][k] for k in ("close", "sma50", "sma200", "sma50_slope20", "sma200_slope20", "drawdown20")},
        **{k: s[k] for k in METRICS},
    } for s in complete]
    pd.DataFrame(export).to_csv(ROOT / "reference/trend_audit_v1_0.csv", index=False)
    print(json.dumps({k: audit[k] for k in ("baseline", "corrected", "retained_original", "readmitted_after_cooldown", "examples")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
