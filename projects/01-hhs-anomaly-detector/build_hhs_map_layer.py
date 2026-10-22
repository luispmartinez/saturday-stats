"""
build_hhs_map_layer.py   (Stage 3 helper)
County outlines for the map panel, one copy per view: "All groups" plus the six risk groups.
Reads hhs_county_stage2.csv and the Census 1:5,000,000 county shapefile in geo/.
Writes hhs_map_layer.csv; build_hhs_canvas.py reads it like any Stage 2 file.

Map rules, all guarded below:
  - the outline comes from a NAME join. HHSC and Census alphabetize the "Mc" counties differently, so the
    code formula (2 x code - 1) is wrong for exactly nine counties and is kept only as a cross-check
  - longitude is scaled by cos(latitude) so Texas keeps its shape
  - each ring loses its repeated closing point; each part of a county gets its own poly_id
  - the Unknown county has no outline; it stays in every total and is reported in the footnote
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import shapefile                                          # pyshp

from hhs_groups import ALL_LABEL, KEY2LABEL

HERE = Path(__file__).parent
OUT = Path.home() / "TableauData" / "Texas HHS Enrollment"          # local disk, never iCloud
SHP = HERE / "geo" / "cb_2024_us_county_5m.shp"
MAP_X0, MAP_X1, MAP_Y0, MAP_Y1 = 690, 1010, 560, 870                 # map card interior, sketch pixels (must match build_hhs_canvas.py)
NBINS = 5                                                           # quantile color steps per view


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


# A Read the boundaries, keep Texas
county = pd.read_csv(OUT / "hhs_county_stage2.csv")
state_total = county["medicaid_caseload"].sum()      # all 255 rows, so "All groups" shares are of the statewide total
sf = shapefile.Reader(str(SHP))
fields = [f[0] for f in sf.fields[1:]]
recs = [dict(zip(fields, r)) for r in sf.records()]
tx_idx = [i for i, r in enumerate(recs) if r["STATEFP"] == "48"]      # Texas's FIPS state code
assert len(tx_idx) == 254, len(tx_idx)

# B Join counties to outlines: the name decides, the code formula cross-checks
def norm(s):
    return re.sub(r"[^a-z]", "", s.lower())                           # keep letters only: "De Witt" == "DeWitt"

county = county[county["on_map"]].copy()
county["fips_rule"] = (county["county_code"] * 2 - 1).astype(str).str.zfill(3)
by_name = {norm(recs[i]["NAME"]): i for i in tx_idx}
by_fips = {recs[i]["COUNTYFP"]: i for i in tx_idx}
county["shp_i_name"] = county["county"].map(lambda s: by_name.get(norm(s)))
county["shp_i_fips"] = county["fips_rule"].map(by_fips)
assert county["shp_i_name"].notna().all() and county["shp_i_name"].is_unique, "the name join must be complete and one-to-one"
assert county["shp_i_fips"].notna().all()
county["shp_i"] = county["shp_i_name"]

KNOWN_FORMULA_MISMATCHES = {"Madison", "Marion", "Martin", "Mason", "Matagorda",
                            "Maverick", "McCulloch", "McLennan", "McMullen"}
off = set(county.loc[county["shp_i_name"] != county["shp_i_fips"], "county"])
assert off == KNOWN_FORMULA_MISMATCHES, f"formula disagrees on a different set: {sorted(off ^ KNOWN_FORMULA_MISMATCHES)}"

# C Project longitude/latitude into the panel
pts = np.vstack([np.array(sf.shape(int(i)).points) for i in county["shp_i"]])
lat0 = np.radians(pts[:, 1].mean())
px, py = pts[:, 0] * np.cos(lat0), pts[:, 1]
minx, maxx, miny, maxy = px.min(), px.max(), py.min(), py.max()
scale = min((MAP_X1 - MAP_X0) / (maxx - minx), (MAP_Y1 - MAP_Y0) / (maxy - miny))
assert 1.0 < (maxx - minx) / (maxy - miny) < 1.1, "aspect ratio looks wrong; check the longitude correction"


def project(lon, lat):
    x = MAP_X0 + (lon * np.cos(lat0) - minx) * scale
    y = MAP_Y1 - (lat - miny) * scale                                # pixels grow down, latitude grows up
    return x, y


def ring_area(r):                                                    # shoelace formula; positive = counter-clockwise
    x, y = r[:, 0], r[:, 1]
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)


ccw = 0
for i in county["shp_i"]:
    s = sf.shape(int(i))
    edges = list(s.parts) + [len(s.points)]
    for a, b in zip(edges[:-1], edges[1:]):
        if ring_area(np.array(s.points[a:b])) > 0:
            ccw += 1
assert ccw == 0, "counter-clockwise rings (holes) found; handle before Tableau"

# D One polygon per county part
rows = []
for _, c in county.iterrows():
    shp = sf.shape(int(c["shp_i"]))
    edges = list(shp.parts) + [len(shp.points)]
    for k in range(len(edges) - 1):
        ring = np.array(shp.points[edges[k]:edges[k + 1]])
        while len(ring) > 3 and (ring[0] == ring[-1]).all():
            ring = ring[:-1]
        x, y = project(ring[:, 0], ring[:, 1])
        part = pd.DataFrame({"x_px": x, "y_px": y})
        part["poly_id"] = f"county|{int(c['county_code']):03d}|{k}"
        part["point_order"] = np.arange(1, len(part) + 1)
        part["county_code"] = int(c["county_code"])
        rows.append(part)
county_poly = pd.concat(rows, ignore_index=True)
assert county_poly["county_code"].nunique() == 254
assert county_poly["x_px"].between(MAP_X0 - 1e-6, MAP_X1 + 1e-6).all()
assert county_poly["y_px"].between(MAP_Y0 - 1e-6, MAP_Y1 + 1e-6).all()


def end_gap(g):
    a = g[["x_px", "y_px"]].iloc[0].to_numpy()
    b = g[["x_px", "y_px"]].iloc[-1].to_numpy()
    return float(np.hypot(*(a - b)))


gaps = county_poly.groupby("poly_id").apply(end_gap)
assert (gaps > 1e-6).all(), f"rings still closed by a repeated point: {gaps[gaps <= 1e-6].index.tolist()}"
src_points = sum(len(sf.shape(int(i)).points) for i in county["shp_i"])
assert len(county_poly) == src_points - len(gaps), f"expected {src_points - len(gaps)} rows, got {len(county_poly)}"
print(len(county_poly), "county rows;", len(gaps), "rings")

# E Seven views: one color step and one tooltip per county per view
views = [(ALL_LABEL, None)] + [(label, key) for key, label in KEY2LABEL.items()]
parts = []
for label, key in views:
    v = county[["county_code", "county", "medicaid_caseload"]].copy()
    v["share"] = county["medicaid_caseload"] / state_total * 100 if key is None else county["share_" + key] * 100
    # Q1 = lowest share ... Qk = highest. Text, not a digit: Tableau types a digit-like column as a measure and
    # colors COUNTD(Step) instead of Step (every county in one color, every legend swatch identical).
    v["step"] = "Q" + (pd.qcut(v["share"], NBINS, labels=False, duplicates="drop") + 1).astype(str)
    v["group"] = label
    what = "of statewide caseload" if key is None else label.lower()
    v["tooltip"] = (v["county"] + ": " + v["share"].round(1).astype(str) + "% " + what + ", "
                    + v["medicaid_caseload"].round(0).astype(int).map("{:,}".format) + " average monthly caseload")
    parts.append(v)
views_df = pd.concat(parts, ignore_index=True)
assert len(views_df) == 7 * 254 and views_df["group"].nunique() == 7
assert views_df["step"].notna().all()
county_map = county_poly.merge(views_df.drop(columns="medicaid_caseload"), on="county_code")
assert len(county_map) == 7 * len(county_poly), "merge changed the row count"
county_map["layer"] = "county"
assert not county_map.duplicated(["group", "poly_id", "point_order"]).any()

# F Output
cols = ["layer", "group", "county_code", "county", "poly_id", "point_order", "x_px", "y_px", "share", "step", "tooltip"]
print(write_atomic(county_map[cols].round({"x_px": 3, "y_px": 3, "share": 3}), "hhs_map_layer.csv"))
print(views_df.groupby("group")["step"].nunique())
