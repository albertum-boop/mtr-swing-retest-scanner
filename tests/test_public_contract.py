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
        if "monthly" in row.get("signal_sources", [])
    }
    assert len(monthly_events) == 154


def test_public_history_separates_complete_reference_from_later_live_signals():
    history = json.loads((ROOT / "public" / "data" / "history.json").read_text())
    complete = [row for row in history["signals"] if row.get("reference_complete")]
    later = [row for row in history["signals"] if row.get("reference_complete") is False]

    assert history["method_version"] == "MTR-Multitemporal-v2.0"
    assert history["reference_signals"] == 323
    assert len(complete) == 323
    assert [(row["ticker"], row["event_date"]) for row in later] == [
        ("MRVL", "2026-08-26")
    ]
