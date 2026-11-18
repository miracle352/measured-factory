# Stage 3 exam list (from the specification only)

IDs E-nn. Sections: TT = Two times per value, EX = Executives, CC = Changes and corrections,
AO = ?as_of=, VA = /values, HI = /history, CH = /changes, UP = Upgrades, CO = Concurrency, RS = Restarts, OP = operation 4.

## Two times (TT)
- E-01 Candidates carry `true_from` and `learned_at` (TT).
- E-02 `true_from` = page's `Effective: YYYY-MM-DD` header (TT).
- E-03 No valid `Effective` line -> UTC date part of `published_at` (TT); invalid Effective (bad date, e.g. 2026-02-30 / wrong format) falls back (TT).
- E-04 Neither -> `true_from` null (TT).
- E-05 Candidate `learned_at` = time of first build that gathered same field+value+URL+provider; stays unchanged across later builds that regather it (TT).
- E-06 A candidate new to a later build gets that build's time (TT).
- E-07 `retrieved_at` stays the time of the build that gathered the candidate in the current candidate set (TT).
- E-08 Selected value's `true_from` = its selected candidate's; selected value's `learned_at` = time of the build that made it the selected value (not changed by a build keeping the same value) (TT).
- E-09 Each field of GET /dossiers/{domain} carries `true_from` and `learned_at`; both null when unknown (TT).
- E-10 In an as_of response these describe the selected value at that snapshot, no later history (TT).
- E-11 Selection rule unchanged (TT).

## Executives (EX)
- E-12 Seventh field `executives` after the six, in every response listing fields (dossier, as_of, history, values) (EX).
- E-13 Research run still asks only six fields (EX).
- E-14 Value = array of {title,name} in order cfo, coo, cto, only for titles with a selected person; null+unknown when none (EX).
- E-15 Title phrases: cfo "chief financial officer"/"CFO"; coo "chief operating officer"/"COO"; cto "chief technology officer"/"CTO"; format/normalisation of ceo (EX, A.4, A.5).
- E-16 Candidate of executives carries `title` beside `value` (name); never a research claim candidate (EX).
- E-17 Selection runs separately per title; `selected` true on highest-ranked of each title with candidates only (EX).
- E-18 `candidates` ordered by title (cfo,coo,cto) then rank (EX).
- E-19 `citations` per member in order: every candidate with that title and name, rank order (EX).
- E-20 status unknown / contested (some title has >=2 names) / known (EX).
- E-21 Candidate learned_at keyed by title+name+URL+provider (EX).
- E-22 Member `true_from` = its title's selected candidate; field true_from = latest of members', null if any member null (EX).
- E-23 /values chooses each title's person from candidates at true_at; value, true_from, citations from them (EX).
- E-24 History/feed entry typing for executives by title: differ rules; correction only if every differing title is a correction (both members, both true_from non-null, new <= old); else change (EX).
- E-25 No `data-testid` for executives from stage-2 screens; /contested "no field contested" ignores executives (EX). (a contested executives field must not appear on /contested.)

## Changes (CC)
- E-26 Each field whose selected value differs from before the build gets one history entry and one feed entry (CC).
- E-27 `correction` iff both values non-null and new true_from <= earlier true_from (both non-null); otherwise `change` (value appearing, disappearing, either true_from null) (CC).
- E-28 First ready build: `initial` history entry per field with value, no feed entry (CC).
- E-29 Field unknown after first build gets first entry (`change`, feed too) when it first gets a value (CC).
- E-30 Same selected value -> nothing, even when candidates/citations/true_from differ (CC).
- E-31 Failed build adds nothing (CC).
- E-32 Concurrent refreshes of one dossier add each entry once (CC, CO, OP).
- E-33 Value equality: same selected value = equal as JSON (stage-2).

## as_of (AO)
- E-34 Returns fields/candidates/researched_at of latest ready build with time <= as_of, by learned_at not true_from (AO).
- E-35 state ready; spent_units = total of builds (all outcomes) with time <= as_of (AO).
- E-36 Equal-time ready builds -> last in build order, also with equivalent timestamps in different offsets; clock need not advance (AO).
- E-37 as_of without explicit offset / not RFC3339 -> 422 validation_failed (AO); no ready build <= as_of -> 404; no dossier -> 404 (AO).
- E-38 Without as_of unchanged (AO).
- E-39 as_of inclusive boundary (== build time returns that build) (AO).
- E-40 422 before 404 (ruling); bearer required (ruling).

