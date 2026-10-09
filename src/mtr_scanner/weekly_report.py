from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .alerts import GRADE_ORDER, send_weekly_report_email
from .storage import read_json, write_json
from .trend import is_operationally_actionable

ROOT = Path(__file__).resolve().parents[2]


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def report_window(cutoff: date) -> tuple[date, date]:
    """Return Monday through the supplied completed market date."""

    return cutoff - timedelta(days=cutoff.weekday()), cutoff


def select_week_signals(
    signals: list[dict[str, Any]],
    *,
    week_start: date,
    week_end: date,
) -> list[dict[str, Any]]:
    """Select unique actionable events confirmed in the requested calendar week."""

    selected = []
    seen: set[tuple[str, str]] = set()
    for signal in signals:
        event_date = date.fromisoformat(str(signal["event_date"]))
        key = (str(signal["ticker"]), event_date.isoformat())
        if (
            week_start <= event_date <= week_end
            and is_operationally_actionable(signal)
            and key not in seen
        ):
            selected.append(signal)
            seen.add(key)
    return sorted(
        selected,
        key=lambda row: (
            GRADE_ORDER.get(row.get("grade", "B"), 9),
            row.get("event_date", ""),
            row.get("ticker", ""),
        ),
    )


def run_weekly_report(
    *,
    root: Path = ROOT,
    as_of: str | None = None,
    send: bool = False,
) -> dict[str, Any]:
    last_run = read_json(root / "state" / "last_run.json", {})
    cutoff_value = as_of or last_run.get("cutoff")
    if not cutoff_value:
        raise RuntimeError("No hay fecha de corte en state/last_run.json")
    cutoff = date.fromisoformat(str(cutoff_value))
    week_start, week_end = report_window(cutoff)
    report_key = f"{week_start.isoformat()}:{week_end.isoformat()}"

    history = read_json(root / "public" / "data" / "history.json", {"signals": []})
    signals = select_week_signals(
        history.get("signals", []),
        week_start=week_start,
        week_end=week_end,
    )

    state_path = root / "state" / "weekly_reports.json"
    state = read_json(state_path, {"reports": []})
    reports = list(state.get("reports", []))
    if any(report.get("report_key") == report_key for report in reports):
        return {
            "status": "already_sent",
            "report_key": report_key,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "signals": len(signals),
        }

    result: dict[str, Any] = {
        "status": "preview",
        "sent": 0,
        "signals": len(signals),
    }
    if send:
        result = send_weekly_report_email(
            signals,
            week_start=week_start,
            week_end=week_end,
        )
        if result.get("status") == "sent":
            reports.append(
                {
                    "report_key": report_key,
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                    "sent_at": _iso_now(),
                    "signals": len(signals),
                }
            )
            write_json(state_path, {"updated_at": _iso_now(), "reports": reports})

    return {
        **result,
        "report_key": report_key,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "signals": len(signals),
        "tickers": [signal["ticker"] for signal in signals],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="MTR weekly signal report")
    parser.add_argument("--as-of", help="Última fecha de mercado incluida, YYYY-MM-DD")
    parser.add_argument("--send", action="store_true", help="Enviar el informe por Resend")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run_weekly_report(
        root=args.root.resolve(),
        as_of=args.as_of,
        send=args.send,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.send and result.get("status") not in {"sent", "already_sent"}:
        raise SystemExit(f"No se pudo enviar el informe semanal: {result}")


if __name__ == "__main__":
    main()
