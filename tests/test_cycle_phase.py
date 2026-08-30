from mtr_scanner.config import StrategyConfig
from mtr_scanner.pipeline import _cycle_phase


def test_cycle_phase_matches_frozen_retest_window():
    config = StrategyConfig()
    assert _cycle_phase(0, config) == "before_retest_window"
    assert _cycle_phase(1, config) == "before_retest_window"
    assert _cycle_phase(2, config) == "retest_window_open"
    assert _cycle_phase(5, config) == "retest_window_open"
    assert _cycle_phase(6, config) == "retest_window_closed"
