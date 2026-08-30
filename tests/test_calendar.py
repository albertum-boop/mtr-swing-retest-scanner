import pandas as pd

from mtr_scanner.market_calendar import active_formation_date, session_number_after


def test_active_formation_waits_for_completed_month_end():
    assert active_formation_date(pd.Timestamp("2026-08-27")) == pd.Timestamp("2026-07-31")
    assert active_formation_date(pd.Timestamp("2026-08-31")) == pd.Timestamp("2026-08-31")


def test_event_day_uses_nyse_sessions():
    assert session_number_after(pd.Timestamp("2026-07-31"), pd.Timestamp("2026-08-05")) == 3
