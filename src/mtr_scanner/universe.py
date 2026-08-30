from __future__ import annotations

import json
from pathlib import Path


def load_universe(database_path: Path) -> list[str]:
    """Return unique active stock symbols from the ETF holdings database.

    ETF keys themselves are deliberately not returned. Symbols with dots are
    normalised to Yahoo's dash convention by the source database.
    """

    with database_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    etfs = payload.get("etfs")
    if not isinstance(etfs, dict):
        raise TypeError("ticker_database.json no contiene el objeto 'etfs'")
    symbols: list[str] = []
    seen: set[str] = set()
    for info in etfs.values():
        for raw in info.get("holdings", []):
            symbol = str(raw).strip().upper().replace(".", "-")
            if symbol and symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
    if not symbols:
        raise ValueError("El universo de acciones está vacío")
    return sorted(symbols)
