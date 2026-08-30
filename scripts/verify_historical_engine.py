from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from mtr_scanner.market_data import adjusted_prices
from mtr_scanner.retest import scan_candidate


def candidates(predictions_path: Path) -> pd.DataFrame:
    panel = pd.read_pickle(predictions_path)
    panel["FormationDate"] = pd.to_datetime(panel["FormationDate"])
    panel = panel.loc[
        panel["Period"].between(pd.Period("2019-01", "M"), pd.Period("2026-07", "M"))
        & panel["R10"].notna()
    ].copy()
    panel["SwingScore"] = panel[["ATRPct20", "Mom12_1_Daily", "ReturnVolumeCorr20"]].mean(axis=1)
    panel["SwingRankPct"] = panel.groupby("Period")["SwingScore"].rank(pct=True, method="average")
    return panel.loc[panel["SwingRankPct"].gt(0.80)].copy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    selected = candidates(args.predictions)
    signals: list[dict[str, object]] = []
    for ticker, group in selected.groupby("Ticker", sort=False):
        raw = pd.read_csv(args.prices / f"{ticker}.csv")
        data = adjusted_prices(raw, ticker)
        prev = data["AdjClose"].shift()
        true_range = pd.concat(
            [
                data["AdjHigh"] - data["AdjLow"],
                (data["AdjHigh"] - prev).abs(),
                (data["AdjLow"] - prev).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr20 = true_range.rolling(20, min_periods=20).mean()
        volume20 = data["AdjVolume"].rolling(20, min_periods=20).mean()
        positions = {date: i for i, date in enumerate(data.index)}
        for row in group.itertuples(index=False):
            formation = pd.Timestamp(row.FormationDate)
            i = positions.get(formation)
            if i is None or not np.isfinite(atr20.iloc[i]):
                continue
            candidate = {
                "ticker": ticker,
                "formation_date": formation.date().isoformat(),
                "formation_close": float(data["AdjClose"].iloc[i]),
                "atr_abs20": float(atr20.iloc[i]),
                "prior_adj_volume20": float(volume20.iloc[i]),
                "adv20": float(row.ADV20),
                "rank_pct": float(row.RankPct),
                "swing_score": float(row.SwingScore),
                "swing_rank_pct": float(row.SwingRankPct),
                "mom12_1_pct": float(row.Mom12_1_Daily),
                "atr_pct20_pct": float(row.ATRPct20),
                "return_volume_corr20_pct": float(row.ReturnVolumeCorr20),
                "sma200_slope20_pct": float(row.SMA200Slope20),
            }
            result = scan_candidate(candidate, raw)
            if result.get("signal"):
                signals.append(result["signal"])
    actual = pd.DataFrame(signals)
    reference = pd.read_csv(args.reference)
    actual_keys = set(zip(actual["ticker"], actual["event_date"], actual["grade"], strict=False))
    expected_keys = set(zip(reference["ticker"], reference["event_date"], reference["grade"], strict=False))
    added = sorted(actual_keys - expected_keys)
    missing = sorted(expected_keys - actual_keys)
    print(f"Candidates: {len(selected)}")
    print(f"Actual signals: {len(actual_keys)}")
    print(f"Reference signals: {len(expected_keys)}")
    print(f"Extra: {len(added)}")
    print(f"Missing: {len(missing)}")
    if added:
        print("EXTRA", added[:20])
    if missing:
        print("MISSING", missing[:20])
    if actual_keys != expected_keys:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
