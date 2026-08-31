from mtr_scanner.lm2 import apply_lm2_grade, lm2_grade_details


def _candidate(**updates):
    candidate = {
        "formation_gap": 0.01,
        "atr_pct20_pct": 0.90,
        "sma200_slope20": 0.08,
    }
    candidate.update(updates)
    return candidate


def _result():
    return {
        "status": "signal",
        "signal": {"grade": "A"},
        "monitor": {"status": "signal"},
    }


def test_lm2_a_plus_requires_all_three_frozen_points():
    details = lm2_grade_details(_candidate())

    assert details["lm2_grade"] == "A+"
    assert details["lm2_quality_points"] == 3


def test_lm2_a_requires_exactly_two_points():
    details = lm2_grade_details(_candidate(formation_gap=-0.001))

    assert details["lm2_grade"] == "A"
    assert details["lm2_quality_points"] == 2


def test_lm2_b_is_audited_in_monitor_but_never_published():
    candidate = _candidate(
        formation_gap=-0.01,
        atr_pct20_pct=0.50,
        sma200_slope20=0.01,
    )
    result = apply_lm2_grade(_result(), candidate)

    assert result["status"] == "rejected_lm2_grade"
    assert result["signal"] is None
    assert result["rejected_signal"]["grade"] == "B"
    assert result["monitor"]["lm2_quality_points"] == 0
    assert result["monitor"]["status"] == "rejected_lm2_grade"
