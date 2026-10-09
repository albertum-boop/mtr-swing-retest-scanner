import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_multitemporal_contract_excludes_weekly_and_lm2_b():
    current = json.loads((ROOT / "public" / "data" / "current.json").read_text())
    history = json.loads((ROOT / "public" / "data" / "history.json").read_text())

    assert current["method_version"] == "MTR-Multitemporal-v2.0"
    assert current["weekly_b_policy"] == "computed_for_audit_but_never_published_or_alerted"
    assert current["lm2_b_policy"] == "computed_for_audit_but_never_published_or_alerted"
    assert current["cross_source_cooldown_sessions"] == 10
    assert current["reference_contract"] == {
        "unique_events": 323,
        "source_observations": 348,
        "actionable_after_cooldown": 313,
        "last_complete_outcome_event": "2026-08-05",
    }
    assert len({row["candidate_id"] for row in current["candidates"]}) == len(
        current["candidates"]
    )
    assert all(
        not (
            set(row.get("signal_sources", [])) & {"weekly", "lm2"}
            and row["grade"] == "B"
            and "monthly" not in row.get("signal_sources", [])
        )
        for row in [*current["signals"], *history["signals"]]
    )
    assert all(
        not ({"stop_price", "stop_loss_percent", "fixed_profit_target"} & set(row))
        for row in [*current["signals"], *history["signals"]]
    )


def test_public_history_preserves_every_original_monthly_event():
    history = json.loads((ROOT / "public" / "data" / "history.json").read_text())["signals"]
    monthly_events = {
        (row["ticker"], row["event_date"])
        for row in history
        if row.get("reference_complete") and "monthly" in row.get("signal_sources", [])
    }
    assert len(monthly_events) == 154


def test_public_history_separates_complete_reference_from_later_live_signals():
    history = json.loads((ROOT / "public" / "data" / "history.json").read_text())
    complete = [row for row in history["signals"] if row.get("reference_complete")]
    later = [row for row in history["signals"] if row.get("reference_complete") is False]

    assert history["method_version"] == "MTR-Multitemporal-v2.0"
    assert history["reference_signals"] == 323
    assert len(complete) == 323
    assert all(row["event_date"] > "2026-08-05" for row in later)
    assert {("ALM", "2026-10-05"), ("HUT", "2026-10-05")} <= {(row["ticker"], row["event_date"]) for row in later}


def test_public_metrics_distinguish_every_actionable_confluence_combination():
    metrics = json.loads((ROOT / "public" / "data" / "metrics.json").read_text())
    confluence = metrics["confluence_profiles"]

    assert confluence["overall"]["count"] == 22
    assert confluence["overall"]["grade_counts"] == {"A+": 12, "A": 10, "B": 0}
    assert {
        row["source_key"]: row["count"]
        for row in confluence["combinations"]
    } == {
        "monthly+lm2": 7,
        "monthly+weekly": 11,
        "lm2+weekly": 2,
        "monthly+lm2+weekly": 2,
    }
    assert all(
        row["count"] == sum(row["grade_counts"].values())
        for row in [confluence["overall"], *confluence["combinations"]]
    )
    assert all(
        metric in row
        for row in [confluence["overall"], *confluence["combinations"]]
        for metric in ["r5", "mfe5", "mae5", "r10", "mfe10", "mae10"]
    )


def test_operational_gate_blocks_latest_alm_and_hut_without_erasing_a_grades():
    current = json.loads((ROOT / "public/data/current.json").read_text())
    assert current["operational_version"] == "MTR-Multitemporal-v2.1"
    history = json.loads((ROOT / "public/data/history.json").read_text())
    rows = [s for s in history["signals"] if s["ticker"] in {"ALM", "HUT"} and s["event_date"] == "2026-10-05"]
    assert len(rows) == 2
    assert all(s["grade"] == "A" and s["operational_actionable"] is False for s in rows)
    assert all(s["trend_gate"]["as_of"] == s["event_date"] for s in rows)
    audit = json.loads((ROOT / "public/data/trend_metrics.json").read_text())
    assert audit["reference_coverage"] == 323
    assert audit["baseline"]["count"] == 313
    assert audit["corrected"]["count"] == 160
    assert audit["maximum_return_reproduction_difference"] < 1e-5
