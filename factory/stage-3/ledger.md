# Stage 3 ledger

Spec: factory/stage-3/spec.md (stage-1 and stage-2 requirements still apply: factory/stage-1/spec.md, factory/stage-2/spec.md; their rows stay met).
Owners: A = builder-a, B = builder-b. Check: S = supplied harness, P = examiner probe.
Status: open until examiner accepts.

Layout (stage-3/, copy of stage-2/):
- A: `ui.py`/`ui_evidence.py`/`ui_pages.py` (executives display, screens), `candidates.py` (true_from, candidate identity key, executives per-title assembly), `build.py` (Effective line, executives candidates, `pages` in build result), `support.py` (cfo/coo/cto), `timeline.py` (NEW, pure functions: entry typing, executives typing, page versions, values_at, import page derivation), `measure.py`.
- B: `store.py` (persistence, builds log, history, feed, as_of, import/export), `server.py` (routes, validation), `Dockerfile`, `RUN.md`.

Interfaces (A implements, B calls):
- `build.run_build(domain, now_iso, should_abort)`: `fields` has 7 fields in assembled form; every candidate carries `true_from` (YYYY-MM-DD or null) and, for executives, `title`; no `learned_at` yet. The result also has `pages`: list of `{"url": str, "true_from": str|None}` for EVERY URL whose page text the build read (including pages with no candidates).
- `candidates.cand_key(field, cand) -> tuple`: identity for learned_at = (field, title-or-None, value, url, provider). B keeps a per-dossier `seen: {key: learned_at}`, stamps `learned_at` on candidates.
- `candidates.assemble_field(cands, field)` returns `{value,status,true_from,citations,candidates}` (executives routed to per-title assembly). Selected value's `learned_at` is set by B (kept while the value is unchanged, build time when it changed).
- `timeline.classify(field, prev, new) -> "change"|"correction"|None` (prev/new are field dicts with value,true_from; None means no difference; executives uses title typing).
- `timeline.values_at(builds, true_at, as_of_iso) -> {field: {value,true_from,citations}}`; `builds` = list in build order of `{"time": iso, "outcome": "ready"|"failed", "pages": [{"url","true_from","candidates": {field: [cand,...]}}]}`.
- `timeline.import_pages(candidates_by_field) -> pages`: page versions for imported candidates (true_from = UTC date part of candidate published_at, else null).

