"""
explore_hhs_enrollment.py   (Stage 2)
Texas Medicaid/CHIP enrollment: prepare the hand-off files the canvas script reads.

Reads the clean CSVs that prep_enrollment.py wrote to drop/.
Writes five Stage 2 CSVs to ~/TableauData/Texas HHS Enrollment/.
Tableau never reads these; build_hhs_canvas.py turns them into geometry.

These are the exports from stage 2
hhs_monthly_stage2.csv
hhs_county_stage2.csv
hhs_group_trend_stage2.csv
hhs_mix_stage2.csv
hhs_group_moves_stage2.csv
"""
# 1 Load libraries
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from hhs_groups import ALL_LABEL, KEY2LABEL

HERE = Path(__file__).parent
OUT = Path.home() / "TableauData" / "Texas HHS Enrollment"   # local disk, never iCloud


def write_atomic(df, name):
    """Write via temp file + rename so a crashed run never leaves a half-written extract."""
    OUT.mkdir(parents=True, exist_ok=True)
    low = str(OUT.resolve()).lower()
    assert not any(t in low for t in ("icloud", "clouddocs", "dropbox", "onedrive")), \
        "OUT is cloud-synced; Tableau can refresh blank extracts from evicted files"
    final = OUT / name
    tmp = final.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(final)
    return final


# 2 Load data
monthly = pd.read_csv(HERE / "drop" / "hhs_monthly_caseload.csv")
county = pd.read_csv(HERE / "drop" / "hhs_county_final_sfy25.csv")
monthly["month"] = pd.to_datetime(monthly["month"])
monthly = monthly.sort_values("month").reset_index(drop=True)
assert county["period"].nunique() == 1 and county["period"].iloc[0] == "SFY 2025 (final)", \
    f"county file is {county['period'].iloc[0]}"

n = len(monthly)
print(monthly.shape, county.shape)
assert monthly["month"].is_monotonic_increasing and monthly["month"].is_unique


# 3 Risk-group columns, and proof they add up
RISK_COLS = [c for c in monthly.columns if c.startswith("caseload_by_risk_group_")]
assert len(RISK_COLS) == 6
total_check = np.isclose(monthly[RISK_COLS].sum(axis=1), monthly["medicaid_caseload"], rtol=1e-10)
assert total_check.all(), monthly.loc[~total_check, "month"].tolist()


# 4 Shares, in long format
monthly_long = monthly.melt(
    id_vars=["month", "medicaid_caseload"],
    value_vars=RISK_COLS, var_name="group", value_name="caseload",
)
monthly_long["group"] = monthly_long["group"].str.replace("caseload_by_risk_group_", "", regex=False)
monthly_long["share"] = monthly_long["caseload"] / monthly_long["medicaid_caseload"]
assert monthly_long.groupby("month")["share"].sum().round(6).eq(1).all(), "shares should sum to 1 per month"


# 5 Which months are estimated?
monthly["is_estimated"] = monthly["medicaid_caseload"].mod(1) != 0
est_months = monthly.loc[monthly["is_estimated"], "month"]
FIRST_ESTIMATED_MONTH = min(est_months)
LAST_WHOLE_NUMBER_MONTH = monthly.loc[~monthly["is_estimated"], "month"].max()
assert FIRST_ESTIMATED_MONTH  >  LAST_WHOLE_NUMBER_MONTH, f"{FIRST_ESTIMATED_MONTH:%b %Y} comes before {LAST_WHOLE_NUMBER_MONTH:%b %Y}"
if monthly["hhs_incomplete"].any():
    FIRST_HIGHLIGHTED_MONTH = monthly.loc[monthly["hhs_incomplete"], "month"].min()
    LAST_UNHIGHLIGHTED_MONTH = monthly.loc[~monthly["hhs_incomplete"], "month"].max()
    assert FIRST_HIGHLIGHTED_MONTH > LAST_UNHIGHLIGHTED_MONTH, f"{FIRST_HIGHLIGHTED_MONTH:%b %Y} comes before {LAST_UNHIGHLIGHTED_MONTH:%b %Y}"
    highlighted_months = monthly.loc[monthly["hhs_incomplete"], "month"]
    bad = monthly.loc[monthly["hhs_incomplete"] & ~monthly["is_estimated"], "month"].dt.strftime("%b %Y").tolist()
    assert not bad, f"HHS highlights these months, but they have whole-number caseloads: {bad}"
    print(f"HHS marks {highlighted_months.min():%b %Y} to {highlighted_months.max():%b %Y} as incomplete; decimals begin {FIRST_ESTIMATED_MONTH:%b %Y}")
   
# NOTE: whole-number-or-not is a PROXY. Confirm against the HHS sheet's footnotes before labeling 'incomplete'.


# 6 Month-over-month change, two baselines, two scores
WINDOW = 12          # months of history in each baseline
THRESH = 3           # spreads from the baseline median (or mean) that count as unusual
K = 1.4826           # 1 / 0.6745: puts MAD on the standard-deviation scale

monthly["mom_pct"] = monthly["medicaid_caseload"].pct_change()
past = monthly["mom_pct"].shift(1)          # shift(1): a month is never inside its own baseline

