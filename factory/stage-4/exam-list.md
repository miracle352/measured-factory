# Stage 4 exam list (examiner; from the stage-4 spec text only)

Ids E4-nn. Refs name the stage-4 spec section. Earlier-stage statements are tracked only where stage 4 touches them.

## General
- E4-01 (Intro, rule 5) Spending never exceeds a budget the spec or caller sets (per build 80 units; per batch budget_units).
- E4-02 (Intro) Three idempotent write paths: stage-1's two plus POST /batches (Idempotency-Key required, §7: replay same body = same response, different body = conflict, missing key = error per §7).
- E4-03 (Batches) POST /batches makes provider calls like POST /dossiers and refresh (§8 Builds).

## Lineage headers
- E4-04 (Lineage) Header lines `Registrant:`, `Canonical:`, `First-Published-By:` are parsed from pages.
- E4-05 Domains in these lines and the host of a Canonical URL are normalised as §4 (case, www, etc.).
- E4-06 A page without a valid Registrant line has registrant = normalised host of its own URL (invalid Registrant value => fallback).

## Own pages / lookalike
- E4-07 (Own pages) Page is kind `own` only when registrant == company domain.
- E4-08 A page stating `Kind: own` with another registrant has kind aggregator for the selection rule (stage-2), and candidates report "kind":"aggregator".
- E4-09 Lookalike = states `Kind: own` and registrant != normalised host of its own URL.

## Origins
- E4-10 Origin precedence: (1) First-Published-By domain; (2) if Canonical != own URL, origin of the page at that URL by same rules; (3) company's domain if lookalike; (4) registrant.
- E4-11 The build obtains from a provider every original rule 2 needs (extra fetch calls; cost counted).
- E4-12 Rule 2 follows at most three Canonical URLs in a row; at a would-be fourth, the host of that URL replaces the original's origin.
- E4-13 If no provider serves a page at the Canonical URL, host of that URL (normalised) is the origin.
- E4-14 Canonical equal to own URL: rule 2 does not apply.
- E4-15 Canonical cycles (A->B->A) terminate (via the three-follow limit).
- E4-16 Pages with same origin are one source regardless of URL, provider or kind.
- E4-17 Candidates gain `origin`.

## Field keys
- E4-18 Each field gains `origins`, `corroborated`, `corroborated_since` (all eight fields incl. executives, investors).
- E4-19 `origins` = distinct origins of candidates whose value is the selected value, sorted ascending; [] for unknown.
- E4-20 `corroborated` true iff origins has >=2 entries.
- E4-21 `corroborated_since` = time (§8 format) of earliest ready build after which the selected value has had >=2 standing origins; null while fewer.
- E4-22 Standing origins = origins of every candidate with that value gathered by any ready build since the value became selected (learned_at of latest history entry), even if a later build did not regather it.
- E4-23 A new selected value starts with no standing origins (resets when value changes).
- E4-24 Imported candidates count as gathered at imported researched_at; stage-3 export builds' candidates count as gathered at that build's time.
- E4-25 Imported candidates with no recorded origin take normalised host of their URL as origin.
- E4-26 Failed builds do not contribute to standing origins / corroborated_since ("ready build").
- E4-27 (executives/investors) origins = distinct origins of candidates of all members, sorted; [] if unknown. A member's candidates: executives by title+name; investors by name.
- E4-28 corroborated (executives/investors) true iff every member's candidates have >=2 distinct origins; false otherwise and for unknown.
- E4-29 corroborated_since (exec/investors): earliest ready build after which every member has >=2 standing origins; null while some member has fewer or field unknown.
- E4-30 Member standing origins = origins of candidates gathered by the build after which it last became a member or any later ready build.

## Investors
- E4-31 Eighth field `investors`, after `executives` in `fields` of every response listing fields; feed entries of one build numbered with investors last.
- E4-32 Statement phrases: investor, investors, led by, backed by, participated. Company name and phrases removed first and act as word separators.
- E4-33 Investor name = run (capitalised words, single spaces, maximal) of >=2 words ending in Ventures/Capital/Partners/Fund/Investments/Holdings/Equity.
- E4-34 In an excerpt containing an amount (A.4), run starting directly after `led by`/`backed by` + one space is an investor name whatever its length/last word ("General Atlantic").
- E4-35 "Acme Robotics is led by Dana Ruiz." (no amount) names no investor.
- E4-36 Name normalises to text as the excerpt writes it. A.2 rules 1-4 apply; excerpt supports each investor name it contains (replaces rule 5).
- E4-37 Candidate value = one investor name; research claims are never investors candidates.
- E4-38 Member: some candidate with that name has kind own or filing, OR candidates with that name have >=2 distinct origins. (Lookalike "own" is aggregator -> not enough.)
- E4-39 value = array of member names sorted by code point; null if none. status known iff a member exists.
- E4-40 candidate `selected` true on every member-name candidate, false others.
- E4-41 candidates listed in stage-2 selection ranking order.
- E4-42 citations: per member in value order, url/excerpt/provider of every candidate with that name, in rank order.
- E4-43 member true_from = earliest non-null true_from among its candidates, null if all null; field true_from = latest of members', null when value null or any member null.
- E4-44 GET /dossiers/{domain}/values decides membership from candidates at true_at, with value/true_from/citations by these rules.
- E4-45 History/feed entry for investors typed by name: name in new value not in earlier counts as correction if both true_froms non-null and new <= earlier value's true_from; entry `correction` when every name in exactly one of the two values (symmetric difference) counts as correction, else `change`. (Removed names: spec says "every name in exactly one of the two values counts as a correction" — only new-value names are defined as counting.)
- E4-46 Screens: investors takes no data-testid of stage-2; /contested "no field is contested" means none of the six §4 fields is contested.