## values (VA)
- E-41 Response shape {domain,true_at,as_of,fields:{<7>:{value,true_from,citations}}}; as_of defaults to now (VA).
- E-42 Page version = candidates + true_from from one URL in one ready build; versions known at as_of are those of ready builds <= as_of (VA).
- E-43 Each version holds from its true_from; later version replaces every earlier version of that URL with true_from >= its own; latest earlier version not replaced stops holding at later version's true_from (VA).
- E-44 Null true_from version holds from no date; later version with null true_from replaces every earlier version of its URL (VA).
- E-45 A gathered version with no candidates still replaces/ends earlier versions (VA).
- E-46 Candidates at true_at = those of every version holding on that date (inclusive of true_from day); value by selection rule; true_from of chosen (VA).
- E-47 No candidate -> value null, true_from null, citations [] (VA); citations = candidates at true_at with chosen value (VA).
- E-48 422 for missing / malformed true_at (also e.g. 2026-13-40) or bad as_of; 404 no dossier or no ready build <= as_of (VA).
- E-49 as_of parameter limits version knowledge (later builds ignored) (VA).

## history (HI)
- E-50 Shape; all seven fields; list per field, oldest first (HI).
- E-51 Entry value/true_from/learned_at/citations are those of the selected value; null value entry: true_from null, citations [] (HI).
- E-52 No dossier -> 404 (HI).

## changes (CH)
- E-53 Feed holds every change/correction of every dossier; shape {changes:[{seq,domain,field,type,from,to,true_from,learned_at}],has_more} (CH).
- E-54 seq positive int, unique, increasing; entries of one build in field order of §4 then executives (CH).
- E-55 from/to earlier/new selected values (null allowed); true_from = new value's; learned_at = build time (CH).
- E-56 since default 0, int >= 0 (else 422), strictly greater; limit default 50, range 1..200 (else 422); has_more exactly when entries exist beyond (CH).
- E-57 Feed never lists `initial`.

## Upgrades (UP)
- E-58 Stage-3 accepts stage-1 and stage-2 export (UP).
- E-59 Each imported field with value gets one `initial` entry, learned_at = researched_at, true_from null unless recorded (UP).
- E-60 Feed empty after import; first build afterwards compares to imported values (UP).
- E-61 Tokens, dossiers, completed idempotent responses survive (UP, §10).
- E-62 Stage-3 export -> stage-3 import keeps history, feed (same seq), builds, as_of and /values answers (UP).
- E-63 Stage-1 import = one ready build at researched_at; imported candidates learned_at = retrieved_at; as_of at/after that and before next build returns imported fields; earlier -> 404; researched_at null -> every as_of 404 until a build completes (UP).
- E-64 Stage-2 import keeps builds with time, outcome, spending; ready ones keep candidates and per-URL page versions with true_from from Effective/Published as gathered; as_of, /values, learned_at answer as if made here (UP).
- E-65 After import executives unknown in imported state and in every kept build, no history entry; first ready build with a value adds `change` (or `initial` if the dossier's first ready build) (UP).
- E-66 as_of response on imported state takes learned_at/true_from from history (UP).

## Concurrency (CO)
- E-67 Concurrent refreshes/reads equal some serial order; no duplicate or missing feed entries (CO).

## Restarts (RS)
- E-68 After an abrupt restart with no build running: accounts sign in, tokens valid (RS).
- E-69 Dossiers answer with/without as_of, values, history; list same (RS).
- E-70 Feed same entries, same seq; later entry larger seq than all before (RS).
- E-71 Replay of completed idempotent request answers per §7 (RS).
- E-72 Clock reads same time after restart until reset/POST /_test/clock (RS).

## Operation
- E-73 Op 4: every selected-value change appears exactly once in feed at its assigned time (OP).
- E-74 Earlier stage requirements continue (regression: stage-1/2 suites).
