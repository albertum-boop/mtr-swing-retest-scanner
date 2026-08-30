from __future__ import annotations

import numpy as np
import pandas as pd

from mtr_scanner.retest import scan_candidate


def candidate() -> dict[str, object]:
    return {
        "ticker": "TEST",
        "formation_date": "2026-07-31",
        "formation_close": 100.0,
        "atr_abs20": 4.0,
        "prior_adj_volume20": 1000.0,
        "adv20": 25_000_000.0,
        "rank_pct": 0.99,
        "swing_score": 0.90,
        "swing_rank_pct": 0.95,
        "mom12_1_pct": 0.96,
        "atr_pct20_pct": 0.92,
        "return_volume_corr20_pct": 0.82,
        "sma200_slope20_pct": 0.60,
    }


def prices(event_day: int = 2, event_volume: float = 700.0) -> pd.DataFrame:
    dates = pd.bdate_range("2026-07-31", periods=14)
    close = np.array([100, 101.5, 101.5, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113], float)
    open_ = close - 0.5
    high = close + 0.8
    low = close - 1.0
    volume = np.full(len(dates), 1000.0)
    # Day 1: intervening expansion. Peak 102.2 gives a shallow A+ pullback.
    high[1], low[1], open_[1], close[1] = 102.2, 100.0, 100.5, 101.6
    # Day 2: valid retest unless the caller asks to defer it.
    high[2], low[2], open_[2], close[2], volume[2] = 102.0, 99.5, 100.0, 101.5, event_volume
    if event_day == 3:
        # Day 2 touches but fails volume; day 3 is the first simultaneous valid retest.
        volume[2] = 900.0
        high[3], low[3], open_[3], close[3], volume[3] = 102.0, 99.5, 100.0, 101.5, event_volume
    return pd.DataFrame(
        {
            "Open": open_, "High": high, "Low": low, "Close": close,
            "Adj Close": close, "Volume": volume,
        },
        index=dates,
    )


def test_valid_a_plus_retest_and_executable_outcomes():
    result = scan_candidate(candidate(), prices())
    signal = result["signal"]
    assert result["status"] == "signal"
    assert signal["event_day"] == 2
    assert signal["grade"] == "A+"
    assert signal["entry_date"] == "2026-08-05"
    assert signal["entry_open"] == 102.5
    assert signal["mfe5"] >= signal["r5"]
    assert signal["mae5"] <= signal["r5"]


def test_failed_first_contact_cannot_be_revived_later():
    result = scan_candidate(candidate(), prices(event_day=3, event_volume=700.0))
    assert result["signal"] is None
    assert result["status"] == "rejected_first_contact"
    assert result["rejections"][0]["failed"] == ["volume_contraction"]


def test_volume_threshold_is_strict():
    result = scan_candidate(candidate(), prices(event_volume=800.0), cutoff="2026-08-04")
    assert result["signal"] is None
    assert result["status"] == "rejected_first_contact"
    assert "volume_contraction" in result["rejections"][0]["failed"]


def test_same_bar_cannot_create_expansion_and_retest():
    frame = prices()
    # Remove day-1 expansion. Day 2 expands and touches, but cannot be the retest.
    frame.loc[pd.Timestamp("2026-08-03"), "High"] = 100.5
    frame.loc[pd.Timestamp("2026-08-04"), ["High", "Low", "Open", "Close", "Adj Close", "Volume"]] = [102.0, 99.5, 100.0, 101.5, 101.5, 700]
    result = scan_candidate(candidate(), frame, cutoff="2026-08-04")
    assert result["signal"] is None
    assert result["status"] == "expanded_waiting_retest"
