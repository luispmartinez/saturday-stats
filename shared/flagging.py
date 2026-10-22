"""Rolling-baseline anomaly flags: the logic behind the HHS anomaly detector, written to be reused.

Each value is compared with the `window` values just before it.
  1. Look back   the previous `window` values (default 12)
  2. Center      their mean, or their median
  3. Spread      their standard deviation, or 1.4826 x MAD (median absolute deviation)
  4. Score       (value - center) / spread; flagged when |score| > threshold (default 3)

Why two methods: a few extreme months in the window stretch the standard deviation, so the mean-and-SD
yardstick goes loose and misses a real drop. The median and MAD barely move. See docs/concepts/.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MAD_TO_SD = 1.4826          # scales MAD to match a standard deviation when data are roughly normal
METHODS = ("mean_sd", "median_mad")
COLUMNS = ["observed", "expected", "spread", "lower", "upper", "score", "flag"]


def flag_series(values, window: int = 12, threshold: float = 3.0, method: str = "median_mad",
                ddof: int = 1, min_move: float | None = None) -> pd.DataFrame:
    """Score every value that has a full window behind it. The first `window` rows stay unscored.

    expected = the baseline center; lower/upper = center -/+ threshold x spread (the band).
    min_move: if given, a flag also needs |value - center| >= min_move (ignores tiny moves in quiet baselines).
    A baseline with zero spread gives score NaN and no flag, never a division by zero.
    """
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}")
    if window < 3:
        raise ValueError("window must be at least 3")
    s = pd.Series(values, dtype="float64")
    out = pd.DataFrame(np.nan, index=s.index, columns=COLUMNS)
    out["observed"] = s
    out["flag"] = False
    for i in range(window, len(s)):
        base = s.iloc[i - window:i]
        if base.isna().any() or pd.isna(s.iloc[i]):
            continue
        if method == "mean_sd":
            center, spread = base.mean(), base.std(ddof=ddof)
        else:
            center = base.median()
            spread = MAD_TO_SD * (base - center).abs().median()
        row = out.index[i]
        out.loc[row, ["expected", "spread"]] = center, spread
        out.loc[row, ["lower", "upper"]] = center - threshold * spread, center + threshold * spread
        if spread > 0:
            score = (s.iloc[i] - center) / spread
            out.loc[row, "score"] = score
            big_enough = min_move is None or abs(s.iloc[i] - center) >= min_move
            out.loc[row, "flag"] = bool(abs(score) > threshold and big_enough)
    out["flag"] = out["flag"].astype(bool)
    return out
