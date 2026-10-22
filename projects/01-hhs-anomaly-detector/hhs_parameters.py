"""
hhs_parameters.py
-----------------
The allowed values for the three Tableau string parameters, built in Python so no value is typed in Tableau.
  p.Group        the seven group labels             default "All groups"
  p.Show Method  the three method labels            default "Median and MAD, all flagged"
  p.Month        every month label, "Oct 2023"      default "Oct 2023"

  python hhs_parameters.py             writes hhs_parameters.csv and checks every Stage 3 file against it
                                       and param_group.txt, param_method.txt, param_month.txt (one value per line)
  python hhs_parameters.py group       also copies that parameter's values to the clipboard (macOS), one per line,
                                       for Tableau:  Allowable values > List > Add values from > Paste from clipboard
                                       (also: method, month)
Run it after build_hhs_canvas.py and build_hhs_selectors.py. A mismatch stops it before Tableau sees a wrong value.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

from hhs_groups import ALL_LABEL, GROUP_LABELS, METHOD_LABELS

OUT = Path.home() / "TableauData" / "Texas HHS Enrollment"

months = pd.read_csv(OUT / "hhs_monthly_stage2.csv", parse_dates=["month"])["month"].sort_values()
PARAMS = {
    "p.Group": ([ALL_LABEL] + GROUP_LABELS, ALL_LABEL),
    "p.Show Method": (METHOD_LABELS, METHOD_LABELS[1]),
    "p.Month": ([m.strftime("%b %Y") for m in months], "Oct 2023"),
}
for name, (values, default) in PARAMS.items():
    assert len(set(values)) == len(values), f"{name}: duplicate value"
    assert default in values, f"{name}: default {default!r} is not in its own list"
    assert all(v == v.strip() and "  " not in v for v in values), f"{name}: stray spaces in a value"

# Every string Tableau will compare against a parameter must be one of its values
canvas = pd.read_csv(OUT / "hhs_canvas.csv", usecols=["group", "method", "sel_month", "month_label", "group_label", "method_label"], low_memory=False)
assert set(canvas["group"].dropna()) == set(PARAMS["p.Group"][0]), "canvas `group` values differ from p.Group"
assert set(canvas["method"].dropna()) == set(PARAMS["p.Show Method"][0]), "canvas `method` values differ from p.Show Method"
for col in ["sel_month", "month_label"]:
    assert set(canvas[col].dropna()) <= set(PARAMS["p.Month"][0]), f"canvas `{col}` has a month not in p.Month"
for col, name in [("group_label", "p.Group"), ("method_label", "p.Show Method")]:
    got = set(canvas[col].dropna())
    assert got == set(PARAMS[name][0]), f"button labels in `{col}` differ from {name}: {sorted(got ^ set(PARAMS[name][0]))}"

# One text file per parameter, one value per line, so the clipboard can be refilled at any moment:
#   pbcopy < ~/TableauData/"Texas HHS Enrollment"/param_group.txt
for short, key in {"group": "p.Group", "method": "p.Show Method", "month": "p.Month"}.items():
    (OUT / f"param_{short}.txt").write_text("\n".join(PARAMS[key][0]))

rows = [dict(parameter=p, value=v, is_default=(v == d), order=i + 1)
        for p, (vals, d) in PARAMS.items() for i, v in enumerate(vals)]
out = pd.DataFrame(rows)
out.to_csv(OUT / "hhs_parameters.csv", index=False)
print(out.groupby("parameter").agg(values=("value", "size"), default=("value", lambda s: s[out.loc[s.index, "is_default"]].iloc[0])))

if len(sys.argv) > 1:
    key = {"group": "p.Group", "method": "p.Show Method", "month": "p.Month"}[sys.argv[1]]
    text = "\n".join(PARAMS[key][0])
    if shutil.which("pbcopy"):
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        print(f"copied {len(PARAMS[key][0])} values for {key} to the clipboard")
    else:
        print(text)
