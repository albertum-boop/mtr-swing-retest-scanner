from mtr_scanner.signals import (
    annotate_signal,
    apply_signal_cooldown,
    merge_signal_records,
)


def _signal(source, grade, signal_id):
    formation_dates = {
        "monthly": "2026-07-31",
        "lm2": "2026-08-28",
        "weekly": "2026-08-21",
    }
    return annotate_signal(
        {
            "signal_id": signal_id,
            "grade": grade,
            "ticker": "TEST",
            "formation_date": formation_dates[source],
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


def test_three_source_confluence_keeps_all_real_grades_and_monthly_id():
    result = merge_signal_records(
        [
            _signal("monthly", "A", "monthly-id"),
            _signal("lm2", "A+", "lm2-id"),
            _signal("weekly", "A", "weekly-id"),
        ]
    )

    assert len(result) == 1
    merged = result[0]
    assert merged["source"] == "monthly+lm2+weekly"
    assert merged["signal_id"] == "monthly-id"
    assert merged["grade"] == "A+"
    assert merged["source_grades"] == {"monthly": "A", "lm2": "A+", "weekly": "A"}


def test_ten_session_cooldown_preserves_but_suppresses_later_event():
    first = _signal("monthly", "A", "first")
    first["event_date"] = "2026-08-03"
    first["signal_id"] = "first"
    first["source_signal_ids"]["monthly"] = "first"
    inside = _signal("lm2", "A+", "inside")
    inside["event_date"] = "2026-08-17"
    inside["signal_id"] = "inside"
    inside["source_signal_ids"]["lm2"] = "inside"
    outside = _signal("weekly", "A", "outside")
    outside["event_date"] = "2026-08-18"
    outside["signal_id"] = "outside"
    outside["source_signal_ids"]["weekly"] = "outside"

    result = sorted(apply_signal_cooldown([first, inside, outside]), key=lambda row: row["event_date"])

    assert [row["actionable"] for row in result] == [True, False, True]
    assert result[1]["suppressed_by_cooldown"] == "first"
