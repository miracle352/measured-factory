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
- Stage 1 closing: review rounds 2 (API at b7b523f, support.py at eb22aeb, then full at d34251d); examiner rows added 2; failures caught in product code: 0 (examiner-side probe fixes only); outside-call cost: mock only, max 47 units/build; probes 1068 + 179 passed; examiner accepted d34251d (stage-1/ unchanged to final). Final isolated check r-s1-1: "claimed stage: 1".

## Stage 2
- Cost per correct result (mock, 12 companies x 2 epochs; raw: factory/stage-2/measure-raw.md):

| Strategy | Units | Correct | Cost/correct | Max single build |
|---|---|---|---|---|
| rendered extract + research + follow-ups (chosen) | 804 | 62 | 12.97 | 72 |
| plain extract + research + follow-ups | 486 | 62 | 7.84 | 42 |
| rendered, no follow-ups | - | - | 15.82 | - |
| rendered, no research | - | - | 8.93 | - |

- Choice: rendered. Plain is cheaper on the mock but the spec's page text is browser text; plain text may differ from it on the hidden corpus. 429 weather gave identical results (24 refused calls each, no cost).
- Deviations: builder-a W-2/W-4/W-5 code in d84c604 (marker commits d658edf, a403779); W-3/W-3b code in f88e425 (45bd83a marker). builder-b W-10..W-12 code in ui_pages.py commit; feb3484 only RUN.md.
- Rows added by examiner: 11 (R-60..R-70).
- Stage 2 closing: review rounds 2 (interim at feb3484 found 1 product-code failure: contested item missing field identifier; final at 73a7655); examiner rows added 11; failures caught in product code 1 (plus 1 low-risk note: Kind case, resolved by ruling); outside-call cost: mock only, max 72 units/build (limit 80); examiner probes 44 passed, 1 skipped (p08 browser-only page, no such page in the mock corpus); isolated check r-s2-x1: stage 1 122 passed, stage 2 12 passed, "claimed stage: 2". Uncovered: browser-only page text, kernel/browserbase sessions (unused), live providers, R-25 numbers not audited.
- Time: dispatch and accept timestamps are in room-log; review rounds 2.
