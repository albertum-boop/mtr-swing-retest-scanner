from __future__ import annotations

import hashlib
import html
import json
import os
from collections import Counter
from collections.abc import Iterable
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

GRADE_ORDER = {"A+": 0, "A": 1, "B": 2}


def _pct(value: Any) -> str:
    return "N/D" if value is None else f"{100 * float(value):+.2f}%"


def _number(value: Any, decimals: int = 2) -> str:
    return "N/D" if value is None else f"{float(value):.{decimals}f}"


def _source(signal: dict[str, Any]) -> str:
    labels = {"monthly": "Mensual", "lm2": "LM2", "weekly": "Semanal"}
    sources = signal.get("signal_sources") or str(
        signal.get("source", "monthly")
    ).split("+")
    return " + ".join(labels.get(str(source), str(source)) for source in sources)


def build_email(signals: Iterable[dict[str, Any]]) -> tuple[str, str, str]:
    ordered = sorted(
        signals,
        key=lambda row: (GRADE_ORDER.get(row.get("grade", "B"), 9), row.get("event_date", ""), row.get("ticker", "")),
    )
    subject = f"MTR: {len(ordered)} señal{'es' if len(ordered) != 1 else ''} nueva{'s' if len(ordered) != 1 else ''}"
    plain_lines = [subject, "", "Entrada de referencia: apertura ajustada de la próxima sesión.", ""]
    rows = []
    for signal in ordered:
        plain_lines.append(
            f"{signal['grade']} · {signal['ticker']} · {_source(signal)} · "
            f"{signal['event_date']} · "
            f"Swing {_number(signal.get('swing_score'), 3)} · "
            f"volumen {_pct(signal.get('event_volume_change'))}"
        )
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(str(signal['grade']))}</strong></td>"
            f"<td><strong>{html.escape(str(signal['ticker']))}</strong></td>"
            f"<td>{html.escape(_source(signal))}</td>"
            f"<td>{html.escape(str(signal['event_date']))}</td>"
            f"<td>{_number(signal.get('swing_score'), 3)}</td>"
            f"<td>{_number(signal.get('close_location'), 3)}</td>"
            f"<td>{_pct(signal.get('event_volume_change'))}</td>"
            f"<td>{_number(signal.get('pullback_from_peak_atr'), 2)} ATR</td>"
            "</tr>"
        )
    body_html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#182432">
      <h2>{html.escape(subject)}</h2>
      <p>La configuración mensual, LM2 o semanal se confirmó al cierre. La entrada es la apertura ajustada de la próxima sesión; no es una orden automática. Las señales B de LM2 y semanales están excluidas, y el cooldown común evita entradas duplicadas.</p>
      <table cellpadding="7" cellspacing="0" border="1" style="border-collapse:collapse;border-color:#ccd6e0">
        <thead><tr style="background:#173f5f;color:white"><th>Grado</th><th>Ticker</th><th>Marco</th><th>Fecha</th><th>Swing</th><th>Cierre/rango</th><th>Volumen</th><th>Pullback</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p style="color:#667587;font-size:12px">MTR Multitemporal v2.0 · señal de investigación, no recomendación financiera.</p>
    </body></html>
    """
    return subject, "\n".join(plain_lines), body_html


def build_weekly_email(
    signals: Iterable[dict[str, Any]],
    *,
    week_start: date,
    week_end: date,
    app_url: str = "https://mtr-swing-retest-scanner.vercel.app/",
) -> tuple[str, str, str]:
    """Build the weekly safety-net report, including weeks with zero signals."""

    ordered = sorted(
        signals,
        key=lambda row: (
            GRADE_ORDER.get(row.get("grade", "B"), 9),
            row.get("event_date", ""),
            row.get("ticker", ""),
        ),
    )
    grades = Counter(str(signal.get("grade", "N/D")) for signal in ordered)
    period = f"{week_start.isoformat()} a {week_end.isoformat()}"
    subject = (
        f"MTR semanal {week_start.strftime('%d/%m')}-{week_end.strftime('%d/%m')}: "
        f"{len(ordered)} señal{'es' if len(ordered) != 1 else ''}"
    )
    summary = (
        f"A+ {grades.get('A+', 0)} · A {grades.get('A', 0)} · "
        f"B mensual {grades.get('B', 0)}"
    )
    plain_lines = [
        subject,
        f"Periodo: {period}",
        summary,
        "",
        "Este informe resume señales accionables ya confirmadas durante la semana.",
        "La entrada reglada es la apertura de la sesión posterior al evento.",
        "",
    ]
    rows = []
    for signal in ordered:
        entry_open = (
            "N/D"
            if signal.get("entry_open") is None
            else f"${float(signal['entry_open']):.2f}"
        )
        entry_date = str(signal.get("entry_date") or "Pendiente")
        confluence = "Sí" if signal.get("is_confluence") else "No"
        plain_lines.append(
            f"{signal['grade']} · {signal['ticker']} · {_source(signal)} · "
            f"señal {signal['event_date']} · entrada {entry_date} {entry_open} · "
            f"confluencia {confluence}"
        )
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(str(signal['grade']))}</strong></td>"
            f"<td><strong>{html.escape(str(signal['ticker']))}</strong></td>"
            f"<td>{html.escape(_source(signal))}</td>"
            f"<td>{html.escape(str(signal['event_date']))}</td>"
            f"<td>{html.escape(entry_date)}</td>"
            f"<td>{html.escape(entry_open)}</td>"
            f"<td>{confluence}</td>"
            f"<td>{_number(signal.get('swing_score'), 3)}</td>"
            f"<td>{_pct(signal.get('event_volume_change'))}</td>"
            "</tr>"
        )

    if not ordered:
        plain_lines.append("No hubo señales accionables confirmadas esta semana.")
        table_body = (
            '<tr><td colspan="9" style="text-align:center;color:#667587">'
            "No hubo señales accionables confirmadas esta semana.</td></tr>"
        )
    else:
        table_body = "".join(rows)
    plain_lines.extend(["", f"Aplicación: {app_url}"])

    body_html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#182432">
      <h2>{html.escape(subject)}</h2>
      <p><strong>Periodo:</strong> {html.escape(period)}<br>
      <strong>Resumen:</strong> {html.escape(summary)}</p>
      <p>Este informe resume todas las señales accionables confirmadas durante la semana,
      aunque ya se hubiera enviado su alerta diaria. La entrada reglada es la apertura de la
      sesión posterior al evento; una fecha pasada no constituye una entrada nueva.</p>
      <table cellpadding="7" cellspacing="0" border="1"
             style="border-collapse:collapse;border-color:#ccd6e0">
        <thead><tr style="background:#173f5f;color:white"><th>Grado</th><th>Ticker</th>
        <th>Marco</th><th>Señal</th><th>Entrada</th><th>Precio</th><th>Confluencia</th>
        <th>Swing</th><th>Volumen</th></tr></thead>
        <tbody>{table_body}</tbody>
      </table>
      <p><a href="{html.escape(app_url)}">Abrir MTR Swing Retest Scanner</a></p>
      <p style="color:#667587;font-size:12px">MTR Multitemporal v2.0 · informe de
      investigación, no recomendación financiera.</p>
    </body></html>
    """
    return subject, "\n".join(plain_lines), body_html


