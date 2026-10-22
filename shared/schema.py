"""The standard output table. Every project writes this; every dashboard builder reads only this.

One row = one entity, group, period, metric and method. See docs/output-table.md.
"""
from __future__ import annotations

import pandas as pd

OUTPUT_COLUMNS = ["entity", "group", "period", "metric", "observed", "expected",
                  "lower", "upper", "score", "flag", "method"]
KEY = ["entity", "group", "period", "metric", "method"]


def from_flags(flags: pd.DataFrame, *, entity: str, group: str, metric: str, periods, method: str) -> pd.DataFrame:
    """Turn the result of flagging.flag_series into output-table rows."""
    periods = list(periods)
    if len(periods) != len(flags):
        raise ValueError("one period label per scored value")
    df = flags[["observed", "expected", "lower", "upper", "score", "flag"]].copy().reset_index(drop=True)
    df.insert(0, "period", periods)
    df.insert(0, "group", group)
    df.insert(0, "entity", entity)
    df.insert(3, "metric", metric)
    df["method"] = method
    return df[OUTPUT_COLUMNS]


def validate_output(df: pd.DataFrame) -> pd.DataFrame:
    """Raise with a clear message if the table breaks the contract; return it unchanged if it holds."""
    missing = [c for c in OUTPUT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    if df.duplicated(KEY).any():
        raise ValueError(f"duplicate rows for key {KEY}")
    if df["flag"].dtype != bool:
        raise ValueError("flag must be a boolean column")
    scored = df["expected"].notna()
    if ((df.loc[scored, "lower"] > df.loc[scored, "expected"]) | (df.loc[scored, "expected"] > df.loc[scored, "upper"])).any():
        raise ValueError("lower must not exceed expected, and expected must not exceed upper")
    if df.loc[df["score"].isna(), "flag"].any():
        raise ValueError("a row with no score cannot be flagged")
    return df
