import pandas as pd

from mtr_scanner.market_calendar import (
    active_formation_date,
    previous_weekly_formation_date,
    session_number_after,
    weekly_formation_dates,
)


def test_active_formation_waits_for_completed_month_end():
    assert active_formation_date(pd.Timestamp("2026-08-27")) == pd.Timestamp("2026-07-31")
    assert active_formation_date(pd.Timestamp("2026-08-31")) == pd.Timestamp("2026-08-31")


def test_event_day_uses_nyse_sessions():
    assert session_number_after(pd.Timestamp("2026-07-31"), pd.Timestamp("2026-08-05")) == 3


def test_weekly_formation_uses_only_completed_weekly_closes():
    assert weekly_formation_dates(pd.Timestamp("2026-08-27"), count=2) == [
        pd.Timestamp("2026-08-14"),
        pd.Timestamp("2026-08-21"),
    ]
    assert weekly_formation_dates(pd.Timestamp("2026-08-28"), count=2) == [
        pd.Timestamp("2026-08-21"),
        pd.Timestamp("2026-08-28"),
    ]
    assert previous_weekly_formation_date(pd.Timestamp("2026-08-21")) == pd.Timestamp(
        "2026-08-14"
    )