## Batches
- E4-47 POST /batches 202 body: batch_id (b_N), state, budget_units, spent_units, dossiers[{domain,state}].
- E4-48 Validation 422 validation_failed: domains missing/empty/>50; invalid entry after normalisation; duplicate after normalisation; budget_units missing/non-integer (string, true, 1.5)/<1/>100000. Wrong JSON type of budget_units is 422 not 400. (50 ok, 51 fail; 1 and 100000 ok.)
- E4-49 dossiers lists normalised domains in order given with each dossier's state.
- E4-50 Domain with no dossier gets one and the batch runs its first build; existing dossier is not researched and costs the batch nothing (state reported as its current state).
- E4-51 batch spent_units = total cost of provider calls of the batch's builds; never exceeds budget_units; each build <=80; cost also counts in dossier spent_units.
- E4-52 When a further call would exceed budget, batch makes no more calls; remaining builds complete with pages/claims obtained; fields known iff those support a value.
- E4-53 GET /batches/{id}: same shape; state running while any build runs, then done; unknown id 404 not_found.
- E4-54 Batch belongs to its creating user; another user's batch 404 not_found.
- E4-55 Idempotent replay of POST /batches returns the same response and starts nothing new; same key different body -> §7 conflict.
- E4-56 Auth/unauth behaviour per earlier stages applies to /batches.

## Provider failure
- E4-57 Provider error = any 5xx or 429; build continues and may retry same request via that provider or another.
- E4-58 All calls to one or more providers fail while nimble answers -> ready with every field known that reachable evidence supports.
- E4-59 All research runs fail while search/extract answered -> ready with all fields known that search+extract evidence supports.
- E4-60 All calls to every provider fail -> build `failed` (§8) within §8 time bound.
- E4-61 A call refused with an error status costs nothing (§9) (dossier and batch spent_units exclude it).
- E4-62 Failed build leaves fields as they were (§8).

## Restarts
- E4-63 Stage-3 restart requirements hold for batches (state persisted incl. batches, idempotency records).
- E4-64 With builds running at stop, everything else still answered as before the stop.
- E4-65 Each running build ends ready or failed within 10s of /health first 200 after restart (provider calls answer within 1s); never stays building; if failed leaves fields as were.
- E4-66 Build is one build across restart: total spend <=80; batch builds total <= budget_units.
- E4-67 Every billed unit before and after the stop counted in dossier spent_units and batch spent_units; in-flight unbilled may count.
- E4-68 After restart, refresh starts a new build of each such dossier as for any other.
- E4-69 Batch state after restart: becomes done once its builds end.

## Upgrades
- E4-70 Stage-4 accepts export from stage-1, -2, -3 services; preserves dossiers, candidates, history, change feed, completed idempotent responses (stage-1 §10).
- E4-71 Stage-3 export keeps builds: ?as_of= and /values answer from them as stage 3 did, with new keys.
- E4-72 Imported citations remain served.
- E4-73 After import from stage<=3, investors is unknown (imported state and every kept build), no history entry; first ready build with a value adds `change`, or `initial` if it is the dossier's first ready build.
- E4-74 Imported candidates with no origin: host fallback (E4-25).
- E4-75 Stage-4's own export/import round-trips batches? (not stated; only probe that batch ids don't collide after import).

## Carry-over touched by stage 4
- E4-76 Provider calls cost per §9; builds <=80 units; refresh/POST dossiers unchanged in shape except added keys and investors field.
- E4-77 Lookalike pages' kind change affects stage-2 selection (aggregator ranked below own).
- E4-78 Feed numbering: entries per build numbered with investors last.
- E4-79 Screens (stage-2/3) still render: executives/investors don't get stage-2 testids; phone and desktop widths.