def email_configuration() -> tuple[dict[str, str], list[str]]:
    values = {
        "RESEND_API_KEY": os.environ.get("RESEND_API_KEY", "").strip(),
        "ALERT_TO": os.environ.get("ALERT_TO", "").strip(),
        "ALERT_FROM": os.environ.get(
            "ALERT_FROM", "MTR Signals <onboarding@resend.dev>"
        ).strip(),
    }
    missing = [name for name in ("RESEND_API_KEY", "ALERT_TO") if not values[name]]
    return values, missing


def _send_email(
    *,
    subject: str,
    plain: str,
    body_html: str,
    signal_count: int,
) -> dict[str, Any]:
    config, missing = email_configuration()
    if missing:
        return {"status": "not_configured", "sent": 0, "missing": missing}
    recipients = [item.strip() for item in config["ALERT_TO"].split(",") if item.strip()]
    if not recipients:
        return {"status": "not_configured", "sent": 0, "missing": ["ALERT_TO"]}
    payload = json.dumps(
        {
            "from": config["ALERT_FROM"],
            "to": recipients,
            "subject": subject,
            "text": plain,
            "html": body_html,
        }
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    request = Request(
        "https://api.resend.com/emails",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {config['RESEND_API_KEY']}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"mtr-{digest}",
            "User-Agent": "mtr-swing-retest-scanner/2.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "error",
            "sent": 0,
            "detail": f"Resend HTTP {exc.code}: {detail}",
        }
    except URLError as exc:
        return {"status": "error", "sent": 0, "detail": f"Resend: {exc.reason}"}
    return {
        "status": "sent",
        "sent": signal_count,
        "recipients": len(recipients),
        "provider": "resend",
        "provider_id": response_payload.get("id"),
    }


def send_signal_email(signals: list[dict[str, Any]]) -> dict[str, Any]:
    if not signals:
        return {"status": "nothing_to_send", "sent": 0}
    subject, plain, body_html = build_email(signals)
    return _send_email(
        subject=subject,
        plain=plain,
        body_html=body_html,
        signal_count=len(signals),
    )


def send_weekly_report_email(
    signals: list[dict[str, Any]],
    *,
    week_start: date,
    week_end: date,
) -> dict[str, Any]:
    """Send a weekly report even when the week contains no signals."""

    subject, plain, body_html = build_weekly_email(
        signals,
        week_start=week_start,
        week_end=week_end,
    )
    return _send_email(
        subject=subject,
        plain=plain,
        body_html=body_html,
        signal_count=len(signals),
    )
