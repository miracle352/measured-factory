# Stage 1 ledger

Owners: A = builder-a, B = builder-b. Check: S = supplied harness, P = examiner probe.
Status: open until examiner accepts.

Layout (stage-1/): `server.py` (HTTP, routing, errors), `store.py` (state, clock, auth, idempotency, export/import) — B.
`support.py` (Appendix A engine), `build.py` (providers, gathering, field decision, budget), `measure.py` — A.
Dockerfile, RUN.md, requirements.txt — B.

Interfaces:
- `support.extract_values(field, excerpt, domain) -> list[normalised values]` (empty when not a single sentence / not naming company / no phrase / negating phrase present); `support.supports(field, value, excerpt, domain) -> bool`; `support.sentences(prose)`; `support.split_header(text) -> (header_lines, prose)`.
- `build.run_build(domain, now_iso, should_abort) -> BuildResult(outcome 'ready'|'failed', fields{name:{value,status,citations}}, spent_units)`; blocking, runs in a worker thread; never raises; B owns state, generation counters and reset-safety.

| ID | Statement | Owner | Check | Work | Status |
|---|---|---|---|---|---|
| R-01 | §1.1 every asserted value cites >=1 excerpt served by a provider that supports it; none invented/reworded/misattached | A | S,P | W-5 | open |
| R-02 | §1.2 no build spends more than 80 units | A | S,P | W-4 | open |
| R-03 | §2 HTTP service + Dockerfile + RUN.md; build/start w/o manual setup; works with `-e PORT` in single container | B | S,P | W-11 | open |
| R-04 | §2 all provider requests go through `web_router` (in-process or Python helper in container); requirements list `webrouter>=0.12.0`; no direct provider API calls | A | P | W-4 | open |
| R-05 | §2 Nimble alone suffices; Tavily optional, absence/failure of Tavily does not block research | A | P | W-4 | open |
| R-06 | §2 Tavily base URL passed via `provider_config={"tavily":{"api_base_url":TAVILY_BASE_URL}}`; Nimble via env; empty/unset base URL never passed empty | A | P | W-4 | open |
| R-07 | §2 limits: 2 vCPU/3GiB, healthy within 60s, 50 concurrent in flight, 5s request timeout (10s reset); runtime assets in image | B | P | W-11 | open |
| R-08 | §3.1 listen on 0.0.0.0, PORT env, default 8080 | B | S | W-6 | open |
| R-09 | §3.2 GET /health -> 200 {"status":"ok"}; no provider call | B | S | W-6 | open |
| R-10 | §3.3 POST /_test/reset replaces all state with fixture (users, no dossiers, no idempotent responses), 204, unauthenticated, repeatable | B | S | W-6 | open |
| R-11 | §3.3 build running at reset must not alter post-reset state | B | P | W-9 | open |
| R-12 | §3.4 clock moved only by reset/clock; reset sets to fixture `now`; before first reset follows system time; stands still between calls | B | S | W-6 | open |
| R-13 | §3.4 POST /_test/clock 204, unauthenticated; `now` RFC3339 with offset; earlier than current -> 422 validation_failed, no change; every timestamp from this clock | B | S,P | W-6 | open |
| R-14 | §3.5 JSON utf-8 bodies; timestamps RFC3339 with explicit offset; unknown body fields and query params ignored; ids <=64 chars opaque | B | P | W-6 | open |
| R-15 | §4 domain normalisation: trim, lowercase, one trailing `.`, one leading `www.`; then valid hostname (>=2 labels, labels 1-63 of a-z0-9-, no leading/trailing -, <=253); else 422 (URL w/ scheme/path invalid); responses carry normalised domain | B | S,P | W-9 | open |
| R-16 | §4 six fields exactly; types (strings, ints; headcount_range one of 8 ranges; funding int dollars); string value as excerpt writes it, no surrounding whitespace; headcount number or range fitting inside a range -> containing range | A | P | W-5 | open |
| R-17 | §4 field shape {value,status,citations[{url,excerpt,provider}]}; known iff value non-null with >=1 citation; unknown => null + []; url = page the excerpt was served for; provider = serving provider | A | S,P | W-5 | open |
| R-18 | §4 evidence = every page any search returns with full text + every claim of a nimble research run asking for all six fields; a build runs research asking for all six fields (output_schema property names = field names, query names company by domain) | A | P | W-4 | open |
| R-19 | §4 of searches answered without error, every build makes exactly one whose query is exactly the normalised domain (any provider); other such searches use other queries; errored searches don't count (retry after error must still end with exactly one) | A | P | W-4 | open |
| R-20 | §4 excerpt: copied char-for-char from served text (whitespace runs may collapse to one space), 1-500 chars, from prose not header | A | P | W-5 | open |
| R-21 | §4 research claim asserted only when its citation supports it; field unknown when no evidence supports a value even if research claims one | A | P | W-5 | open |
| R-22 | §4 multiple supported values: field holds one, cites only excerpts supporting that value | A | P | W-5 | open |
| R-23 | §4 header lines `Name: value` (capitalised word(s) joined by `-`), header ends at first empty line, rest is prose; text without header-first-line is all prose; Facts header informative only, never cited | A | P | W-1 | open |
| R-24 | §4 fixture: `now` required, users seeded login immediately with given password; user_id = fixture id; duplicate emails -> 422 validation_failed, state unchanged; missing now -> 422 | B | S,P | W-6 | open |
| R-25 | §5 error body {"error":{"code","message"}} on every 4xx/5xx; codes/statuses: 400 malformed_request (unparseable body or wrong JSON type), 400 missing_idempotency_key, 401 unauthenticated, 404 not_found, 409 idempotency_key_reuse, 422 validation_failed | B | S,P | W-6 | open |
| R-26 | §5 integer query params plain decimal digits only (`1e9`,`4.0`,`+4` -> 422); invalid format/out-of-range correct type -> 422; Idempotency-Key 1-255 else 422; limit 1-200; offset >=0 | B | P | W-9 | open |
| R-27 | §5 no 5xx ever, incl. concurrent load and provider errors | A,B | P | W-4,W-6 | open |
| R-28 | §6 POST /auth/signup 201 {user_id,display_name,token}; 409 email_taken; password <8 -> 422; email not local@domain -> 422; display_name empty or >100 -> 422 | B | S,P | W-7 | open |
| R-29 | §6 POST /auth/login 200 same shape; wrong password / unknown email -> 401 unauthenticated; wrong JSON types -> 400 | B | S,P | W-7 | open |
| R-30 | §6 every other endpoint needs bearer token (except /health, /_test/*, the two auth); missing/malformed/unknown -> 401, even when Idempotency-Key also missing; tokens never expire, multiple concurrent tokens per account | B | S,P | W-7 | open |
| R-31 | §6 passwords stored hashed (bcrypt/scrypt/argon2 or equiv.), no plaintext | B | P | W-7 | open |
| R-32 | §4 every authenticated user sees the same dossiers | B | P | W-9 | open |
| R-33 | §7 Idempotency-Key header on POST /dossiers and POST /dossiers/{domain}/refresh; absent/empty -> 400; scoped per user; same key different users independent | B | S,P | W-8 | open |
| R-34 | §7 replay = same user+method+path+body: 200 with body identical (JSON value) to original, no build, no provider call, even after dossier changed; same key different path = different request; differently-cased domain in path/body = different request | B | S,P | W-8 | open |
| R-35 | §7 same key + different body -> 409 idempotency_key_reuse; body compare as parsed JSON, unknown fields ignored; refresh body ignored entirely | B | S,P | W-8 | open |
| R-36 | §7 key reused after original failed with 4xx = first use | B | P | W-8 | open |
| R-37 | §7 concurrent identical requests with unused key: exactly one normal response, others 200 same body; takes effect once | B | P | W-8 | open |
| R-38 | §7 after body parses as JSON object and caller authenticated, claimed key resolved before field validation (valid then invalid body same key -> 409) | B | P | W-8 | open |
| R-39 | §8 POST /dossiers: 202 {dossier_id,domain,state:building} creating dossier + first build; existing dossier -> 200 with id, domain, current state, no build; concurrent same domain (any keys) -> one dossier one build; domain missing/invalid -> 422 | B | S,P | W-9 | open |
| R-40 | §8 GET /dossiers/{domain}: dossier_id, domain, state, researched_at, spent_units, fields(all six); path domain normalised; unknown -> 404 | B | S,P | W-9 | open |
| R-41 | §8 state = building while a build runs, else latest outcome ready/failed; before first ready build every field unknown; during later build fields are last ready build's; researched_at = time of last ready build (build time = clock when request received) or null | B | S,P | W-9 | open |
| R-42 | §8 spent_units = total cost of every provider call for this dossier across all builds since creation (including failed builds) | A,B | S,P | W-4,W-9 | open |
| R-43 | §8 POST /dossiers/{domain}/refresh: 202 {dossier_id,domain,state:building}; running build -> no second build, 202 same body; no dossier -> 404; refresh researches again (calls providers) and its spend counts | B | S,P | W-9 | open |
| R-44 | §8 at most one build running per dossier | B | P | W-9 | open |
| R-45 | §8 build ends `ready` when completed, `failed` when none of its provider calls succeeded; failed build leaves fields unchanged | A | P | W-5 | open |
| R-46 | §8 when ready, each field known exactly when evidence supports a value (gather enough evidence: searches, extracts as needed within budget) | A | S,P | W-5 | open |
| R-47 | §8 build with providers answering within 1s ends within 10s of the request | A | P | W-4 | open |
| R-48 | §8 against live providers a build does not give up on a call waiting <30s, does not stop gathering due to time in first 120s, ends ready/failed within 300s; timings never tuned to mocks | A | P | W-4 | open |
| R-49 | §8 reads, lists, every request other than POST /dossiers and refresh make no provider call | B | P | W-9 | open |
| R-50 | §8 GET /dossiers: items {dossier_id,domain,state,legal_name,researched_at,spent_units}, has_more; q case-insensitive contains on domain or legal_name, empty q = all; ordered by domain asc; limit default 50 (1-200), offset default 0; has_more true iff more items beyond | B | S,P | W-9 | open |
| R-51 | §9 cost table applied: nimble search lite/fast/deep 1/5/15, tavily 8/16/16, extract 1 / 2 per URL requested (even when no page returned), nimble research 25 at start (poll free); search max 10 results; refused-with-error calls cost 0; timed-out/connection-failed calls cost table amount; nimble extract never sets render; spend tracked per call with the mock log as ground truth | A | P | W-4 | open |
| R-52 | §9 build stops making calls before spending would exceed 80 and completes with what it has (pessimistic accounting for in-flight/timeout calls); research request: query names company by domain, output_schema property names = field names | A | P | W-4 | open |
| R-53 | §9 handle provider errors (500, 429, delays up to 10s) with bounded retries without exceeding budget or five-second request timeouts of API calls (builds are background) | A | P | W-4 | open |
| R-54 | §10 GET /_test/export -> 200 {track:"dossier",format_version:1,state:{}}; atomic read-only snapshot; unauthenticated; 10s | B | P | W-10 | open |
| R-55 | §10 POST /_test/import replaces entire state atomically, 204; accepts unchanged export; repeatable, no duplicates; no dependency on source process; invalid JSON 400; missing fields/wrong track/version/invalid state 422 w/o change | B | P | W-10 | open |
| R-56 | §10 preserves accounts + hashed login, tokens, dossiers (ids, states, fields, citations, researched_at, spent_units), completed idempotent bodies and responses; failed keys reusable; ids/timestamps not regenerated; no provider call on import; import removes prior data; reset clears imported state; clock untouched by export/import | B | P | W-10 | open |
| R-57 | §10 export during running build holds the dossier as before that build; after import dossier is last completed build's state, or failed with all fields unknown if none completed | B | P | W-10 | open |
| R-58 | §11 concurrent requests equal some serial order; requirements hold at every read (no partial dossier visible; fields swap atomically) | B | P | W-9 | open |
| R-59 | A.1 sentence splitting: lines at line breaks; sentence ends after `.`,`!`,`?` plus directly-following `"`,`”`,`’`,`)` when whitespace follows; `.` ending a legal-form suffix as whole word doesn't end sentence; trimmed, empties dropped; excerpt single-sentence iff exactly one sentence after whitespace collapse | A | P | W-1 | open |
| R-60 | A.2 supports rule: (1) single sentence (2) names company (domain or first label with `-`→space) (3) statement phrase for F (4) no negating phrase (5) >=1 value in F's format and every such value normalises to V; case-insensitive whole-word matching (neighbours not letters/digits); phrase spaces match one space | A | P | W-1 | open |
| R-61 | A.3 statement phrases per field and negating phrase list exactly as specified | A | P | W-1 | open |
| R-62 | A.4 definitions: capitalised word (any alphabet, e.g. Zürich), uppercase word (>=2), number format (digits, comma groups of three, decimal part; digits adjacent to letters or otherwise joined by `,`/`.` aren't numbers) | A | P | W-2 | open |
| R-63 | A.4 legal_name format: company name or domain, then 0+ capitalised/uppercase words each after one space, then optional `,`+space+legal-form suffix (exact list, no alnum after); shortest of texts starting at same place; A.5 value as written | A | P | W-2 | open |
| R-64 | A.4 hq_city format: longest run of capitalised words joined by single spaces or `-` directly after the statement phrase + one space, not part of a longer run; value as written | A | P | W-2 | open |
| R-65 | A.4 ceo format: run of 2-3 capitalised words with single spaces, not part of a longer run; company-name occurrences and ceo statement phrases removed first and act as separators | A | P | W-2 | open |
| R-66 | A.4/A.5 founded_year: four-digit number 1800-2099 not part of an amount -> integer | A | P | W-3 | open |
| R-67 | A.4/A.5 headcount_range: number, no decimal part, >=1, not part of an amount; ranges like `51-200 employees` hold two numbers; value = containing range of the 8 ranges (10001+ top) | A | P | W-3 | open |
| R-68 | A.4/A.5 funding_total: amount forms (`$`/`US$`/`USD` + optional space + number + scale k/m/mn/bn or ` thousand|million|billion`; or number [scale word] + ` dollars`/` US dollars`), case-insensitive, no alnum before/after; other currencies not amounts; value = number × scale in whole dollars, non-whole not a value | A | P | W-3 | open |
| R-69 | A.2 negating phrase/other-value behaviour: excerpt with two different values for F supports none; two occurrences of the same value supports it | A | P | W-1,W-3 | open |
| R-70 | §4 gathered-page handling: citations taken from pages the service obtained (search results with text, extracts, research citations excerpts); excerpts from truncated search bodies are still served text and valid | A | P | W-5 | open |
| R-71 | §1/§9 cost per correct result measured against local mock with >=2 strategies; numbers in factory/measurements.md | A | P | W-12 | open |

## Work items

| Item | Owner | Rows | Files |
|---|---|---|---|
| W-1 | A | R-23,R-59,R-60,R-61,R-69 | support.py (header, sentences, rule, phrases) |
| W-2 | A | R-62,R-63,R-64,R-65 | support.py (number/word/legal_name/hq_city/ceo) |
| W-3 | A | R-66,R-67,R-68 | support.py (year/headcount/funding) |
| W-4 | A | R-02,R-04,R-05,R-06,R-18,R-19,R-47,R-48 (+R-42,R-51,R-52,R-53,R-27 partial) | build.py gathering/budget — split into 2 commits if >8 rows |
| W-5 | A | R-01,R-16,R-17,R-20,R-21,R-22,R-45,R-46,R-70 | build.py decision/citations |
| W-12 | A | R-71 | measure.py |
| W-6 | B | R-08,R-09,R-10,R-12,R-13,R-14,R-24,R-25 | server.py, store.py core |
| W-7 | B | R-28,R-29,R-30,R-31 | auth |
| W-8 | B | R-33..R-38 | idempotency |
| W-9 | B | R-11,R-15,R-26,R-32,R-39..R-41,R-43,R-44 | dossiers endpoints |
| W-9b | B | R-49,R-50,R-58 | list/reads/concurrency |
| W-10 | B | R-54..R-57 | export/import |
| W-11 | B | R-03,R-07 | Dockerfile, RUN.md, requirements.txt |

(A's W-4 is split into W-4a [R-04,R-05,R-06,R-18,R-19,R-47,R-48] and W-4b [R-02,R-42,R-51,R-52,R-53,R-27]. Examiner-added rows are appended below.)

## Examiner-added rows
| R-72 | §3.4 clock `now` lacking an explicit offset (or not RFC 3339) -> 422 validation_failed, no change (examiner E-25) | B | P | W-6 | open |
| R-73 | §10/§6 export contains no plaintext passwords; spent_units never decreases at any read (examiner E-115, E-120) | B | P | W-10 | open |
