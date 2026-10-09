"""MTR Multitemporal Swing Retest Scanner.

The frozen v2.0 pattern contract remains available for audit. Operational
v2.1 additionally requires an intact current trend at the event close.
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
__version__ = "2.1.0"
