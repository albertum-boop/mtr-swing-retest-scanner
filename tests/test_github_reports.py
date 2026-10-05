import json
from pathlib import Path

from mtr_scanner.github_reports import daily_report, weekly_report


def signal(ticker: str, event_date: str, *, grade: str = "A") -> dict[str, object]:
    return {
        "signal_id": f"test:{ticker}:{event_date}",
        "ticker": ticker,
        "grade": grade,
        "event_date": event_date,
        "entry_date": "2026-10-02",
        "entry_open": 141.87,
        "source": "lm2",
        "signal_sources": ["lm2"],
        "is_confluence": False,
        "swing_score": 0.83,
        "event_volume_change": -0.48,
        "actionable": True,
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_daily_report_only_contains_new_cutoff_signals(tmp_path: Path):
    write_json(
        tmp_path / "public/data/current.json",
        {
            "cutoff": "2026-10-02",
            "signals": [
                signal("NEW", "2026-10-02", grade="A+"),
                signal("OLD", "2026-10-01"),
            ],
        },
    )

    report, count = daily_report(tmp_path)

    assert count == 1
    assert "mtr-report:daily:2026-10-02" in report
    assert "**NEW**" in report
    assert "OLD" not in report


def test_daily_report_is_empty_without_new_signals(tmp_path: Path):
    write_json(
        tmp_path / "public/data/current.json",
        {"cutoff": "2026-10-02", "signals": [signal("OLD", "2026-10-01")]},
    )

    assert daily_report(tmp_path) == ("", 0)


def test_weekly_report_includes_docn_and_zero_signal_weeks(tmp_path: Path):
    write_json(tmp_path / "state/last_run.json", {"cutoff": "2026-10-02"})
    write_json(
        tmp_path / "public/data/history.json",
        {"signals": [signal("DOCN", "2026-10-01", grade="A+")]},
    )

    report, count = weekly_report(tmp_path)
    assert count == 1
    assert "mtr-report:weekly:2026-09-28:2026-10-02" in report
    assert "**DOCN**" in report

    empty, empty_count = weekly_report(tmp_path, as_of="2026-10-09")
    assert empty_count == 0
    assert "No hubo señales accionables" in empty
