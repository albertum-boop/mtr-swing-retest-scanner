from datetime import date

from mtr_scanner.alerts import build_weekly_email
from mtr_scanner.weekly_report import report_window, select_week_signals


def signal(
    ticker: str,
    event_date: str,
    *,
    grade: str = "A",
    actionable: bool = True,
) -> dict[str, object]:
    return {
        "signal_id": f"test:{ticker}:{event_date}",
        "ticker": ticker,
        "grade": grade,
        "event_date": event_date,
        "entry_date": "2026-10-02",
        "entry_open": 141.87,
        "source": "lm2",
        "signal_sources": ["lm2"],
        "is_confluence": False,
        "swing_score": 0.83,
        "event_volume_change": -0.48,
        "actionable": actionable,
    }


def test_report_window_starts_on_monday():
    assert report_window(date(2026, 10, 2)) == (
        date(2026, 9, 28),
        date(2026, 10, 2),
    )


def test_weekly_selection_excludes_old_and_suppressed_events():
    signals = [
        signal("DOCN", "2026-10-01", grade="A+"),
        signal("DMRA", "2026-09-29"),
        signal("OLD", "2026-09-25"),
        signal("BLOCKED", "2026-10-01", actionable=False),
    ]

    selected = select_week_signals(
        signals,
        week_start=date(2026, 9, 28),
        week_end=date(2026, 10, 2),
    )

    assert [row["ticker"] for row in selected] == ["DOCN", "DMRA"]


def test_weekly_email_includes_entry_and_sends_empty_week_content():
    subject, plain, body = build_weekly_email(
        [signal("DOCN", "2026-10-01", grade="A+")],
        week_start=date(2026, 9, 28),
        week_end=date(2026, 10, 2),
    )
    assert "1 señal" in subject
    assert "DOCN" in plain
    assert "2026-10-02 $141.87" in plain
    assert "Abrir MTR Swing Retest Scanner" in body

    empty_subject, empty_plain, empty_body = build_weekly_email(
        [],
        week_start=date(2026, 9, 28),
        week_end=date(2026, 10, 2),
    )
    assert "0 señales" in empty_subject
    assert "No hubo señales accionables" in empty_plain
    assert "No hubo señales accionables" in empty_body
