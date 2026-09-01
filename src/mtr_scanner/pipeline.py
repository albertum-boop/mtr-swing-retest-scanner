from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .alerts import GRADE_ORDER, send_signal_email
from .config import StrategyConfig
from .features import build_ranked_candidates
from .lm2 import (
    LM2_METHOD_VERSION,
    LM2StrategyConfig,
    apply_lm2_grade,
)
from .market_calendar import (
    active_formation_date,
    active_lm2_formation_date,
    latest_completed_session,
    previous_weekly_formation_date,
    session_number_after,
    weekly_formation_dates,
)
from .market_data import download_histories, load_price_directory
from .retest import candidate_monitor, scan_candidate
from .signals import (
    annotate_signal,
    apply_signal_cooldown,
    merge_signal_records,
    signal_key,
)
from .storage import read_json, write_json
from .universe import load_universe
from .weekly import (
    MULTITEMPORAL_METHOD_VERSION,
    WEEKLY_METHOD_VERSION,
    WeeklyStrategyConfig,
    apply_weekly_grade,
    weekly_crossing_candidates,
)

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
    """Return signals confirmed on the just-completed session and never sent before."""

    cutoff_iso = pd.Timestamp(cutoff).date().isoformat()
    return [
        signal
        for signal in signals
        if signal["signal_id"] not in sent_ids
        and signal.get("event_date") == cutoff_iso
        and signal.get("actionable", True)
    ]


def _cycle_phase(session_after_formation: int, config: StrategyConfig) -> str:
    if session_after_formation < config.first_retest_day:
        return "before_retest_window"
    if session_after_formation <= config.last_retest_day:
        return "retest_window_open"
    return "retest_window_closed"


def _monthly_state_path(root: Path, formation_date: pd.Timestamp) -> Path:
    return root / "state" / "formations" / f"{formation_date.date().isoformat()}.json"


def _weekly_state_path(root: Path, formation_date: pd.Timestamp) -> Path:
    return root / "state" / "weekly_formations" / f"{formation_date.date().isoformat()}.json"


def _lm2_state_path(root: Path, formation_date: pd.Timestamp) -> Path:
    return root / "state" / "lm2_formations" / f"{formation_date.date().isoformat()}.json"


def _valid_state(path: Path, method_version: str) -> dict[str, Any] | None:
    state = read_json(path)
    if state and state.get("method_version") == method_version:
        return state
    return None


def _load_universe_prices(
    *,
    root: Path,
    start: pd.Timestamp,
    cutoff: pd.Timestamp,
    prices_dir: Path | None,
) -> tuple[dict[str, pd.DataFrame], dict[str, str], int]:
    universe = load_universe(root / "config" / "ticker_database.json")
    if prices_dir:
        prices = load_price_directory(prices_dir, universe, start=start, cutoff=cutoff)
        errors = {
            ticker: "No existe un CSV local válido"
            for ticker in universe
            if ticker not in prices
        }
    else:
        prices, errors = download_histories(universe, start=start, cutoff=cutoff)
    return prices, errors, len(universe)


def _coverage_guard(stats: dict[str, Any], label: str) -> None:
    if stats["observed"] < 500 or stats.get("coverage", 0) < 0.60:
        raise RuntimeError(
            f"Cobertura insuficiente para congelar {label}: {stats}. "
            "El estado anterior, si existe, no se sobrescribe."
        )


def _build_monthly_state(
    *,
    root: Path,
    formation_date: pd.Timestamp,
    prices: dict[str, pd.DataFrame],
    errors: dict[str, str],
    config: StrategyConfig,
) -> dict[str, Any]:
    candidates, stats = build_ranked_candidates(prices, formation_date, config)
    _coverage_guard(stats, "la formación mensual")
    payload = {
        "method_version": config.method_version,
        "formation_frequency": "monthly",
        "generated_at": _iso_now(),
        "formation_date": formation_date.date().isoformat(),
        "parameters": config.as_dict(),
        "stats": {**stats, "download_errors": len(errors)},
        "candidates": candidates,
    }
    write_json(_monthly_state_path(root, formation_date), payload)
    return payload


def _build_lm2_state(
    *,
    root: Path,
    formation_date: pd.Timestamp,
    prices: dict[str, pd.DataFrame],
    errors: dict[str, str],
    base_config: StrategyConfig,
    lm2_config: LM2StrategyConfig,
) -> dict[str, Any]:
    candidates, stats = build_ranked_candidates(prices, formation_date, base_config)
    _coverage_guard(stats, "la formación LM2")
    payload = {
        "method_version": LM2_METHOD_VERSION,
        "base_retest_method_version": base_config.method_version,
        "formation_frequency": "lm2",
        "generated_at": _iso_now(),
        "formation_date": formation_date.date().isoformat(),
        "parameters": {
            "base": base_config.as_dict(),
            "lm2_grade": lm2_config.as_dict(),
            "formation_rule": "penultimate_nyse_session_of_calendar_month",
        },
        "stats": {**stats, "download_errors": len(errors)},
        "candidates": candidates,
    }
    write_json(_lm2_state_path(root, formation_date), payload)
    return payload


