# Stage 4 ledger

Spec: factory/stage-4/spec.md (stages 1-3 still apply: factory/stage-1/spec.md, stage-2/spec.md, stage-3/spec.md; earlier rows stay met).
Owners: A = builder-a, B = builder-b. Check: S = supplied harness, P = examiner probe. Status: open until examiner accepts.

Layout (stage-4/, copy of stage-3/):
- A: build.py, candidates.py, support.py, timeline.py, ui*.py, measure.py (lineage, origins, investors extraction/assembly/typing/values_at, provider failure handling in build, UI).
- B: store.py, server.py, Dockerfile, RUN.md (batches, shared budget, corroborated_since, investors history/feed, restart, import).

Interfaces (agree details directly in the room):
- `build.run_build(domain, now_iso, should_abort, budget=None)`: budget is B's thread-safe object with `reserve(n)->bool` / `settle(reserved, actual)`; the build reserves a call's max cost before each call and makes no call when refused. Result `fields` has 8 fields; every candidate carries `origin`; A computes `origins` and `corroborated`; B stamps `corroborated_since`.
- B stores per build the candidates by field (as stage 3) and derives standing origins and corroborated_since from them.
- `timeline.classify(field, prev, new)` handles investors (A). `timeline.values_at` handles investors (A). A provides pure `timeline.investor_members(cands)`.
- A returns the build's total spend and whether every provider call failed (-> failed outcome per section 8).

