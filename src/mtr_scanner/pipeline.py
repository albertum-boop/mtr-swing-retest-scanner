from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .alerts import GRADE_ORDER, send_signal_email
from .config import StrategyConfig
from .features import build_monthly_candidates
from .market_calendar import active_formation_date, latest_completed_session, session_number_after
from .market_data import download_histories, load_price_directory
from .retest import scan_candidate
from .storage import read_json, write_json
from .universe import load_universe

ROOT = Path(__file__).resolve().parents[2]


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _sort_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        signals,
        key=lambda row: (
            GRADE_ORDER.get(row.get("grade", "B"), 9),
            row.get("event_date", ""),
            row.get("ticker", ""),
        ),
    )


def _new_alert_candidates(
    signals: list[dict[str, Any]], *, cutoff: pd.Timestamp, sent_ids: set[str]
) -> list[dict[str, Any]]:
    """Return only signals confirmed on the just-completed session.

    The dashboard keeps every signal from the active cycle, but a first deployment or
    a backfill must not email a setup that was confirmed days or weeks earlier.
    """

    cutoff_iso = pd.Timestamp(cutoff).date().isoformat()
    return [
        signal
        for signal in signals
        if signal["signal_id"] not in sent_ids and signal.get("event_date") == cutoff_iso
    ]


def _load_or_build_formation(
    *,
    root: Path,
    formation_date: pd.Timestamp,
    cutoff: pd.Timestamp,
    prices_dir: Path | None,
    config: StrategyConfig,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    state_path = root / "state" / "formations" / f"{formation_date.date().isoformat()}.json"
    existing = read_json(state_path)
    if existing and existing.get("method_version") == config.method_version:
        return existing, {}
    universe = load_universe(root / "config" / "ticker_database.json")
    start = formation_date - pd.Timedelta(days=560)
    if prices_dir:
        prices = load_price_directory(prices_dir, universe, start=start, cutoff=cutoff)
        errors: dict[str, str] = {}
    else:
        prices, errors = download_histories(universe, start=start, cutoff=cutoff)
    candidates, stats = build_monthly_candidates(prices, formation_date, config)
    if stats["observed"] < 500 or stats.get("coverage", 0) < 0.60:
        raise RuntimeError(
            f"Cobertura insuficiente para congelar la formación: {stats}. "
            "El estado anterior, si existe, no se sobrescribe."
        )
    payload = {
        "method_version": config.method_version,
        "generated_at": _iso_now(),
        "formation_date": formation_date.date().isoformat(),
        "parameters": config.as_dict(),
        "stats": {**stats, "download_errors": len(errors)},
        "candidates": candidates,
    }
    write_json(state_path, payload)
    return payload, prices


def run_pipeline(
    *,
    root: Path = ROOT,
    as_of: str | None = None,
    prices_dir: Path | None = None,
    send_alerts: bool = False,
) -> dict[str, Any]:
    config = StrategyConfig()
    cutoff = pd.Timestamp(as_of).normalize() if as_of else latest_completed_session()
    formation_date = active_formation_date(cutoff)
    formation, cached_prices = _load_or_build_formation(
        root=root,
        formation_date=formation_date,
        cutoff=cutoff,
        prices_dir=prices_dir,
        config=config,
    )
    candidates = formation["candidates"]
    candidate_tickers = [row["ticker"] for row in candidates]
    if prices_dir:
        prices = cached_prices or load_price_directory(
            prices_dir,
            candidate_tickers,
            start=formation_date - pd.Timedelta(days=45),
            cutoff=cutoff,
        )
    else:
        prices, candidate_errors = download_histories(
            candidate_tickers,
            start=formation_date - pd.Timedelta(days=45),
            cutoff=cutoff,
            batch_size=40,
        )
        formation["candidate_download_errors"] = candidate_errors

    scans = []
    current_signals: list[dict[str, Any]] = []
    for candidate in candidates:
        ticker = candidate["ticker"]
        raw = prices.get(ticker)
        if raw is None:
            scans.append({"ticker": ticker, "status": "missing_prices", "signal": None})
            continue
        result = scan_candidate(candidate, raw, cutoff=cutoff, config=config)
        scans.append(result)
        if result.get("signal"):
            current_signals.append(result["signal"])

    history_path = root / "public" / "data" / "history.json"
    history_payload = read_json(history_path, {"signals": []})
    history_by_id = {row["signal_id"]: row for row in history_payload.get("signals", [])}
    for signal in current_signals:
        history_by_id[signal["signal_id"]] = signal
    all_history = _sort_signals(list(history_by_id.values()))

    sent_path = root / "state" / "sent_signals.json"
    sent_payload = read_json(sent_path, {"signal_ids": []})
    sent_ids = set(sent_payload.get("signal_ids", []))
    pending = _new_alert_candidates(current_signals, cutoff=cutoff, sent_ids=sent_ids)
    alert_result = {"status": "disabled", "sent": 0}
    if send_alerts:
        alert_result = send_signal_email(pending)
        if alert_result.get("status") == "sent":
            sent_ids.update(signal["signal_id"] for signal in pending)
            write_json(sent_path, {"updated_at": _iso_now(), "signal_ids": sorted(sent_ids)})

    status_counts: dict[str, int] = {}
    for result in scans:
        status = result["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    current_payload = {
        "method_version": config.method_version,
        "generated_at": _iso_now(),
        "cutoff": cutoff.date().isoformat(),
        "formation_date": formation_date.date().isoformat(),
        "session_after_formation": session_number_after(formation_date, cutoff),
        "formation_stats": formation["stats"],
        "scan_status": status_counts,
        "signals": _sort_signals(current_signals),
        "alert_scope": "signals confirmed on cutoff session only",
        "alert_result": alert_result,
    }
    write_json(root / "public" / "data" / "current.json", current_payload)
    write_json(
        history_path,
        {
            "method_version": config.method_version,
            "updated_at": _iso_now(),
            "signals": all_history,
        },
    )
    write_json(
        root / "state" / "last_run.json",
        {
            "status": "ok",
            "generated_at": current_payload["generated_at"],
            "cutoff": current_payload["cutoff"],
            "formation_date": current_payload["formation_date"],
            "signals": len(current_signals),
            "pending_alerts": len(pending),
            "alert_result": alert_result,
        },
    )
    return current_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="MTR Swing Retest v1.0 daily scanner")
    parser.add_argument("--as-of", help="Fecha de corte YYYY-MM-DD; por defecto, última sesión completa")
    parser.add_argument("--prices-dir", type=Path, help="Directorio OHLCV local para auditoría")
    parser.add_argument("--send-alerts", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run_pipeline(
        root=args.root.resolve(),
        as_of=args.as_of,
        prices_dir=args.prices_dir.resolve() if args.prices_dir else None,
        send_alerts=args.send_alerts,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
