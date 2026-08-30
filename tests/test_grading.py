from mtr_scanner.retest import classify_grade


def test_a_plus_has_priority_even_below_a_close_location():
    assert classify_grade(
        sma200_slope_percentile=0.50,
        pullback_from_peak_atr=-0.25,
        event_body_atr=0.25,
        event_body_return=0.001,
        close_location=0.71,
    ) == "A+"


def test_a_and_b_are_mutually_exclusive():
    common = {
        "sma200_slope_percentile": 0.49,
        "pullback_from_peak_atr": -0.10,
        "event_body_atr": 0.40,
        "event_body_return": 0.02,
    }
    assert classify_grade(**common, close_location=0.75) == "A"
    assert classify_grade(**common, close_location=0.749999) == "B"
