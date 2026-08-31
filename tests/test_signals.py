from mtr_scanner.signals import annotate_signal, merge_signal_records


def _signal(source, grade, signal_id):
    return annotate_signal(
        {
            "signal_id": signal_id,
            "grade": grade,
            "ticker": "TEST",
            "formation_date": "2026-07-31" if source == "monthly" else "2026-08-21",
            "event_date": "2026-08-25",
            "entry_date": "2026-08-26",
            "r5": 0.10,
        },
        source,
    )


def test_exact_event_confluence_preserves_monthly_id_and_best_real_grade():
    monthly = _signal("monthly", "A", "monthly-id")
    weekly = _signal("weekly", "A+", "discarded-by-annotate")

    result = merge_signal_records([monthly, weekly])

    assert len(result) == 1
    merged = result[0]
    assert merged["signal_id"] == "monthly-id"
    assert merged["source"] == "monthly+weekly"
    assert merged["is_confluence"] is True
    assert merged["grade"] == "A+"
    assert merged["monthly_grade"] == "A"
    assert merged["weekly_grade"] == "A+"
    assert merged["formation_dates"] == {
        "monthly": "2026-07-31",
        "weekly": "2026-08-21",
    }
