"""MTR Multitemporal Swing Retest Scanner.

The monthly v1.0 contract remains available while v1.2 unites it with the
frozen LM2 and weekly crossing branches.
"""

from .config import StrategyConfig
from .features import build_monthly_candidates, build_ranked_candidates
from .lm2 import LM2_METHOD_VERSION
from .retest import scan_candidate
from .weekly import MULTITEMPORAL_METHOD_VERSION, WEEKLY_METHOD_VERSION

__all__ = [
    "LM2_METHOD_VERSION",
    "MULTITEMPORAL_METHOD_VERSION",
    "WEEKLY_METHOD_VERSION",
    "StrategyConfig",
    "build_monthly_candidates",
    "build_ranked_candidates",
    "scan_candidate",
]
__version__ = "1.2.0"
