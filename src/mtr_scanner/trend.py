from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

TREND_POLICY_VERSION = "MTR-TrendGate-v1.0"
OPERATIONAL_VERSION = "MTR-Multitemporal-v2.1"
TREND_CHECK_LABELS = {
    "price_above_sma50": "Cierre por encima de SMA50",
    "sma50_above_sma200": "SMA50 por encima de SMA200",
    "sma50_rising20": "SMA50 ascendente en 20 sesiones",
    "sma200_rising20": "SMA200 ascendente en 20 sesiones",
    "drawdown20_within_limit": "Caída desde máximo de cierre de 20 sesiones ≤15%",
}
TREND_PARAMETERS = {
    "fast_sma_sessions": 50,
    "slow_sma_sessions": 200,
    "slope_sessions": 20,
    "drawdown_sessions": 20,
    "max_drawdown": 0.15,
    "evaluated_at": "event_close",
}


def trend_snapshot(raw: pd.DataFrame, event_date: str) -> dict[str, Any]:
    """Evaluate only closes available at confirmation; fail closed on missing data.

    The fixed policy describes intact trend structure, not a forecast or a
    fitted profitability model. Future prices never enter any calculation.
    """
    result: dict[str, Any] = {
        "policy_version": TREND_POLICY_VERSION,
        "as_of": event_date,
        "status": "unknown",
        "passed": False,
        "checks": {},
        "failed_conditions": [],
    }
    data = raw.copy()
    if "Date" in data:
        data.index = pd.to_datetime(data.pop("Date"))
    data.index = pd.to_datetime(data.index)
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)
    data = data.sort_index().loc[lambda d: d.index <= pd.Timestamp(event_date)]
    column = "Adj Close" if "Adj Close" in data else "AdjClose"
    if column not in data or data.index.duplicated().any():
        return {**result, "reason": "invalid_close_series"}
    close = pd.to_numeric(data[column], errors="coerce")
    if (
        len(close) < 220
        or close.index[-1] != pd.Timestamp(event_date)
        or not np.isfinite(close.iloc[-220:]).all()
        or not close.iloc[-220:].gt(0).all()
    ):
        return {**result, "reason": "missing_event_or_220_valid_sessions"}
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    last = float(close.iloc[-1])
    fast, slow = float(sma50.iloc[-1]), float(sma200.iloc[-1])
    slope50 = fast / float(sma50.iloc[-21]) - 1
    slope200 = slow / float(sma200.iloc[-21]) - 1
    peak20 = float(close.iloc[-20:].max())
    drawdown20 = last / peak20 - 1
    checks = {
        "price_above_sma50": last > fast,
        "sma50_above_sma200": fast > slow,
        "sma50_rising20": slope50 > 0,
        "sma200_rising20": slope200 > 0,
        "drawdown20_within_limit": drawdown20 >= -TREND_PARAMETERS["max_drawdown"],
    }
    passed = all(checks.values())
    return {
        **result,
        "status": "pass" if passed else "rejected",
        "passed": passed,
        "checks": checks,
        "failed_conditions": [key for key, value in checks.items() if not value],
        "close": last,
        "sma50": fast,
        "sma200": slow,
        "sma50_slope20": slope50,
        "sma200_slope20": slope200,
        "max_close20": peak20,
        "drawdown20": drawdown20,
        "return20": last / float(close.iloc[-21]) - 1,
    }


def annotate_trend(signal: dict[str, Any], raw: pd.DataFrame | None) -> dict[str, Any]:
    result = dict(signal)
    snapshot = signal.get("trend_gate")
    if raw is not None:
        evaluated = trend_snapshot(raw, str(signal["event_date"]))
        if (
            evaluated["status"] != "unknown"
            or not snapshot
            or snapshot.get("policy_version") != TREND_POLICY_VERSION
            or snapshot.get("as_of") != signal["event_date"]
        ):
            snapshot = evaluated
    elif not snapshot or snapshot.get("policy_version") != TREND_POLICY_VERSION:
        snapshot = {
            "policy_version": TREND_POLICY_VERSION,
            "as_of": str(signal["event_date"]),
            "status": "unknown",
            "passed": False,
            "checks": {},
            "failed_conditions": [],
            "reason": "historical_prices_unavailable",
        }
    result.update(operational_version=OPERATIONAL_VERSION, trend_gate=snapshot)
    return result


def apply_operational_cooldown(
    signals: Iterable[dict[str, Any]], *, cooldown_sessions: int = 10
) -> list[dict[str, Any]]:
    """Recompute eligibility after the gate without rewriting v2.0 actionability.

    A blocked trend never starts/extends cooldown. Previously suppressed raw
    events may become eligible when the earlier event fails the new gate.
    """
    from .market_calendar import session_ordinals

    rows = [dict(row) for row in signals]
    ordinals = session_ordinals([pd.Timestamp(row["event_date"]) for row in rows])
    last: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda s: (s["event_date"], s["ticker"])):
        gate = row.get("trend_gate") or {}
        eligible = (
            gate.get("policy_version") == TREND_POLICY_VERSION
            and gate.get("as_of") == row["event_date"]
            and gate.get("passed") is True
        )
        row["operational_actionable"] = eligible
        row["operational_suppressed_by_cooldown"] = None
        row["operational_cooldown_gap_sessions"] = None
        row["operational_reason"] = None if eligible else "trend_" + gate.get("status", "unknown")
        previous = last.get(row["ticker"])
        if eligible and previous is not None:
            gap = ordinals[row["event_date"]] - ordinals[previous["event_date"]]
            if gap <= cooldown_sessions:
                row.update(
                    operational_actionable=False,
                    operational_reason="cooldown",
                    operational_suppressed_by_cooldown=previous["signal_id"],
                    operational_cooldown_gap_sessions=gap,
                )
        if row["operational_actionable"]:
            last[row["ticker"]] = row
    return rows


def is_operationally_actionable(signal: dict[str, Any]) -> bool:
    gate = signal.get("trend_gate") or {}
    return (
        signal.get("operational_version") == OPERATIONAL_VERSION
        and signal.get("operational_actionable") is True
        and gate.get("policy_version") == TREND_POLICY_VERSION
        and gate.get("as_of") == signal.get("event_date")
        and gate.get("passed") is True
    )
