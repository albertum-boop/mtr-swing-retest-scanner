from __future__ import annotations

import html
import os
import smtplib
import ssl
from collections.abc import Iterable
from email.message import EmailMessage
from typing import Any

GRADE_ORDER = {"A+": 0, "A": 1, "B": 2}


def _pct(value: Any) -> str:
    return "N/D" if value is None else f"{100 * float(value):+.2f}%"


def _number(value: Any, decimals: int = 2) -> str:
    return "N/D" if value is None else f"{float(value):.{decimals}f}"


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
            f"{signal['grade']} · {signal['ticker']} · {signal['event_date']} · "
            f"Swing {_number(signal.get('swing_score'), 3)} · "
            f"volumen {_pct(signal.get('event_volume_change'))}"
        )
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(str(signal['grade']))}</strong></td>"
            f"<td><strong>{html.escape(str(signal['ticker']))}</strong></td>"
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
      <p>La configuración se confirmó al cierre. La entrada v1.0 es la apertura ajustada de la próxima sesión; no es una orden automática.</p>
      <table cellpadding="7" cellspacing="0" border="1" style="border-collapse:collapse;border-color:#ccd6e0">
        <thead><tr style="background:#173f5f;color:white"><th>Grado</th><th>Ticker</th><th>Fecha</th><th>Swing</th><th>Cierre/rango</th><th>Volumen</th><th>Pullback</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p style="color:#667587;font-size:12px">MTR Swing Retest v1.0 · señal de investigación, no recomendación financiera.</p>
    </body></html>
    """
    return subject, "\n".join(plain_lines), body_html


def email_configuration() -> tuple[dict[str, str], list[str]]:
    names = [
        "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "ALERT_FROM", "ALERT_TO"
    ]
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    return values, missing


def send_signal_email(signals: list[dict[str, Any]]) -> dict[str, Any]:
    if not signals:
        return {"status": "nothing_to_send", "sent": 0}
    config, missing = email_configuration()
    if missing:
        return {"status": "not_configured", "sent": 0, "missing": missing}
    subject, plain, body_html = build_email(signals)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["ALERT_FROM"]
    recipients = [item.strip() for item in config["ALERT_TO"].split(",") if item.strip()]
    message["To"] = ", ".join(recipients)
    message.set_content(plain)
    message.add_alternative(body_html, subtype="html")
    host = config["SMTP_HOST"]
    port = int(config["SMTP_PORT"])
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
            server.send_message(message)
    return {"status": "sent", "sent": len(signals), "recipients": len(recipients)}