def _load_or_build_formation(
    *,
    root: Path,
    formation_date: pd.Timestamp,
    cutoff: pd.Timestamp,
    prices_dir: Path | None,
    config: StrategyConfig,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    """Backward-compatible monthly state loader used by the original scanner tests."""

    existing = _valid_state(_monthly_state_path(root, formation_date), config.method_version)
    if existing:
        return existing, {}
    prices, errors, _ = _load_universe_prices(
        root=root,
        start=formation_date - pd.Timedelta(days=560),
        cutoff=cutoff,
        prices_dir=prices_dir,
    )
    state = _build_monthly_state(
        root=root,
        formation_date=formation_date,
        prices=prices,
        errors=errors,
        config=config,
    )
    return state, prices


def _build_weekly_states(
    *,
    root: Path,
    formation_dates: list[pd.Timestamp],
    prices: dict[str, pd.DataFrame],
    errors: dict[str, str],
    base_config: StrategyConfig,
    weekly_config: WeeklyStrategyConfig,
) -> list[dict[str, Any]]:
    selection_cache: dict[pd.Timestamp, tuple[list[dict[str, Any]], dict[str, Any]]] = {}

    def selection(date: pd.Timestamp) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        date = pd.Timestamp(date).normalize()
        if date not in selection_cache:
            selection_cache[date] = build_ranked_candidates(prices, date, base_config)
        return selection_cache[date]

    states: list[dict[str, Any]] = []
    for formation_date in formation_dates:
        existing = _valid_state(_weekly_state_path(root, formation_date), WEEKLY_METHOD_VERSION)
        if existing:
            states.append(existing)
            continue

        current_selected, stats = selection(formation_date)
        _coverage_guard(stats, f"la formación semanal {formation_date.date().isoformat()}")
        previous_date = previous_weekly_formation_date(formation_date)
        previous_state = _valid_state(
            _weekly_state_path(root, previous_date), WEEKLY_METHOD_VERSION
        )
        if previous_state:
            previous_selected = previous_state.get("selected", [])
        else:
            previous_selected, previous_stats = selection(previous_date)
            _coverage_guard(
                previous_stats,
                f"la comparación semanal {previous_date.date().isoformat()}",
            )
        crossings = weekly_crossing_candidates(current_selected, previous_selected)
        payload = {
            "method_version": WEEKLY_METHOD_VERSION,
            "base_retest_method_version": base_config.method_version,
            "formation_frequency": "weekly",
            "generated_at": _iso_now(),
            "formation_date": formation_date.date().isoformat(),
            "comparison_date": previous_date.date().isoformat(),
            "parameters": {
                "base": base_config.as_dict(),
                "weekly_grade": weekly_config.as_dict(),
                "crossing_rule": "selected_now_and_not_selected_at_previous_weekly_close",
            },
            "stats": {
                **stats,
                "previous_selected": len(previous_selected),
                "weekly_crossings": len(crossings),
                "download_errors": len(errors),
            },
            "selected_tickers": sorted(str(row["ticker"]) for row in current_selected),
            "selected": current_selected,
            "candidates": crossings,
        }
        write_json(_weekly_state_path(root, formation_date), payload)
        states.append(payload)
    return states


def _decorate_monitor(
    monitor: dict[str, Any],
    *,
    source: str,
    formation_date: str,
    cutoff: pd.Timestamp,
) -> dict[str, Any]:
    result = dict(monitor)
    result.update(
        candidate_id=f"{source}:{formation_date}:{monitor['ticker']}",
        source=source,
        formation_frequency=source,
        session_after_formation=session_number_after(pd.Timestamp(formation_date), cutoff),
    )
    return result


def _scan_source_candidates(
    *,
    source: str,
    formation: dict[str, Any],
    prices: dict[str, pd.DataFrame],
    cutoff: pd.Timestamp,
    base_config: StrategyConfig,
    weekly_config: WeeklyStrategyConfig,
    lm2_config: LM2StrategyConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    scans: list[dict[str, Any]] = []
    monitors: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    formation_date = str(formation["formation_date"])
    for candidate in formation.get("candidates", []):
        ticker = str(candidate["ticker"])
        raw = prices.get(ticker)
        if raw is None:
            monitor = candidate_monitor(candidate, base_config)
            monitor.update(
                status="missing_prices",
                next_step="No se puede evaluar: faltan precios posteriores a la formación",
            )
            result = {"ticker": ticker, "status": "missing_prices", "signal": None}
        else:
            result = scan_candidate(candidate, raw, cutoff=cutoff, config=base_config)
            monitor = result["monitor"]
            if source == "weekly":
                result = apply_weekly_grade(result, candidate, weekly_config)
                monitor = result["monitor"]
            elif source == "lm2":
                result = apply_lm2_grade(result, candidate, lm2_config)
                monitor = result["monitor"]

        monitor = _decorate_monitor(
            monitor,
            source=source,
            formation_date=formation_date,
            cutoff=cutoff,
        )
        result.update(source=source, formation_date=formation_date, monitor=monitor)
        scans.append(result)
        monitors.append(monitor)
        if result.get("signal"):
            signals.append(annotate_signal(result["signal"], source))
    return scans, monitors, signals


def _status_counts(scans: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for scan in scans:
        status = str(scan["status"])
        result[status] = result.get(status, 0) + 1
    return result


def run_pipeline(
    *,
    root: Path = ROOT,
    as_of: str | None = None,
    prices_dir: Path | None = None,
    send_alerts: bool = False,
) -> dict[str, Any]:
    base_config = StrategyConfig()
    weekly_config = WeeklyStrategyConfig()
    lm2_config = LM2StrategyConfig()
    cutoff = pd.Timestamp(as_of).normalize() if as_of else latest_completed_session()
    monthly_date = active_formation_date(cutoff)
    lm2_date = active_lm2_formation_date(cutoff)
    lm2_is_active = session_number_after(lm2_date, cutoff) <= base_config.last_retest_day
    weekly_dates = weekly_formation_dates(cutoff, count=2)

    monthly = _valid_state(_monthly_state_path(root, monthly_date), base_config.method_version)
    weekly_states: list[dict[str, Any] | None] = [
        _valid_state(_weekly_state_path(root, date), WEEKLY_METHOD_VERSION)
        for date in weekly_dates
    ]
    lm2 = (
        _valid_state(_lm2_state_path(root, lm2_date), LM2_METHOD_VERSION)
        if lm2_is_active
        else None
    )
    needs_universe = (
        monthly is None
        or any(state is None for state in weekly_states)
        or (lm2_is_active and lm2 is None)
    )
    full_prices: dict[str, pd.DataFrame] = {}
    universe_errors: dict[str, str] = {}
    universe_size = 0
    if needs_universe:
        earliest_comparison = previous_weekly_formation_date(weekly_dates[0])
        required_dates = [monthly_date, earliest_comparison]
        if lm2_is_active:
            required_dates.append(lm2_date)
        start = min(required_dates) - pd.Timedelta(days=560)
        full_prices, universe_errors, universe_size = _load_universe_prices(
            root=root,
            start=start,
            cutoff=cutoff,
            prices_dir=prices_dir,
        )
    if monthly is None:
        monthly = _build_monthly_state(
            root=root,
            formation_date=monthly_date,
            prices=full_prices,
            errors=universe_errors,
            config=base_config,
        )
    if any(state is None for state in weekly_states):
        weekly_states = _build_weekly_states(
            root=root,
            formation_dates=weekly_dates,
            prices=full_prices,
            errors=universe_errors,
            base_config=base_config,
            weekly_config=weekly_config,
        )
    if lm2_is_active and lm2 is None:
        lm2 = _build_lm2_state(
            root=root,
            formation_date=lm2_date,
            prices=full_prices,
            errors=universe_errors,
            base_config=base_config,
            lm2_config=lm2_config,
        )
    active_weekly = [
        state
        for state in weekly_states
        if state is not None
        and session_number_after(pd.Timestamp(state["formation_date"]), cutoff)
        <= base_config.last_retest_day
    ]

    formations = [
        ("monthly", monthly),
        *([("lm2", lm2)] if lm2 is not None else []),
        *[("weekly", state) for state in active_weekly],
    ]
    candidate_tickers = sorted(
        {
            str(candidate["ticker"])
            for _, formation in formations
            for candidate in formation.get("candidates", [])
        }
    )
    if full_prices:
        prices = {ticker: full_prices[ticker] for ticker in candidate_tickers if ticker in full_prices}
        candidate_errors = {
            ticker: universe_errors[ticker]
            for ticker in candidate_tickers
            if ticker in universe_errors
        }
    else:
        earliest_active = min(pd.Timestamp(state["formation_date"]) for _, state in formations)
        if prices_dir:
            prices = load_price_directory(
                prices_dir,
                candidate_tickers,
                start=earliest_active - pd.Timedelta(days=45),
                cutoff=cutoff,
            )
            candidate_errors = {
                ticker: "No existe un CSV local válido"
                for ticker in candidate_tickers
                if ticker not in prices
            }
        else:
            prices, candidate_errors = download_histories(
                candidate_tickers,
                start=earliest_active - pd.Timedelta(days=45),
                cutoff=cutoff,
                batch_size=40,
            )

    scans: list[dict[str, Any]] = []
    candidate_monitors: list[dict[str, Any]] = []
    source_signals: list[dict[str, Any]] = []
    scans_by_source: dict[str, list[dict[str, Any]]] = {
        "monthly": [],
        "lm2": [],
        "weekly": [],
    }
    for source, formation in formations:
        source_scans, monitors, signals = _scan_source_candidates(
            source=source,
            formation=formation,
            prices=prices,
            cutoff=cutoff,
            base_config=base_config,
            weekly_config=weekly_config,
            lm2_config=lm2_config,
        )
        scans.extend(source_scans)
        scans_by_source[source].extend(source_scans)
        candidate_monitors.extend(monitors)
        source_signals.extend(signals)
    merged_current = merge_signal_records(source_signals)
    current_keys = {signal_key(signal) for signal in merged_current}

    history_path = root / "public" / "data" / "history.json"
    history_payload = read_json(history_path, {"signals": []})
    all_history = _sort_signals(
        apply_signal_cooldown(
            [*history_payload.get("signals", []), *merged_current],
            cooldown_sessions=base_config.cooldown_sessions,
        )
    )
    current_signals = _sort_signals(
        [signal for signal in all_history if signal_key(signal) in current_keys]
    )

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

    monthly_session = session_number_after(monthly_date, cutoff)
    source_counts = {
        "monthly_candidates": len(monthly.get("candidates", [])),
        "weekly_crossing_candidates": sum(
            len(state.get("candidates", [])) for state in active_weekly
        ),
        "lm2_candidates": len(lm2.get("candidates", [])) if lm2 else 0,
        "monthly_signals": sum("monthly" in row["signal_sources"] for row in current_signals),
        "lm2_signals": sum("lm2" in row["signal_sources"] for row in current_signals),
        "weekly_signals": sum("weekly" in row["signal_sources"] for row in current_signals),
        "confluence_signals": sum(bool(row.get("is_confluence")) for row in current_signals),
        "cooldown_suppressed": sum(not row.get("actionable", True) for row in current_signals),
    }
    current_payload = {
        "method_version": MULTITEMPORAL_METHOD_VERSION,
        "source_method_versions": {
            "monthly": base_config.method_version,
            "lm2": lm2_config.method_version,
            "weekly": weekly_config.method_version,
        },
        "generated_at": _iso_now(),
        "cutoff": cutoff.date().isoformat(),
        "formation_date": monthly_date.date().isoformat(),
        "monthly_formation_date": monthly_date.date().isoformat(),
        "lm2_formation_date": lm2["formation_date"] if lm2 else None,
        "weekly_formation_dates": [state["formation_date"] for state in active_weekly],
        "session_after_formation": monthly_session,
        "cycle_phase": _cycle_phase(monthly_session, base_config),
        "formation_stats": monthly["stats"],
        "weekly_formation_stats": [
            {
                "formation_date": state["formation_date"],
                "comparison_date": state["comparison_date"],
                **state["stats"],
            }
            for state in active_weekly
        ],
        "lm2_formation_stats": lm2["stats"] if lm2 else None,
        "source_counts": source_counts,
        "scan_status": _status_counts(scans),
        "scan_status_by_source": {
            source: _status_counts(source_scans)
            for source, source_scans in scans_by_source.items()
        },
        "candidate_download_errors": len(candidate_errors),
        "universe_size": universe_size or None,
        "candidates": sorted(
            candidate_monitors,
            key=lambda row: (
                {"monthly": 0, "lm2": 1, "weekly": 2}.get(row.get("source"), 9),
                row.get("formation_date", ""),
                row.get("candidate_rank") is None,
                row.get("candidate_rank") or 0,
            ),
        ),
        "signals": current_signals,
        "alert_scope": "A+, A and monthly B confirmed on cutoff; actionable after global cooldown",
        "weekly_b_policy": "computed_for_audit_but_never_published_or_alerted",
        "lm2_b_policy": "computed_for_audit_but_never_published_or_alerted",
        "cross_source_cooldown_sessions": base_config.cooldown_sessions,
        "alert_result": alert_result,
    }
    write_json(root / "public" / "data" / "current.json", current_payload)
    write_json(
        history_path,
        {
            "method_version": MULTITEMPORAL_METHOD_VERSION,
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
            "monthly_formation_date": current_payload["monthly_formation_date"],
            "lm2_formation_date": current_payload["lm2_formation_date"],
            "weekly_formation_dates": current_payload["weekly_formation_dates"],
            "signals": len(current_signals),
            "source_counts": source_counts,
            "pending_alerts": len(pending),
            "alert_result": alert_result,
        },
    )
    return current_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="MTR Multitemporal v2.0 daily scanner")
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
