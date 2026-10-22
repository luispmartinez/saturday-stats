"""
build_hhs_flag_detail.py   (Stage 2b)
The numbers behind the "how the flag works" box: for every group, scored month and method, the 12 baseline months,
the center, the spread, the +/-3 band, the month's change and its score.

It recomputes everything with plain loops from the monthly change in hhs_group_trend_stage2.csv, then PROVES the
result against the scores and flags Stage 2 already exported. If the box ever disagrees with the flags, this stops.

  hhs_flag_baseline_stage2.csv   group, month, k (1 = oldest of the 12), base_month, base_pct   (percent)
  hhs_flag_summary_stage2.csv    group, month, method, center, spread, lo, hi, month_pct, score, flag,
                                 and for median_mad: gap_pp, min_move, flag_larger
"""
from pathlib import Path

import numpy as np
import pandas as pd

from hhs_groups import ALL_LABEL, GROUP_LABELS

OUT = Path.home() / "TableauData" / "Texas HHS Enrollment"          # local disk, never iCloud
WINDOW, THRESH, K = 12, 3, 1.4826                                    # must match explore_hhs_enrollment.py


def write_atomic(df, name):
    OUT.mkdir(parents=True, exist_ok=True)
    low = str(OUT.resolve()).lower()
    assert not any(t in low for t in ("icloud", "clouddocs", "dropbox", "onedrive")), "OUT is cloud-synced"
    final = OUT / name
    tmp = final.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(final)
    return final


gt = pd.read_csv(OUT / "hhs_group_trend_stage2.csv", parse_dates=["month"])
groups = [ALL_LABEL] + GROUP_LABELS
assert set(gt["group"]) == set(groups)

base_rows, sum_rows = [], []
for g in groups:
    s = gt[gt["group"] == g].sort_values("month").reset_index(drop=True)
    pct = (s["mom_pct"] * 100).to_numpy()                 # percent change vs the month before
    months = s["month"].to_numpy()
    for t in range(WINDOW + 1, len(s)):                   # month 0 has no change; the first scored month is 13
        win = pct[t - WINDOW:t]                           # the 12 months before month t
        assert len(win) == WINDOW and not np.isnan(win).any()
        for k in range(1, WINDOW + 1):
            base_rows.append(dict(group=g, month=months[t], k=k, base_month=months[t - WINDOW + k - 1], base_pct=win[k - 1]))
        med = float(np.median(win))
        methods = {"mean_sd": (float(win.mean()), float(win.std(ddof=1))),
                   "median_mad": (med, K * float(np.median(np.abs(win - med))))}
        for method, (center, spread) in methods.items():
            score = (pct[t] - center) / spread
            row = dict(group=g, month=months[t], method=method, center=center, spread=spread,
                       lo=center - THRESH * spread, hi=center + THRESH * spread, month_pct=pct[t],
                       score=score, flag=abs(score) > THRESH)
            if method == "median_mad":
                row.update(gap_pp=pct[t] - center, min_move=float(s["min_move"].iloc[t]),
                           flag_larger=bool(abs(score) > THRESH and abs(pct[t] - center) >= s["min_move"].iloc[t]))
            sum_rows.append(row)

baseline, summary = pd.DataFrame(base_rows), pd.DataFrame(sum_rows)

# Proof against Stage 2: same scores, same flags, for every group and every scored month
n_scored = len(gt[gt["group"] == ALL_LABEL]) - WINDOW - 1
assert len(summary) == len(groups) * n_scored * 2 and len(baseline) == len(groups) * n_scored * WINDOW
assert (baseline.groupby(["group", "month"]).size() == WINDOW).all(), "every month needs exactly 12 baseline months"
assert (baseline["base_month"] < baseline["month"]).all(), "a baseline month must come before the scored month"
for g in groups:
    s = gt[gt["group"] == g].sort_values("month").reset_index(drop=True).iloc[WINDOW + 1:]
    for method, zc, fc in [("mean_sd", "z_mean_sd", "flag_mean_sd"), ("median_mad", "z_robust", "flag_robust")]:
        m = summary[(summary["group"] == g) & (summary["method"] == method)].sort_values("month")
        assert (m["month"].to_numpy() == s["month"].to_numpy()).all()
        assert np.allclose(m["score"].to_numpy(), s[zc].to_numpy(), rtol=1e-9, atol=1e-9), f"{g}/{method}: scores differ from Stage 2"
        assert (m["flag"].to_numpy() == s[fc].to_numpy()).all(), f"{g}/{method}: flags differ from Stage 2"
    m = summary[(summary["group"] == g) & (summary["method"] == "median_mad")].sort_values("month")
    assert (m["flag_larger"].to_numpy() == s["flag_robust_min"].to_numpy()).all(), f"{g}: larger-move flags differ from Stage 2"

print(write_atomic(baseline.round({"base_pct": 6}), "hhs_flag_baseline_stage2.csv"), baseline.shape)
print(write_atomic(summary.round({c: 6 for c in ["center", "spread", "lo", "hi", "month_pct", "score", "gap_pp", "min_move"]}), "hhs_flag_summary_stage2.csv"), summary.shape)
