import math

import pandas as pd
import pytest

from shared.flagging import flag_series
from shared.schema import from_flags, validate_output

# Twelve baseline months with two extreme ones in the middle, then a real drop.
EXTREME_BASELINE = [0.4, 0.5, 0.3, 0.6, 0.5, 0.4, 14.0, 12.0, 0.5, 0.4, 0.6, 0.5]
DROP = -5.5


def test_median_mad_catches_the_drop_that_mean_sd_misses():
    series = EXTREME_BASELINE + [DROP]
    mean_sd = flag_series(series, method="mean_sd").iloc[-1]
    robust = flag_series(series, method="median_mad").iloc[-1]
    assert not mean_sd["flag"] and abs(mean_sd["score"]) < 3     # the extremes stretched the yardstick
    assert robust["flag"] and abs(robust["score"]) > 30           # the median and MAD ignored them


def test_hand_calculation_for_median_mad():
    r = flag_series(EXTREME_BASELINE + [DROP], method="median_mad").iloc[-1]
    assert r["expected"] == pytest.approx(0.5)                    # median of the twelve
    assert r["spread"] == pytest.approx(1.4826 * 0.1)             # MAD is 0.1
    assert r["score"] == pytest.approx((DROP - 0.5) / (1.4826 * 0.1))


def test_first_window_rows_are_not_scored():
    r = flag_series(EXTREME_BASELINE + [DROP])
    assert r["score"].iloc[:12].isna().all() and not r["flag"].iloc[:12].any()


def test_zero_spread_gives_no_score_and_no_flag():
    r = flag_series([1.0] * 12 + [5.0]).iloc[-1]
    assert math.isnan(r["score"]) and not r["flag"]


def test_min_move_ignores_tiny_gaps_in_a_quiet_baseline():
    quiet = [1.00, 1.01, 0.99, 1.00, 1.01, 0.99, 1.00, 1.01, 0.99, 1.00, 1.01, 0.99]
    assert flag_series(quiet + [1.06]).iloc[-1]["flag"]                       # far in spread terms
    assert not flag_series(quiet + [1.06], min_move=0.1).iloc[-1]["flag"]     # but only 0.06 away


def test_output_table_contract():
    f = flag_series(EXTREME_BASELINE + [DROP])
    out = from_flags(f, entity="state", group="All groups", metric="mom_pct", periods=range(13), method="median_mad")
    validate_output(out)
    with pytest.raises(ValueError):
        validate_output(pd.concat([out, out]))                    # duplicate keys
