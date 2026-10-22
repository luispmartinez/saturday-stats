"""
hhs_groups.py: the names Stage 2, the selector builder, and the canvas builder share.
The button labels ARE the Tableau parameter values, so every table with a `group` column
must use these labels, or the parameter filter finds nothing.
"""
ALL_KEY = "all_groups"
ALL_LABEL = "All groups"          # statewide total

# Stage 2 keys (column suffixes in hhs_monthly_caseload.csv) -> button labels, in button order
KEY2LABEL = {
    "children_s_medicaid": "Children's Medicaid",
    "aged_medicare_related": "Aged, Medicare",
    "disability_related": "Disability",
    "pregnant_women": "Pregnant women",
    "parents": "Parents",
    "breast_and_cervical_cancer": "Breast, cervical cancer",
}
GROUP_LABELS = list(KEY2LABEL.values())

METHOD_LABELS = ["Mean and SD", "Median and MAD, all flagged", "Median and MAD, larger moves"]

assert len(set(GROUP_LABELS)) == len(GROUP_LABELS) and ALL_LABEL not in GROUP_LABELS
