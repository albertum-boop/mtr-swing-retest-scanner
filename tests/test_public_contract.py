import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_multitemporal_contract_excludes_weekly_b():
    current = json.loads((ROOT / "public" / "data" / "current.json").read_text())
    history = json.loads((ROOT / "public" / "data" / "history.json").read_text())

    assert current["method_version"] == "MTR-Multitemporal-v1.1"
    assert current["weekly_b_policy"] == "computed_for_audit_but_never_published_or_alerted"
    assert len({row["candidate_id"] for row in current["candidates"]}) == len(
        current["candidates"]
    )
    assert all(
        not (row.get("source") == "weekly" and row["grade"] == "B")
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
