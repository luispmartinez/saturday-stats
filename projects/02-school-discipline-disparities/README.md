# 02 School discipline disparities (planned)

**Decision sentence (draft).** After seeing this, a district leader would review these campuses first.

**Question.** Which campuses sit far above what their context predicts, and where are the gaps between student groups widest?

**Approach.**
1. Measure the gaps: risk ratios by group, campus by campus, with confidence bounds.
2. Predict expected discipline from campus context (size, grade span, mobility, assessment scores as a covariate), then flag campuses far above expectation.
3. Student race and gender are what is measured, never inputs that predict discipline.

**Method cautions.** Suppressed small cells leave gaps; shrink small campuses toward the group average; control false discoveries when flagging many campuses; describe patterns, assign no blame; campus data cannot support claims about individuals.

**Sources (confirm current formats).** TEA public discipline and campus performance files.

**Status.** Dataset spec and output table first: see [`docs/output-table.md`](../../docs/output-table.md).
