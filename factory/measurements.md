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

## Stage 3
- Rows added by examiner: 3 (R-71..R-73, from exam list E-33/E-39/E-46); ledger total 73.
- Review rounds: 2 interim (aaf8ddb host runs ex-s3-1..4; ex-s3-1 failure was an examiner probe bug, fixed in 6149490) + final at bb84cdd (isolated). Failures caught in product code: 0; one builder-b fix found by its own restart/import testing (bb84cdd, R-58/R-59 learned_at of imported builds).
- Deviations: builder-b's store.py commit 87f1b54 carries W-6a, W-6b, W-7/W-8/W-9/W-10/W-11 store code (about 30 rows) in one commit; server.py (7283c9f) and Dockerfile/RUN.md (aaf8ddb) separate. Not split (single file).
- Outside-call cost: no cost defined for stage 3; build path unchanged from stage 2 (mock, max 72 units/build, limit 80); no new measurement run.
- Final: examiner accepted bb84cdd78beb38b9035485ccfe10bff5e1054b97. Isolated check final-iso: stage 1 122, stage 2 12, stage 3 9 passed; examiner probes 66/66 isolated (53 API, 4 UI, 9 supplied). Uncovered: stage-2 export builds-list schema is a guess (our stage-2 exports carry none); live contested/unknown executives states and loading/error states only via mocked screenshots; concurrency stress only builder-b's 3-dossier run and examiner's two-refresh probe.
- Time: dispatch and accept timestamps are in the room log; interim rounds 2 plus final 1.

## Stage 4
- Rows added by examiner: 5 (R-61..R-65); ledger total 65.
- Review rounds: 3 against builds (interim f27a809/89c06e4 found the restart overspend, fixed 00d4835; 4695fb1 found the 80-unit cap defect on originals, fixed 32129f9; final 3a05d10 accepted) plus a screens round (d7ff845).
- Failures caught in product code: 3 (restart billed 204 vs batch budget 150; build billed 92 vs cap 80 because an in-band 404 extract, which is billed, was settled as free and retried; screens: self-contradicting corroboration line and raw field key visible on /contested).
- Deviations: builder-b store.py 7e5b218 carries about 20 rows (R-13..16,19..21,33,36,43,44,46,52..59,61..63) in one commit (single intertwined file); builder-a dfbc5d8 also carries the originals-fetching loop and budget hook (R-06,08,09,10,44,46).
- Outside-call cost: no new measurement run (mock, build cost cap 80 units/build, batch budget enforced; originals fetched via rendered extract at 3 units).
- Final: examiner accepted 3a05d10 (stage-4 code = 32129f9). Isolated: own probes 50/50, supplied stages 1-4 all pass, rig 16/16 on crafted corpus. Uncovered: screen states other than stubbed known/unknown/contested investors (loading, error, fully corroborated, evidence page); restart probed with one batch.
