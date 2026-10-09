import pandas as pd

from mtr_scanner.pipeline import _new_alert_candidates
from mtr_scanner.trend import OPERATIONAL_VERSION, TREND_POLICY_VERSION


def test_alerts_exclude_stale_and_already_sent_signals():
    signals = [
        {"signal_id": "new", "event_date": "2026-08-27"},
        {"signal_id": "old", "event_date": "2026-08-05"},
        {"signal_id": "sent", "event_date": "2026-08-27"},
        {"signal_id": "cooldown", "event_date": "2026-08-27", "actionable": False},
    ]

    for signal in signals:
        signal.update(operational_version=OPERATIONAL_VERSION, operational_actionable=signal.get("actionable", True), trend_gate={"policy_version": TREND_POLICY_VERSION, "as_of": signal["event_date"], "passed": True})
    signals += [
        {"signal_id": "unknown", "event_date": "2026-08-27", "actionable": True},
        {**signals[0], "signal_id": "bad_trend", "trend_gate": {"policy_version": TREND_POLICY_VERSION, "as_of": "2026-08-27", "passed": False}},
    ]
    result = _new_alert_candidates(
        signals,
        cutoff=pd.Timestamp("2026-08-27"),
        sent_ids={"sent"},
    )

    assert [row["signal_id"] for row in result] == ["new"]
