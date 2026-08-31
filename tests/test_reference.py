from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_reference_is_complete_and_ordered_quality_then_date():
    data = pd.read_csv(ROOT / "reference" / "signals_v1_0.csv", parse_dates=["event_date"])
    assert len(data) == 154
    assert data["grade"].value_counts().to_dict() == {"A": 79, "A+": 49, "B": 26}
    assert data["reference_id"].is_unique
    assert not data.duplicated(["ticker", "event_date"]).any()
    assert data["grade"].map({"A+": 0, "A": 1, "B": 2}).is_monotonic_increasing
    for _, group in data.groupby("grade", sort=False):
        assert group["event_date"].is_monotonic_increasing


def test_reference_grades_reproduce_frozen_equations():
    data = pd.read_csv(ROOT / "reference" / "signals_v1_0.csv")
    is_a_plus = (
        data["sma200_slope_percentile_d10"].ge(0.50)
        & data["pullback_from_peak_atr"].ge(-0.25)
        & data["event_body_atr"].ge(0.25)
        & data["event_body_return"].gt(0)
    )
    expected = pd.Series("B", index=data.index)
    expected.loc[(~is_a_plus) & data["close_location"].ge(0.75)] = "A"
    expected.loc[is_a_plus] = "A+"
    assert expected.tolist() == data["grade"].tolist()


def test_weekly_reference_keeps_b_for_audit_but_marks_it_non_actionable():
    data = pd.read_csv(ROOT / "reference" / "weekly_signals_v1_0.csv")
    assert len(data) == 129
    assert data["grade"].value_counts().to_dict() == {"A": 62, "B": 38, "A+": 29}
    assert data.loc[data["grade"].eq("B"), "actionable"].eq(False).all()
    assert data.loc[data["grade"].isin(["A+", "A"]), "actionable"].eq(True).all()


def test_multitemporal_reference_is_union_not_replacement():
    data = pd.read_csv(ROOT / "reference" / "multitemporal_signals_v1_1.csv")
    assert len(data) == 232
    assert data["master_grade"].value_counts().to_dict() == {
        "A": 132,
        "A+": 75,
        "B": 25,
    }
    assert data["origin"].value_counts().to_dict() == {
        "monthly_only": 141,
        "weekly_incremental": 78,
        "exact_confluence": 13,
    }
    assert data.loc[data["origin"].eq("weekly_incremental"), "weekly_grade"].isin(
        ["A+", "A"]
    ).all()
