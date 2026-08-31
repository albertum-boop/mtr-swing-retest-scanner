from __future__ import annotations

from datetime import datetime

import pandas as pd
import pandas_market_calendars as mcal


def _schedule(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    calendar = mcal.get_calendar("NYSE")
    schedule = calendar.schedule(start_date=start.date(), end_date=end.date())
    return pd.DatetimeIndex(schedule.index).tz_localize(None)


def latest_completed_session(
    now: datetime | pd.Timestamp | None = None,
    *,
    market_timezone: str = "America/New_York",
    finalization_hour_et: int = 18,
) -> pd.Timestamp:
    current = pd.Timestamp.now(tz=market_timezone) if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize(market_timezone)
    else:
        current = current.tz_convert(market_timezone)
    sessions = _schedule(current.tz_localize(None) - pd.Timedelta(days=14), current.tz_localize(None))
    if not len(sessions):
        raise RuntimeError("No se encontraron sesiones NYSE recientes")
    today = current.tz_localize(None).normalize()
    if today in sessions and current.hour < finalization_hour_et:
        sessions = sessions[sessions < today]
    else:
        sessions = sessions[sessions <= today]
    if not len(sessions):
        raise RuntimeError("No existe todavía una sesión NYSE completa")
    return pd.Timestamp(sessions[-1])


def active_formation_date(cutoff: pd.Timestamp) -> pd.Timestamp:
    """Most recent completed NYSE month-end at or before ``cutoff``."""

    cutoff = pd.Timestamp(cutoff).normalize()
    sessions = _schedule(cutoff - pd.Timedelta(days=70), cutoff + pd.Timedelta(days=7))
    month_ends = pd.Series(sessions, index=sessions).groupby(sessions.to_period("M")).max()
    completed = month_ends.loc[month_ends.le(cutoff)]
    if completed.empty:
        raise RuntimeError("No se encontró un cierre mensual NYSE completo")
    return pd.Timestamp(completed.iloc[-1])


def active_lm2_formation_date(cutoff: pd.Timestamp) -> pd.Timestamp:
    """Most recent completed penultimate NYSE session of a calendar month."""

    cutoff = pd.Timestamp(cutoff).normalize()
    sessions = _schedule(cutoff - pd.Timedelta(days=100), cutoff + pd.Timedelta(days=10))
    grouped = pd.Series(sessions, index=sessions).groupby(sessions.to_period("M"))
    penultimate = grouped.nth(-2)
    completed = penultimate.loc[penultimate.le(cutoff)]
    if completed.empty:
        raise RuntimeError("No se encontró una formación LM2 completa")
    return pd.Timestamp(completed.iloc[-1])


def sessions_between(start: pd.Timestamp, end: pd.Timestamp) -> int:
    """Count completed NYSE sessions strictly after ``start`` through ``end``."""

    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()
    if end <= start:
        return 0
    sessions = _schedule(start, end)
    return int(((sessions > start) & (sessions <= end)).sum())


def session_ordinals(dates: list[pd.Timestamp]) -> dict[str, int]:
    """Map NYSE signal dates to one shared ordinal for fast distance checks."""

    normalized = sorted({pd.Timestamp(value).normalize() for value in dates})
    if not normalized:
        return {}
    sessions = _schedule(normalized[0] - pd.Timedelta(days=7), normalized[-1])
    return {
        value.date().isoformat(): int(sessions.searchsorted(value, side="right") - 1)
        for value in normalized
    }


def weekly_formation_dates(cutoff: pd.Timestamp, count: int = 2) -> list[pd.Timestamp]:
    """Last completed NYSE session in each W-FRI week, oldest first."""

    cutoff = pd.Timestamp(cutoff).normalize()
    lookback_days = max(35, count * 12)
    sessions = _schedule(
        cutoff - pd.Timedelta(days=lookback_days), cutoff + pd.Timedelta(days=7)
    )
    weekly_closes = pd.Series(sessions, index=sessions).groupby(
        sessions.to_period("W-FRI")
    ).max()
    completed = weekly_closes.loc[weekly_closes.le(cutoff)].tail(count)
    if len(completed) < count:
        raise RuntimeError("No se encontraron suficientes cierres semanales NYSE")
    return [pd.Timestamp(value) for value in completed]


def previous_weekly_formation_date(formation: pd.Timestamp) -> pd.Timestamp:
    return weekly_formation_dates(
        pd.Timestamp(formation) - pd.Timedelta(days=1), count=1
    )[0]


def session_number_after(formation: pd.Timestamp, cutoff: pd.Timestamp) -> int:
    sessions = _schedule(pd.Timestamp(formation), pd.Timestamp(cutoff))
    return int(((sessions > pd.Timestamp(formation)) & (sessions <= pd.Timestamp(cutoff))).sum())
