from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from .alerts import GRADE_ORDER
from .storage import read_json
from .weekly_report import report_window, select_week_signals

ROOT = Path(__file__).resolve().parents[2]
APP_URL = "https://mtr-swing-retest-scanner.vercel.app/"


def _source(signal: dict[str, Any]) -> str:
    labels = {"monthly": "Mensual", "lm2": "LM2", "weekly": "Semanal"}
    sources = signal.get("signal_sources") or [signal.get("source", "monthly")]
    return " + ".join(labels.get(str(source), str(source)) for source in sources)


def _price(value: Any) -> str:
    return "Pendiente" if value is None else f"${float(value):.2f}"


def _pct(value: Any) -> str:
    return "N/D" if value is None else f"{100 * float(value):+.1f}%"


def _score(value: Any) -> str:
    return "N/D" if value is None else f"{float(value):.3f}"


def _ordered(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        signals,
        key=lambda row: (
            GRADE_ORDER.get(str(row.get("grade", "B")), 9),
            str(row.get("event_date", "")),
            str(row.get("ticker", "")),
        ),
    )


def select_daily_signals(current: dict[str, Any]) -> list[dict[str, Any]]:
    cutoff = str(current["cutoff"])
    return _ordered(
        [
            signal
            for signal in current.get("signals", [])
            if signal.get("event_date") == cutoff and signal.get("actionable", True)
        ]
    )


def render_report(
    signals: list[dict[str, Any]],
    *,
    report_id: str,
    title: str,
    empty_message: str,
) -> str:
    lines = [
        f"<!-- mtr-report:{report_id} -->",
        f"## {title}",
        "",
        "La entrada reglada es la **apertura de la sesión posterior a la señal**. ",
        "Una fecha de entrada pasada no constituye una entrada nueva.",
        "",
    ]
    if not signals:
        lines.extend([empty_message, "", f"[Abrir la aplicación]({APP_URL})"])
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Grado | Ticker | Marco | Señal | Entrada | Precio | Confluencia | Swing | Volumen |",
            "|---|---|---|---|---|---:|---|---:|---:|",
        ]
    )
    for signal in signals:
        lines.append(
            "| {grade} | **{ticker}** | {source} | {event} | {entry} | {price} | "
            "{confluence} | {swing} | {volume} |".format(
                grade=signal.get("grade", "N/D"),
                ticker=signal.get("ticker", "N/D"),
                source=_source(signal),
                event=signal.get("event_date", "N/D"),
                entry=signal.get("entry_date") or "Próxima sesión",
                price=_price(signal.get("entry_open")),
                confluence="Sí" if signal.get("is_confluence") else "No",
                swing=_score(signal.get("swing_score")),
                volume=_pct(signal.get("event_volume_change")),
            )
        )
    lines.extend(
        [
            "",
            (
                f"**Total:** {len(signals)} señal{'es' if len(signals) != 1 else ''} "
                f"accionable{'s' if len(signals) != 1 else ''}."
            ),
            "",
            f"[Abrir la aplicación]({APP_URL})",
        ]
    )
    return "\n".join(lines) + "\n"


def daily_report(root: Path = ROOT) -> tuple[str, int]:
    current = read_json(root / "public" / "data" / "current.json", {})
    if not current.get("cutoff"):
        raise RuntimeError("Falta public/data/current.json o su fecha de corte")
    signals = select_daily_signals(current)
    if not signals:
        return "", 0
    cutoff = str(current["cutoff"])
    return (
        render_report(
            signals,
            report_id=f"daily:{cutoff}",
            title=f"Señales confirmadas al cierre de {cutoff}",
            empty_message="No hubo señales nuevas.",
        ),
        len(signals),
    )


def weekly_report(
    root: Path = ROOT,
    *,
    as_of: str | None = None,
) -> tuple[str, int]:
    last_run = read_json(root / "state" / "last_run.json", {})
    cutoff_value = as_of or last_run.get("cutoff")
    if not cutoff_value:
        raise RuntimeError("Falta state/last_run.json o su fecha de corte")
    cutoff = date.fromisoformat(str(cutoff_value))
    week_start, week_end = report_window(cutoff)
    history = read_json(root / "public" / "data" / "history.json", {"signals": []})
    signals = select_week_signals(
        history.get("signals", []),
        week_start=week_start,
        week_end=week_end,
    )
    return (
        render_report(
            signals,
            report_id=f"weekly:{week_start.isoformat()}:{week_end.isoformat()}",
            title=f"Resumen semanal · {week_start.isoformat()} a {week_end.isoformat()}",
            empty_message="No hubo señales accionables confirmadas esta semana.",
        ),
        len(signals),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GitHub notification reports")
    parser.add_argument("frequency", choices=["daily", "weekly"])
    parser.add_argument("--as-of", help="Última fecha de mercado incluida, YYYY-MM-DD")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.frequency == "daily":
        report, count = daily_report(args.root.resolve())
    else:
        report, count = weekly_report(args.root.resolve(), as_of=args.as_of)
    args.output.write_text(report, encoding="utf-8")
    print(json.dumps({"frequency": args.frequency, "signals": count, "output": str(args.output)}))


if __name__ == "__main__":
    main()
