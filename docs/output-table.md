# The output table

Every project writes one table with these columns. A dashboard builder reads only this, so a new dataset never touches the builder.

| Column | Meaning |
|---|---|
| `entity` | What is being measured: campus, county, state |
| `group` | The segment: a program, a student group, "All" |
| `period` | Month, term or year label |
| `metric` | What the number is, e.g. `mom_pct` |
| `observed` | The actual value |
| `expected` | What the baseline or model predicts |
| `lower`, `upper` | The band around `expected`; always show it, never a bare number |
| `score` | Gap divided by spread; empty when the baseline has no spread |
| `flag` | True when the score is past the threshold (and past any minimum move) |
| `method` | Which method produced the row, e.g. `median_mad` |

Rules, enforced by `shared/schema.py`: one row per `entity, group, period, metric, method`; `lower <= expected <= upper`; no flag without a score.
