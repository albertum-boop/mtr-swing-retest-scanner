from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StrategyConfig:
    """Frozen MTR Swing Retest v2.0 candidate parameters.

    Changing any field creates a different research branch. Production code
    serialises this object with every formation state and every signal.
    """

    method_version: str = "MTR-Swing-Retest-v2.0"
    min_price: float = 5.0
    min_adv20_usd: float = 10_000_000.0
    momentum_lookback_sessions: int = 252
    momentum_skip_sessions: int = 21
    d10_rank_threshold: float = 0.90
    swing_rank_threshold: float = 0.80
    swing_atr_weight: float = 1 / 3
    swing_momentum_weight: float = 1 / 3
    swing_return_volume_weight: float = 1 / 3
    atr_sessions: int = 20
    prior_volume_sessions: int = 20
    expansion_atr: float = 0.25
    contact_band_atr: float = 0.25
    first_retest_day: int = 2
    last_retest_day: int = 5
    min_close_location: float = 0.70
    max_close_extension_atr: float = 0.75
    max_event_volume_ratio: float = 0.80
    a_plus_min_sma200_slope_percentile: float = 0.50
    a_plus_min_pullback_from_peak_atr: float = -0.25
    a_plus_min_bull_body_atr: float = 0.25
    a_min_close_location: float = 0.75
    cooldown_sessions: int = 10

    def as_dict(self) -> dict[str, object]:
        return asdict(self)