# Baseline A, the first method: mean and standard deviation
base_mean = past.rolling(WINDOW).mean()
base_std = past.rolling(WINDOW).std()
# Baseline B, the robust method: median and scaled MAD
base_med = past.rolling(WINDOW).median()
base_mad = past.rolling(WINDOW).apply(lambda x: np.median(np.abs(x - np.median(x))), raw=True)
base_scale = K * base_mad

monthly["z_mean_sd"] = (monthly["mom_pct"] - base_mean) / base_std
monthly["z_robust"] = (monthly["mom_pct"] - base_med) / base_scale
monthly["gap_pp"] = (monthly["mom_pct"] - base_med) * 100          # signed: direction matters for a reader

# Guards on the CODE (these fail only if the code is wrong, never because the data is eventful)
assert monthly["z_robust"].notna().sum() == n - WINDOW - 1   # 12 = changes a baseline needs; 1 = first month has no change. Same 13 as the trace: 1 (pct_change) + 1 (shift) + 11 (window warm-up)
assert (base_scale.dropna() > 0).all(), "a zero spread would make z infinite"
assert np.isfinite(monthly["z_robust"].dropna()).all()
assert np.isfinite(monthly["z_mean_sd"].dropna()).all()

# The flags, per method
MIN_MOVE = monthly["gap_pp"].abs().median()      # the typical month's distance from its baseline, in points
monthly["flag_mean_sd"] = monthly["z_mean_sd"].abs() > THRESH
monthly["flag_robust"] = monthly["z_robust"].abs() > THRESH
monthly["meets_min_move"] = monthly["gap_pp"].abs() >= MIN_MOVE
monthly["flag_robust_min"] = monthly["flag_robust"] & monthly["meets_min_move"]

n_scored = int(monthly["z_robust"].notna().sum())
p = 2 * stats.norm.sf(THRESH)
print(f"scored months: {n_scored}")
print(f"chance alone would flag about {p * n_scored:.1f} at {THRESH} spreads")
print(f"mean/sd flags: {int(monthly['flag_mean_sd'].sum())}   "
      f"median/MAD flags: {int(monthly['flag_robust'].sum())}   "
      f"with minimum move ({MIN_MOVE:.3f} points): {int(monthly['flag_robust_min'].sum())}")
print(monthly.loc[monthly["flag_robust"], ["month", "mom_pct", "z_mean_sd", "z_robust", "gap_pp"]]
      .round({"mom_pct": 4, "z_mean_sd": 2, "z_robust": 2, "gap_pp": 3}))
## Sources for the two long runs (timeline facts, not causes):
#   Apr-Aug 2020: federal continuous-coverage rule in effect since Mar 2020.
#   Jun-Dec 2023: continuous coverage ended Mar 31, 2023; HHSC's first disenrollments could take effect Jun 1, 2023 (check slide 6 before printing that date).
#   HHSC: https://www.hhs.texas.gov/sites/default/files/documents/ending-continuous-medicaid-coverage-webinar-slides.pdf
#   KFF:  https://www.kff.org/medicaid/issue-brief/10-things-to-know-about-the-unwinding-of-the-medicaid-continuous-enrollment-provision/
# the three months after the crash
after = (monthly["month"] >= "2023-10-01") & (monthly["month"] <= "2023-12-01")
assert after.sum() == 3, "the Oct-Dec 2023 mask should select exactly three months"
missed = monthly.loc[after & ~monthly["flag_robust"], "month"].dt.strftime("%b %Y").tolist()
assert not missed, f"flag_robust should be true for Oct-Dec 2023, but is false for: {missed}"
wrongly_flagged = monthly.loc[after & monthly["flag_mean_sd"], "month"].dt.strftime("%b %Y").tolist()
assert not wrongly_flagged, f"flag_mean_sd should be false for Oct-Dec 2023, but is true for: {wrongly_flagged}"

# 6B who moved
group_long = (monthly[["month"] + RISK_COLS]
              .melt(id_vars="month", var_name="group", value_name="caseload"))
group_long["group"] = group_long["group"].str.replace("caseload_by_risk_group_", "", regex=False)
group_long = group_long.sort_values(["group", "month"])
group_long["pct_change"] = group_long.groupby("group")["caseload"].pct_change() * 100
group_long["change_people"] = group_long.groupby("group")["caseload"].diff()

total_change = monthly.set_index("month")["medicaid_caseload"].diff()
group_long["total_change"] = group_long["month"].map(total_change)
group_long["share_of_move"] = group_long["change_people"] / group_long["total_change"] * 100

flagged = monthly.set_index("month")[["flag_mean_sd", "flag_robust"]].any(axis=1)
group_long.loc[~group_long["month"].map(flagged), "share_of_move"] = np.nan
assert (group_long["share_of_move"].notna().sum()) == 6 * int(flagged.sum()), f"should have 6 groups"
by_month = group_long.groupby("month")["change_people"].sum()
assert by_month.index.equals(total_change.index), "months are not in the same order"
off = by_month.iloc[1:].index[~np.isclose(by_month.iloc[1:], total_change.iloc[1:])]
assert len(off) == 0, f"group changes do not add up to the statewide change in: {list(off.strftime('%b %Y'))}"
group_long = group_long[["month", "group", "pct_change", "change_people", "share_of_move"]]

