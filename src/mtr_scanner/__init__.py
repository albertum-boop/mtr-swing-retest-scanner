"""MTR Swing Retest Scanner.

The public API is intentionally small: the frozen strategy configuration,
monthly candidate builder and retest scanner are the three stable contracts.
"""

from .config import StrategyConfig
from .features import build_monthly_candidates
from .retest import scan_candidate

__all__ = ["StrategyConfig", "build_monthly_candidates", "scan_candidate"]
__version__ = "1.0.0"
