import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mtr_scanner.config import StrategyConfig
from mtr_scanner.lm2 import LM2StrategyConfig
from mtr_scanner.pipeline import _scan_source_candidates
from mtr_scanner.trend import (
    OPERATIONAL_VERSION,
    TREND_POLICY_VERSION,
    annotate_trend,
    apply_operational_cooldown,
    is_operationally_actionable,
    trend_snapshot,
)
from mtr_scanner.weekly import WeeklyStrategyConfig

ROOT = Path(__file__).resolve().parents[1]


def rising_prices():
    return pd.DataFrame({"Adj Close": np.linspace(50, 150, 240)}, index=pd.bdate_range("2025-01-01", periods=240))


def signal(date, *, ticker="TEST", passed=True):
    return {
        "signal_id": f"test:{ticker}:{date}", "ticker": ticker, "event_date": date,
        "grade": "A", "operational_version": OPERATIONAL_VERSION,
        "trend_gate": {"policy_version": TREND_POLICY_VERSION, "as_of": date, "status": "pass" if passed else "rejected", "passed": passed},
    }


def test_gate_accepts_rising_structure_and_is_invariant_to_future_prices():
    raw = rising_prices()
    date = raw.index[-1].date().isoformat()
    before = trend_snapshot(raw, date)
    future = pd.DataFrame({"Adj Close": [0.01, 1e9]}, index=pd.bdate_range(raw.index[-1] + pd.Timedelta(days=1), periods=2))
    assert before["passed"] is True
    assert trend_snapshot(pd.concat([raw, future]), date) == before


def test_short_history_missing_event_and_nan_fail_closed():
    raw = rising_prices()
    date = raw.index[-1].date().isoformat()
    for bad in [raw.tail(219), raw.iloc[:-1], raw.assign(**{"Adj Close": np.nan})]:
        gate = trend_snapshot(bad, date)
        assert gate["status"] == "unknown"
        assert gate["passed"] is False
    assert not is_operationally_actionable({"actionable": True})


def test_cached_event_snapshot_survives_shorter_subsequent_download():
    raw = rising_prices()
    date = raw.index[-1].date().isoformat()
    evaluated = annotate_trend(signal(date), raw)
    assert annotate_trend(evaluated, raw.tail(10))["trend_gate"] == evaluated["trend_gate"]


@pytest.mark.parametrize("ticker,drawdown", [("ALM", -0.292887), ("HUT", -0.162649)])
def test_october_signals_fail_before_entry_despite_rising_sma200(ticker, drawdown):
    raw = pd.read_csv(ROOT / "tests/fixtures/october_2026_trend_closes.csv")
    raw = raw[raw.ticker.eq(ticker)]
    gate = trend_snapshot(raw, "2026-10-05")
    assert not gate["passed"]
    assert gate["checks"]["sma200_rising20"] is True
    assert not gate["checks"]["price_above_sma50"]
    assert not gate["checks"]["sma50_rising20"]
    assert gate["drawdown20"] == pytest.approx(drawdown, abs=1e-6)


def test_blocked_trend_does_not_start_cooldown_and_base_history_is_preserved():
    first = signal("2026-08-03", passed=False)
    second = {**signal("2026-08-17"), "actionable": False}
    third = signal("2026-08-18")
    result = apply_operational_cooldown([first, second, third])
    assert [s["operational_actionable"] for s in result] == [False, True, False]
    assert result[1]["actionable"] is False  # original v2.0 field is not rewritten
    assert result[2]["operational_suppressed_by_cooldown"] == second["signal_id"]
    assert first.get("operational_actionable") is None  # inputs are not mutated


def test_pipeline_preserves_real_alm_retest_but_blocks_its_entry():
    frame = pd.read_csv(ROOT / "tests/fixtures/october_2026_trend_closes.csv")
    frame = frame[frame.ticker.eq("ALM")].set_index(pd.to_datetime(frame[frame.ticker.eq("ALM")].Date))
    frame["Close"] = frame["Adj Close"]
    frame["Open"] = frame.Close
    frame["High"] = frame.Close + 0.1
    frame["Low"] = frame.Close - 0.1
    frame["Volume"] = 4_000_000
    for date, values in {
        "2026-10-01": [12.97, 13.36, 12.76, 13.18, 6606100],
        "2026-10-02": [13.20, 13.77, 13.19, 13.40, 5723700],
        "2026-10-05": [13.23, 13.67, 12.95, 13.52, 3876900],
    }.items():
        frame.loc[pd.Timestamp(date), ["Open", "High", "Low", "Close", "Volume"]] = values
        frame.loc[pd.Timestamp(date), "Adj Close"] = values[3]
    frame = frame.drop(columns=["Date", "ticker"])
    formation = json.loads((ROOT / "state/formations/2026-09-30.json").read_text())
    formation["candidates"] = [c for c in formation["candidates"] if c["ticker"] == "ALM"]
    scans, monitors, signals = _scan_source_candidates(
        source="monthly", formation=formation, prices={"ALM": frame},
        cutoff=pd.Timestamp("2026-10-05"), base_config=StrategyConfig(),
        weekly_config=WeeklyStrategyConfig(), lm2_config=LM2StrategyConfig(),
    )
    assert signals[0]["grade"] == "A"
    assert signals[0]["event_date"] == "2026-10-05"
    assert signals[0]["entry_open"] is None
    assert monitors[0]["status"] == "rejected_current_trend"
    assert not apply_operational_cooldown(signals)[0]["operational_actionable"]
    assert scans[0]["status"] == "rejected_current_trend"