# 6C 
def score_series(caseload):
    mom = caseload.pct_change()
    past = mom.shift(1)
    base_mean, base_std = past.rolling(WINDOW).mean(), past.rolling(WINDOW).std()
    base_med = past.rolling(WINDOW).median()
    base_scale = K * past.rolling(WINDOW).apply(lambda x: np.median(np.abs(x - np.median(x))), raw=True)
    out = pd.DataFrame({"caseload": caseload, "mom_pct": mom})
    out["z_mean_sd"] = (mom - base_mean) / base_std
    out["z_robust"] = (mom - base_med) / base_scale
    out["gap_pp"] = (mom - base_med) * 100
    assert out["z_robust"].notna().sum() == len(caseload) - WINDOW - 1, "scored months should be len - 12 - 1"
    assert (base_scale.dropna() > 0).all() and np.isfinite(out["z_robust"].dropna()).all()
    out["min_move"] = out["gap_pp"].abs().median()          # per series: each group has its own scale
    out["flag_mean_sd"] = out["z_mean_sd"].abs() > THRESH
    out["flag_robust"] = out["z_robust"].abs() > THRESH
    out["flag_robust_min"] = out["flag_robust"] & (out["gap_pp"].abs() >= out["min_move"])
    return out

series = {ALL_LABEL: monthly["medicaid_caseload"]}
series.update({KEY2LABEL[c.replace("caseload_by_risk_group_", "")]: monthly[c] for c in RISK_COLS})
parts = []
for label, s in series.items():
    r = score_series(s)
    r.insert(0, "group", label); r.insert(0, "month", monthly["month"])
    parts.append(r)
group_trend = pd.concat(parts, ignore_index=True)

all_rows = group_trend[group_trend["group"] == ALL_LABEL]
for col in ["z_mean_sd", "z_robust", "gap_pp"]:
    assert np.allclose(all_rows[col].to_numpy(), monthly[col].to_numpy(), equal_nan=True), f"{col}: All groups differs from statewide"
for col in ["flag_mean_sd", "flag_robust", "flag_robust_min"]:
    assert (all_rows[col].to_numpy() == monthly[col].to_numpy()).all(), f"{col}: All groups differs from statewide"
assert np.isclose(all_rows["min_move"].iloc[0], MIN_MOVE), "min_move: All groups differs from statewide"

# 7 County shares
# Unknown has no county, so there is no polygon to draw. It stays in the data and in every total; the footnote reports its share.

county["on_map"] = county["county_code"] <= 254
assert county.loc[~county["on_map"], "county"].tolist() == ["Unknown"], "only the Unknown row should be off the map"

CRISK = [c for c in county.columns if c.startswith("caseload_by_risk_group_")]
for c in CRISK:
    county["share_" + c.replace("caseload_by_risk_group_", "")] = county[c] / county["medicaid_caseload"]
assert county["county"].is_unique and county.filter(like="share_").notna().all().all()
assert (county.filter(like="share_").sum(axis=1).round(6) == 1).all(), "shares should sum to 1 per county"


# 8 Reconcile county to state
unknown_caseload = county.loc[~county["on_map"], "medicaid_caseload"].sum()
unknown_share = unknown_caseload / county["medicaid_caseload"].sum()
print(f"unknown: {unknown_caseload:,.0f} ({unknown_share:.3%}) stays in the data, off the map")


sfy = monthly[(monthly["month"] >= "2024-09-01") & (monthly["month"] <= "2025-08-01")]
assert len(sfy) == 12
final_gap = abs(county["medicaid_caseload"].sum() - sfy["medicaid_caseload"].mean()) / sfy["medicaid_caseload"].mean()
county_total = county["medicaid_caseload"].sum()
sfy_average = sfy["medicaid_caseload"].mean()
assert np.isclose(county_total, sfy_average, rtol=1e-8), \
    f"final county sum {county_total:,.2f} != SFY25 monthly average {sfy_average:,.2f}"
print(group_trend.groupby("group")[["flag_mean_sd", "flag_robust", "flag_robust_min"]].sum())

# 9 Export the Stage 2 hand-off files
trend = monthly[["month", "medicaid_caseload", "mom_pct", "gap_pp", "z_mean_sd", "z_robust",
                 "flag_mean_sd", "flag_robust", "meets_min_move", "flag_robust_min", "is_estimated", "hhs_incomplete"]]
mix = monthly_long.merge(monthly[["month", "is_estimated"]], on="month")
county_out = county[["county_code", "county", "medicaid_caseload"] + [c for c in county.columns if c.startswith("share_")] + ["on_map"]]
for name, df in [("hhs_monthly_stage2.csv", trend), ("hhs_mix_stage2.csv", mix),
                 ("hhs_county_stage2.csv", county_out), ("hhs_group_moves_stage2.csv", group_long),
                 ("hhs_group_trend_stage2.csv", group_trend)]:
    assert len(df) > 0
    print(write_atomic(df, name), df.shape)
