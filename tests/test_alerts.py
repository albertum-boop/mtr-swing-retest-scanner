from __future__ import annotations

import json
from io import BytesIO
from typing import Self
from urllib.error import HTTPError

from mtr_scanner import alerts


class FakeResponse:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"id":"email_test_123"}'


def _signal() -> dict[str, object]:
    return {
        "grade": "A+",
        "ticker": "DOCN",
        "event_date": "2026-10-01",
        "source": "weekly",
    }


def test_resend_delivery_uses_api_and_default_sender(monkeypatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("ALERT_TO", "owner@example.com")
    monkeypatch.delenv("ALERT_FROM", raising=False)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(alerts, "urlopen", fake_urlopen)

    result = alerts.send_signal_email([_signal()])

    assert result == {
        "status": "sent",
        "sent": 1,
        "recipients": 1,
        "provider": "resend",
        "provider_id": "email_test_123",
    }
    request = captured["request"]
    payload = json.loads(request.data)
    assert request.full_url == "https://api.resend.com/emails"
    assert request.get_header("Authorization") == "Bearer re_test"
    assert request.get_header("Idempotency-key").startswith("mtr-")
    assert captured["timeout"] == 30
    assert payload["from"] == "MTR Signals <onboarding@resend.dev>"
    assert payload["to"] == ["owner@example.com"]
    assert "DOCN" in payload["html"]
    assert "DOCN" in payload["text"]


def test_resend_configuration_reports_only_required_values(monkeypatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("ALERT_TO", raising=False)
    monkeypatch.delenv("ALERT_FROM", raising=False)

    result = alerts.send_signal_email([_signal()])

    assert result == {
        "status": "not_configured",
        "sent": 0,
        "missing": ["RESEND_API_KEY", "ALERT_TO"],
    }


def test_resend_http_error_is_visible_without_leaking_key(monkeypatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_secret_value")
    monkeypatch.setenv("ALERT_TO", "owner@example.com")

    def fail_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},
            BytesIO(b'{"message":"validation_error"}'),
        )

    monkeypatch.setattr(alerts, "urlopen", fail_urlopen)

    result = alerts.send_signal_email([_signal()])

    assert result["status"] == "error"
    assert result["sent"] == 0
    assert "Resend HTTP 403" in result["detail"]
    assert "re_secret_value" not in result["detail"]
