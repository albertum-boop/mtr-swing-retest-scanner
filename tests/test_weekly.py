from mtr_scanner.weekly import apply_weekly_grade, weekly_crossing_candidates


def _candidate(**updates):
    candidate = {
        "ticker": "TEST",
        "mom12_1_pct": 0.80,
        "atr_pct20_pct": 0.50,
        "swing_rank_pct": 0.90,
        "relative_volume5_20": 0.10,
    }
    candidate.update(updates)
    return candidate


def _result():
    return {
        "status": "signal",
        "signal": {"grade": "A", "close_vs_level_atr": 0.30},
        "monitor": {"status": "signal"},
    }


def test_weekly_candidates_are_new_crossings_only():
    current = [{"ticker": "OLD"}, {"ticker": "NEW"}]
    previous = [{"ticker": "OLD"}, {"ticker": "GONE"}]

    result = weekly_crossing_candidates(current, previous)

    assert [row["ticker"] for row in result] == ["NEW"]
    assert result[0]["formation_frequency"] == "weekly"


def test_weekly_a_plus_requires_three_quality_points_and_volume():
    result = apply_weekly_grade(_result(), _candidate())

    assert result["signal"]["grade"] == "A+"
    assert result["signal"]["weekly_quality_points"] == 4


def test_weekly_b_is_computed_but_never_published_as_signal():
    candidate = _candidate(mom12_1_pct=0.20, atr_pct20_pct=0.95, swing_rank_pct=0.30)
    result = apply_weekly_grade(_result(), candidate)

    assert result["status"] == "rejected_weekly_grade"
    assert result["signal"] is None
    assert result["rejected_signal"]["grade"] == "B"
    assert result["monitor"]["status"] == "rejected_weekly_grade"
