# Measurements

## Stage 1
- Deviation: builder-b commit c2bb1e9 covers W-6..W-10 (about 40 rows) in one commit; mandate limit is 8 rows per commit. Not split (single-file code); later fixes must be per-item commits.
- Rows added by examiner: 2 (R-72, R-73).
- Deviation: builder-a commit 0c31522 (message lists 8 rows) contains build.py logic for 22 rows (W-4a, W-4b, W-5 together); single file, not split.
- Cost per correct result (mock sample corpus, 12 company/epoch runs per strategy; raw: factory/stage-1/measure-raw.md):

| Strategy | Units | Correct | Missed | Cost/correct |
|---|---|---|---|---|
| A lite+extract+research+follow-ups (chosen) | 511 | 70 | 0 | 7.30 |
| B deep+research | 690 | 70 | 0 | 9.86 |
| C lite+extract, no research | 208 | 62 | 8 | 3.35 |
| D fast+research, no extract | 360 | 46 | 24 | 7.83 |

- Choice: A. C is cheaper but misses fields only research reaches (spec counts research claims as evidence). Max single-build spend 47 (limit 80).