| ID | Statement | Owner | Check | Work | Status |
|---|---|---|---|---|---|
| R-01 | Lineage header lines `Registrant:`, `Canonical:`, `First-Published-By:` parsed; domains and Canonical host normalised as section 4 | A | P | W-1 | open |
| R-02 | Page with no valid Registrant line: registrant = normalised host of its own URL | A | P | W-1 | open |
| R-03 | Kind `own` only when registrant == company domain; other page stating `Kind: own` is aggregator for selection and its candidates report "aggregator" | A | P | W-1 | open |
| R-04 | Lookalike = states `Kind: own` and registrant is not the normalised host of its own URL | A | P | W-1 | open |
| R-05 | Origin rule 1: First-Published-By domain | A | P | W-1 | open |
| R-06 | Origin rule 2: Canonical URL not the page's own URL -> origin of the original; build obtains each needed original from a provider | A | P | W-2a | open |
| R-07 | Origin rule 3: lookalike -> company's domain; rule 4: registrant | A | P | W-1 | open |
| R-08 | Rule 2 follows at most 3 Canonical URLs in a row; at a fourth, or where no provider serves the URL, the URL host replaces the original's origin | A | P | W-2a | open |
| R-09 | Pages with same origin are one source whatever URL/provider/kind; candidates carry `origin` | A | P | W-2a | open |
| R-10 | Originals fetched stay within build cap 80 units and shared budget | A | P | W-2a | open |
| R-11 | Field `origins`: distinct origins of candidates with the selected value, sorted asc; [] when unknown | A | P | W-2b | open |
| R-12 | Field `corroborated` true iff origins has >=2 entries | A | P | W-2b | open |
| R-13 | Imported candidates with no recorded origin take normalised host of their URL | B | P | W-12 | open |
| R-14 | `corroborated_since`: time of earliest ready build after which selected value has had >=2 standing origins, else null | B | P | W-8 | open |
| R-15 | Standing origins = origins of every candidate with that value gathered by any ready build since the value became selected (learned_at of latest history entry), even if later builds dropped it; new selected value starts with none | B | P | W-8 | open |
| R-16 | Imported candidates count as gathered at imported researched_at; stage-3 export builds: candidates of each build count as gathered at that build's time | B | P | W-12 | open |
| R-17 | Executives origins: distinct origins of candidates of all members (member = title+name), sorted; [] unknown | A | P | W-2b | open |
| R-18 | Executives corroborated true iff every member's candidates have >=2 distinct origins; false otherwise and when unknown | A | P | W-2b | open |
| R-19 | Executives corroborated_since: earliest ready build after which every member has >=2 standing origins (member standing origins = candidates gathered by the build after which it last became a member or later); null if some member has fewer or unknown | B | P | W-8 | open |
| R-20 | Eighth field `investors` after `executives` in every response listing fields (dossier, as_of, history, values) | B | P | W-9 | open |
| R-21 | Feed entries one build adds numbered with investors last | B | P | W-9 | open |
| R-22 | Investors is an Appendix-A field with phrases investor, investors, led by, backed by, participated | A | P | W-3 | open |
| R-23 | Company name and phrases removed first and separate words; runs of capitalised words (A.4) joined by single spaces, not part of a longer run; run of >=2 words ending Ventures/Capital/Partners/Fund/Investments/Holdings/Equity = investor name | A | P | W-3 | open |
| R-24 | In an excerpt containing an amount (A.4), run starting directly after `led by`/`backed by` + one space is an investor name whatever length/last word; "Acme Robotics is led by Dana Ruiz." names none | A | P | W-3 | open |
| R-25 | Investor name normalises to text as excerpt writes it; A.2 rules 1-4 apply; excerpt supports each name it contains (replaces rule 5) | A | P | W-3 | open |
| R-26 | Candidate value of investors is one investor name; a research claim is never an investors candidate | A | P | W-3 | open |
| R-27 | Member = name with a candidate of kind own or filing, or candidates with that name from >=2 distinct origins | A | P | W-4 | open |
| R-28 | investors value = sorted (code point) array of member names, null when none; known iff a member exists, else unknown | A | P | W-4 | open |
| R-29 | investors candidates: `selected` true iff name is a member; listed in stage-2 rank order | A | P | W-4 | open |
| R-30 | investors citations: per member in value order, url/excerpt/provider of every candidate with the name, rank order | A | P | W-4 | open |
| R-31 | Member true_from = earliest non-null true_from among its candidates, else null; field true_from = latest member true_from, null if value null or any member null | A | P | W-4 | open |
| R-32 | investors origins/corroborated/corroborated_since follow members (as executives): candidates with the member's name | A,B | P | W-4,W-8 | open |
| R-33 | investors candidate learned_at keyed by name+URL+provider; field/value learned_at as other fields | B | P | W-9 | open |
| R-34 | /values decides investors membership from candidates at true_at; value, true_from, citations by R-27..R-31 | A | P | W-5 | open |
| R-35 | investors history/feed typing by name: new name counts as correction iff its true_from and earlier value's true_from non-null and its true_from <= earlier's; entry `correction` iff every name in exactly one of the two values counts as a correction, else `change` | A | P | W-5 | open |
| R-36 | investors history/feed entries: one per ready build whose value differs, initial rules as stage 3 | B | P | W-9 | open |
| R-37 | Screens: investors takes none of the stage-2 data-testids; /contested "no field is contested" considers only the six section-4 fields | A | P | W-6 | open |
| R-38 | POST /batches idempotent write path; Idempotency-Key required (section 7); counts as provider-calling request (section 8) | B | P | W-7 | open |
| R-39 | 202 shape: batch_id, state running, budget_units, spent_units, dossiers [{domain,state}] in order given, normalised | B | P | W-7 | open |
| R-40 | 422 validation_failed: domains missing/empty/>50/invalid after normalisation/duplicates after normalisation | B | P | W-7 | open |
| R-41 | 422 validation_failed: budget_units missing, not integer (string, true, 1.5 included), <1 or >100000; wins over 400 malformed for wrong JSON type | B | P | W-7 | open |
| R-42 | Domain with no dossier gets one and the batch runs its first build; existing dossier not researched and costs batch nothing | B | P | W-7 | open |
| R-43 | batch spent_units = total cost of its builds' calls, never exceeds budget_units; each build <=80 and counts in its dossier's spent_units | B | P | W-10 | open |
| R-44 | When budget would be exceeded by a further call, batch makes no more calls; remaining builds complete with pages/claims obtained, each field known exactly when those support a value | A,B | P | W-10,W-2 | open |
| R-45 | GET /batches/{id}: same shape; state running while any build runs then done; unknown or other user's batch 404 not_found; auth 401 | B | P | W-7 | open |
| R-46 | Op list 5: spending never exceeds a budget the spec or caller sets (80/build, batch budget) | A,B | P | W-10 | open |
| R-47 | Provider 5xx/429 errors: build continues, may retry same request through same or another provider | A | P | W-11 | open |
| R-48 | Calls to one or more providers all failing while nimble answers: build ready with every field known that reachable evidence supports | A | P | W-11 | open |
| R-49 | Every research run failing while search/extract answer: ready with everything search+extract support | A | P | W-11 | open |
| R-50 | Every call to every provider failing: build failed (section 8) within section 8 time bound | A | P | W-11 | open |
| R-51 | Call refused with error status costs nothing (section 9) | A | P | W-11 | open |
| R-52 | Restart: batches persisted like other state; everything else still answered while builds were running at stop | B | P | W-13 | open |
| R-53 | Restart: a running build ends ready/failed within 10 s of /health 200 (calls answering within 1 s); if failed, fields as before | B | P | W-13 | open |
| R-54 | A build is one build across restart: calls before+after spend <=80; a batch's builds together <= budget_units | B | P | W-13 | open |
| R-55 | Every billed unit before and after restart counted in dossier spent_units and batch spent_units (in-flight unbilled may also count) | B | P | W-13 | open |
| R-56 | After restart POST refresh starts a new build of each such dossier | B | P | W-13 | open |
| R-57 | Import of stage-1/2/3 export keeps dossiers, candidates, history, feed, idempotent responses; citations remain served | B | P | W-12 | open |
| R-58 | Stage-3 export keeps builds; after upgrade as_of and /values answer from them as before, with new keys | B | P | W-12 | open |
| R-59 | After import investors is unknown in imported state and every kept build, no history entry; first ready build with a value adds `change` (or `initial` if first ready build of dossier) | B | P | W-12 | open |
| R-60 | Stages 1-3 behaviour unchanged (supplied checks stages 1-3) | A,B | S | all | open |
| R-61 | Failed builds contribute nothing to standing origins / corroborated_since (ready builds only) (exam E4-26) | B | P | W-8 | open |
| R-62 | After restart a batch becomes `done` once its builds end (E4-69) | B | P | W-13 | open |
| R-63 | Batch ids do not collide after restart or import (E4-75) | B | P | W-13 | open |
| R-64 | Canonical equal to the page's own URL: rule 2 does not apply; Canonical cycles terminate via the 3-follow limit (E4-14/15) | A | P | W-2a | open |
| R-65 | Invalid Registrant or Canonical/First-Published-By value: invalid Registrant falls back to own-URL host; invalid lineage domains are ignored (E4-06) | A | P | W-1 | open |