| ID | Statement | Owner | Check | Work | Status |
|---|---|---|---|---|---|
| R-01 | true_from = date from `Effective: <YYYY-MM-DD>` header line (Two times) | A | P | W-1 | met |
| R-02 | Page with no valid Effective line takes the UTC date part of its published_at (invalid calendar date or malformed = not valid; offset timestamps converted to UTC) | A | P | W-1 | met |
| R-03 | With neither Effective nor published_at, true_from is null | A | P | W-1 | met |
| R-04 | Candidates carry true_from and learned_at; retrieved_at stays the build time of the current candidate set | A,B | P | W-1,W-6a | met |
| R-05 | Candidate learned_at = time of the first build that gathered a candidate with same field, value, URL, provider (stable across later builds, even after the candidate leaves and returns) | B | P | W-6a | met |
| R-06 | Selected value true_from is that of its selected candidate | A | P | W-2 | met |
| R-07 | Selected value learned_at = time of the build that made it the selected value (kept while unchanged; new time when it changed, incl. A->B->A) | B | P | W-6a | met |
| R-08 | Each field of GET /dossiers/{domain} carries true_from and learned_at; both null when field is unknown | B | S,P | W-6a | met |
| R-09 | In an as_of response, true_from/learned_at describe the selected value at that snapshot using no later history | B | P | W-8 | met |
| R-10 | Selection rule of stage-2 unchanged | A | S,P | W-2 | met |
| R-11 | Seventh field `executives` in `fields` of every response that lists fields (dossier, as_of, history, values), after the six fields of §4 | B | P | W-7 | met |
| R-12 | Research run still asks for the six fields only; a research claim is never an executives candidate | A | P | W-3a | met |
| R-13 | executives value = array of `{title,name}` for each of cfo,coo,cto with a selected person, in that order; null and status unknown when none | A | P | W-3a | met |
| R-14 | Titles cfo/coo/cto are Appendix-A fields with phrases (chief financial/operating/technology officer, CFO/COO/CTO) and ceo format and normalisation (A.4, A.5) | A | P | W-3a | met |
| R-15 | Executives candidate carries `title` beside `value`; value is the person's name | A | P | W-3a | met |
| R-16 | Selection rule runs separately per title: `selected` true on highest-ranked candidate of each title with candidates, false on others | A | P | W-3a | met |
| R-17 | executives `candidates` listed by title (cfo,coo,cto) then rank order | A | P | W-3b | met |
| R-18 | executives `citations`: per member in order, url/excerpt/provider of every candidate with member's title and name, rank order | A | P | W-3b | met |
| R-19 | executives status: unknown when value null; contested when candidates of some title carry two or more different names; known otherwise | A | P | W-3b | met |
| R-20 | Executives candidate learned_at keyed by title, name, URL, provider | B | P | W-6a | met |
| R-21 | Member true_from = its title's selected candidate; field true_from = latest member true_from, null if any member's null | A | P | W-3b | met |
| R-22 | /values picks each title's person from candidates at true_at and gives value, true_from, citations by these rules | A | P | W-5 | met |
| R-23 | Executives history/feed typing by title: a title differs when exactly one value has the member, or both have it and names differ; correction when every differing title is a correction (both members present, both true_from not null, new on or before earlier), else change | A | P | W-4 | met |
| R-24 | Screens: executives takes none of the six-field data-testids; any screen showing it uses other markup; /contested "no field is contested" considers only the six fields | A | P | W-12 | met |
| R-25 | Ready build: each field whose selected value differs from before gets one history entry and one feed entry (change or correction) | B | P | W-6b | met |
| R-26 | correction iff both earlier and new value non-null and new true_from on or before earlier true_from (both non-null); otherwise change (appearing, disappearing, either true_from null) | A | P | W-4 | met |
| R-27 | First selected value set by the dossier's first ready build: history `initial`, no feed entry | B | P | W-6b | met |
| R-28 | Field unknown after first ready build gets first entry when it first gets a value; that entry is a `change` | B | P | W-6b | met |
| R-29 | Build with same selected value adds nothing (even when candidates/citations/true_from differ); failed build adds nothing | B | P | W-6b | met |
| R-30 | Concurrent refreshes of one dossier run one build and add each entry once | B | P | W-10 | met |
| R-31 | GET ?as_of: latest ready build with time <= as_of: its fields, candidates, researched_at; state ready; decided by learned_at never true_from | B | P | W-8 | met |
| R-32 | as_of spent_units = total of builds (any outcome) with time <= as_of | B | P | W-8 | met |
| R-33 | Equal build times: last in build order wins, also for equivalent RFC 3339 timestamps with different offsets; clock need not advance between builds | B | P | W-8 | met |
| R-34 | as_of not RFC 3339 with explicit offset: 422 validation_failed | B | P | W-8 | met |
| R-35 | No ready build <= as_of: 404 not_found; no dossier: 404 not_found; without as_of unchanged | B | P | W-8 | met |
| R-36 | GET /values?true_at=: shape {domain,true_at,as_of,fields:{f:{value,true_from,citations}}}, 7 fields, as_of defaults to current time (§8) | B | P | W-8 | met |
| R-37 | Page version = candidates and true_from one ready build gathered from one URL; versions known at as_of = ready builds with time <= as_of in build order; each holds from its true_from | A | P | W-5 | met |
| R-38 | Later version of same URL replaces every earlier version of the URL with true_from on or after its own | A | P | W-5 | met |
| R-39 | Latest earlier version not replaced stops holding on the later version's true_from | A | P | W-5 | met |
| R-40 | Version with null true_from holds from no date; later null-true_from version replaces all earlier versions of its URL | A | P | W-5 | met |
| R-41 | A gathered version with no candidates still replaces or ends earlier versions | A | P | W-5 | met |
| R-42 | Candidates at true_at = those of every version holding that date; each field's value by stage-2 selection rule; true_from of chosen candidate | A | P | W-5 | met |
| R-43 | Field with no candidate at true_at: value null, true_from null, citations []; citations = candidates at true_at with chosen value | A | P | W-5 | met |
| R-44 | /values: true_at missing or not a valid YYYY-MM-DD, or as_of not RFC 3339 with offset: 422; no dossier or no ready build <= as_of: 404 | B | P | W-8 | met |
| R-45 | GET /history: {domain, fields} with all seven fields, each list oldest first; [] when none | B | P | W-7 | met |
| R-46 | History entry value/true_from/learned_at/citations = those of the selected value recorded; null value gives true_from null and citations [] | B | P | W-7 | met |
| R-47 | History: no dossier 404 not_found; bearer required (401) | B | P | W-7 | met |
| R-48 | GET /changes shape {changes:[{seq,domain,field,type,from,to,true_from,learned_at}],has_more}; feed holds every change/correction entry of every dossier, never initial | B | P | W-7 | met |
| R-49 | seq positive integer, unique, larger for later entries; entries of one build numbered in field order of §4 then executives | B | P | W-7 | met |
| R-50 | from/to = earlier/new selected value (null allowed); true_from = new value's; learned_at = time of the build that added the entry | B | P | W-7 | met |
| R-51 | since default 0, integer >=0, lists seq > since ascending; limit default 50, 1..200; has_more true when entries beyond the last returned; invalid since/limit 422 | B | P | W-7 | met |
| R-52 | Operation 4: every change to a selected value appears exactly once in the feed at its assigned time | B | P | W-6b | met |
| R-53 | Upgrade: stage-1/stage-2 export import accepted; every imported field with a value gets one `initial` history entry, learned_at = researched_at, true_from null unless the export records the date | B | P | W-9a | met |
| R-54 | Feed empty after import; first build after import compares with imported selected values | B | P | W-9a | met |
| R-55 | Tokens, dossiers, completed idempotent responses survive import (§10); stage-3 export history, feed and builds survive stage-3 import unchanged; as_of and /values answer as in exporting service | B | P | W-9a | met |
| R-56 | Stage-1 import = one ready build at researched_at; each imported candidate URL one version; imported candidate learned_at = retrieved_at; as_of at/after it and before next build returns imported fields | B | P | W-9a | met |
| R-57 | Earlier as_of than that: 404; imported dossier with null researched_at: every as_of 404 until a build completes | B | P | W-9a | met |
| R-58 | Stage-2 import keeps builds (time, outcome, spending); ready ones keep candidates and one page version per URL with true_from from Effective/Published (rulings: our exports hold no builds, so one ready build at researched_at); state the stage-2 service itself imported = one ready build at researched_at | B | P | W-9b | met |
| R-59 | Stage-2 import: as_of response takes each field's learned_at and true_from from history; history one initial entry per field with value | B | P | W-9b | met |
| R-60 | Import: executives unknown in imported state and every kept build, no history entry; first ready build with a value adds change, or initial if it is the dossier's first ready build | B | P | W-9b | met |
| R-61 | Concurrency: concurrent refreshes and reads give results equal to some serial order; no change twice or missing in feed | B | P | W-10 | met |
| R-62 | Restarts: state on container filesystem survives abrupt stop; with no build running, every account signs in, every bearer token valid | B | P | W-11 | met |
| R-63 | After restart dossiers answer GET, as_of, /values, /history as before; GET /dossiers lists same dossiers | B | P | W-11 | met |
| R-64 | After restart feed has same entries and seq; new entry has seq larger than all before | B | P | W-11 | met |
| R-65 | After restart replay of completed idempotent request answers per §7; clock reads the time it read before the stop until reset/POST clock | B | P | W-11 | met |
| R-66 | Abrupt stop safety: state written atomically (temp file + fsync + rename) after every mutation, so a kill never leaves corrupt or half-written state; startup tolerates a missing file | B | P | W-11 | met |
| R-67 | Stage-3 export includes builds, history, feed, seen map so a stage-3 import restores them; stage-1 and stage-2 exports still accepted | B | P | W-9b | met |
| R-68 | Dossier screen/evidence show executives with human labels (title names, no raw keys), fine at phone and desktop width | A | P | W-12 | met |
| R-69 | RUN.md/Dockerfile: state directory on container filesystem, documented; image builds and starts | B | S | W-11 | met |
| R-70 | Regression: stage-1 and stage-2 supplied checks still pass in stage-3 | A,B | S | all | met |
| R-71 | as_of boundary is inclusive: as_of equal to a build's time returns that build (examiner E-39) | B | P | W-8 | met |
| R-72 | A version holds on its own true_from day itself (true_at == true_from is inside) (examiner E-46) | A | P | W-5 | met |
| R-73 | Same selected value = JSON-equal (stage-2), including executives arrays, when deciding no-change vs entry (examiner E-33) | B | P | W-6b | met |
