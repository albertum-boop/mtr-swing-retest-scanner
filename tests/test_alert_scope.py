import pandas as pd

from mtr_scanner.pipeline import _new_alert_candidates


def test_alerts_exclude_stale_and_already_sent_signals():
    signals = [
        {"signal_id": "new", "event_date": "2026-08-27"},
        {"signal_id": "old", "event_date": "2026-08-05"},
        {"signal_id": "sent", "event_date": "2026-08-27"},
    ]

    result = _new_alert_candidates(
        signals,
        cutoff=pd.Timestamp("2026-08-27"),
        sent_ids={"sent"},
    )

    assert result == [{"signal_id": "new", "event_date": "2026-08-27"}]
