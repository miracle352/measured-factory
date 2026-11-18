# Stage 1 exam list (from specification only)

IDs E-xx; section refs are to the stage-1 spec. P = probe covers it (probes/probe.py), M = needs mock admin.

## Global invariants (§1, §9)
- E-01 §1.1 every asserted value cites >=1 excerpt that a provider served to the service, and the excerpt supports the value (M log "served").
- E-02 §1.2 no build spends >80 units (M log cost sum per build; spent_units <= 80 per build).
- E-03 §1 only six fields; no contact/people data.

## Delivery (§2)
- E-10 Dockerfile + RUN.md present; RUN.md has build+start command without manual setup.
- E-11 Image runs with `-e PORT` + port mapping alone; no compose; no runtime network except providers.
- E-12 Providers reached only via `web_router` (webrouter>=0.12.0); nimble works alone; tavily optional, absence must not block research; tavily base URL via provider_config.
- E-13 Healthy within 60 s; 2 vCPU / 3 GiB; 50 concurrent in flight; 5 s per-request timeout (10 s reset/export/import).
- E-14 No runtime assets fetched from the internet.

## Runtime (§3)
- E-20 Listens 0.0.0.0, PORT default 8080.
- E-21 GET /health -> 200 {"status":"ok"}; makes no provider call.
- E-22 POST /_test/reset -> 204; replaces all state (users, dossiers, idempotency records); repeated resets OK; running build must not affect post-reset state; unauthenticated.
- E-23 reset with duplicate emails -> 422 validation_failed, state unchanged; `now` required (missing -> 422).
- E-24 Seeded users log in immediately; user_id = fixture id.
- E-25 POST /_test/clock -> 204, unauthenticated; moves the clock; earlier-than-current -> 422 validation_failed, no change; `now` needs explicit offset (else 422).
- E-26 Reset sets clock to fixture `now`; clock stands still (two requests same timestamp; researched_at = reset now).
- E-27 Every recorded timestamp from clock; responses RFC3339 with explicit offset.
- E-28 JSON content type utf-8; unknown body fields ignored; unknown query params ignored; IDs <=64 chars opaque.

## Model (§4)
- E-30 Domain normalisation: trim, lowercase, strip one trailing ".", strip one leading "www."; then valid hostname (>=2 labels, labels 1-63 [a-z0-9-], no leading/trailing "-", <=253 total); URL with scheme/path -> 422.
- E-31 Same company/dossier for `Acme-Robotics.TEST.`, `www.acme-robotics.test`, `acme-robotics.test`; responses carry normalised domain; path domains normalised too.
- E-32 Exactly six fields with types: legal_name str, hq_city str (no region/country), ceo str, founded_year int, headcount_range one of 8 ranges, funding_total int whole USD.
- E-33 String values as excerpt writes them, trimmed; headcount number or range within a bucket -> containing bucket.
- E-34 Field shape: value/status/citations{url,excerpt,provider}; known<->value non-null, >=1 citation; unknown -> null, [].
- E-35 provider is nimble|tavily and is the provider that served the excerpt; url is page it was served for.
- E-36 Citation: excerpt copied char-for-char from served text (whitespace runs may collapse to one space), 1-500 chars, from prose not header.
- E-37 Excerpt supports value per Appendix A (see E-90..).
- E-38 Research claim asserted only when its citation supports it; field unknown when no evidence supports, even if research claims one.
- E-39 Multiple supported values -> field holds one, cites only excerpts supporting that value.
- E-40 `Facts:` header informative only, citations from prose only; other headers ignorable.
- E-41 Evidence = pages from any search for any query naming company + research claims (nimble all six fields).
- E-42 Exactly one successful search per build whose query is exactly the normalised domain (M log); other successful searches use other queries; errored searches don't count.
- E-43 Fixture: now required; two users sharing email -> 422.

## Errors (§5)
- E-50 Error body {"error":{"code","message"}} on every 4xx/5xx.
- E-51 400 malformed_request: unparseable body / wrong JSON type (e.g. domain: 5, email: 5).
- E-52 400 missing_idempotency_key; 401 unauthenticated (missing, malformed, unknown token); 404 not_found; 409 idempotency_key_reuse; 422 validation_failed.
- E-53 Query ints: `1e9`, `4.0`, `+4` -> 422; limit 1..200 else 422; offset >=0 else 422; Idempotency-Key 1..255 else 422 (256 chars -> 422).
- E-54 Never 5xx, incl. concurrency and provider errors.

## Auth (§6)
- E-60 signup 201 {user_id, display_name, token}; login 200 same.
- E-61 email taken 409 email_taken; password <8 422; bad email 422; display_name empty/>100 422; wrong pw / unknown email 401 unauthenticated.
- E-62 Bearer required elsewhere except /health, /_test/*, auth; invalid token 401 even if idempotency key missing.
- E-63 Tokens don't expire; multiple valid tokens per account (login twice, both work).
- E-64 Passwords hashed (not checkable black-box except via export: no plaintext in export).
- E-65 Every authenticated user sees the same dossiers.

## Idempotency (§7) for POST /dossiers and POST /dossiers/{d}/refresh
- E-70 Missing/empty header -> 400 (after 401 check).
- E-71 First use normal; replay (same user, method, path, body) -> 200 with identical body JSON; same key different body -> 409.
- E-72 Key scoped per user; same key different path -> normal first use.
- E-73 `Acme-Robotics.test` vs `acme-robotics.test` in body/path are different requests (-> 409 on same key).
- E-74 Body compare as parsed JSON (order/whitespace); unknown fields ignored -> replay.
- E-75 Refresh ignores any body for replay purposes.
- E-76 Key reused after 4xx failure -> first use.
- E-77 Concurrent identical requests, unused key: exactly one normal response (202), others 200 same body; takes effect once.
- E-78 Replay returns original response even after dossier changed; starts no build, no provider call (M log).
- E-79 Already-claimed key resolved before field validation (valid -> invalid body same key -> 409), once body parsed as JSON object and authed.

## API (§8)
- E-80 Build semantics: one running at a time; ends ready or failed (failed = none of provider calls succeeded; fields unchanged); ready -> field known iff evidence supports value.
- E-81 Build with fast providers ends <=10 s of request.
- E-82 No 5xx/hang when provider errors; build stops before exceeding 80 units; completes with what it has.
- E-83 Read/list/any other request make no provider call (M log).
- E-84 POST /dossiers: new -> 202 {dossier_id, domain, state:"building"}; existing -> 200 with id, domain, current state, no build; concurrent same domain with different keys -> one dossier, one build.
- E-85 domain missing 422; invalid 422.
- E-86 GET /dossiers/{domain}: shape; state building/ready/failed; fields all six; before first ready all unknown; during later build fields = last ready; researched_at = clock time of request that started last ready build (or null); spent_units = total cost of every provider call by every build; 404 unknown.
- E-87 Refresh: 202 body; running build -> 202 same body, no second build; researches again even when unchanged, spend counted; 404 no dossier.
- E-88 GET /dossiers list: shape (dossier_id, domain, state, legal_name, researched_at, spent_units), has_more; q case-insensitive substring in domain or legal_name; empty q lists all; ordered by domain asc; limit default 50 / 1..200; offset default 0; has_more correct.
- E-89 spent_units equals ground-truth cost of mock log for the dossier (M).

## Providers and cost (§9)
- E-100 Costs as table; search returns <=10 results; refused call costs nothing; unanswered call costs units; extract per URL requested; nimble extract does not set render (M log cost 1 not 3).
- E-101 Build stops calls before >80 units.
- E-102 Research request names company by domain in query; output schema properties are field names (M log `fields`).
- E-103 Live providers: no give-up before 30 s per call or 120 s gathering; ends <=300 s (not testable with mock except via delay fault).

## Export/Import (§10)
- E-110 GET /_test/export 200 {track:"dossier", format_version:1, state}; unauthenticated; atomic snapshot.
- E-111 POST /_test/import: 204; replacement not merge; idempotent repeat; invalid JSON 400; missing fields / wrong track / wrong version / invalid state 422 and destination unchanged.
- E-112 Preserves accounts + hashed login, tokens, dossiers (ids, state, fields, citations, researched_at, spent_units), idempotency records + original responses; ids/timestamps not regenerated; failed keys reusable.
- E-113 Import makes no provider call; removes previous destination data and credentials; reset clears imported state; clock unchanged by export/import.
- E-114 Export during build holds pre-build dossier; after import, last completed build or failed+all unknown.
- E-115 Export contains no plaintext passwords (hashed) -- checked by grep.

## Concurrency (§11)
- E-120 Concurrent requests serialisable; invariants at every read (e.g. polling GET during build never shows partial/mixed fields, spent never decreases).

## Appendix A (support rule)
- E-90 A.1 sentence splitting: ends at . ! ? plus trailing " ” ’ ) when whitespace follows; legal-form suffix dot doesn't end; line breaks split; excerpt must be a single sentence.
- E-91 A.2 names company (domain or first label with - as space), whole-word, case-insensitive.
- E-92 A.2/A.3 statement phrase per field required; negating phrases (incl. "not", "could", "former", ...) exclude.
- E-93 A.2.5 at least one value in format and ALL format values normalise to V (two different years in one sentence -> no support).
- E-94 A.4 formats: legal_name (name/domain + capitalised/uppercase words + optional ", suffix", shortest); hq_city (longest cap-word run after phrase, hyphen-joined); ceo (2-3 cap words, company name and ceo phrases removed first); founded_year (4 digits 1800-2099 not amount); headcount (integer >=1 not amount; range holds two numbers -> both must map to same bucket); funding amounts ($, US$, USD, k/m/mn/bn, thousand/million/billion, "N million dollars"); non-USD not amounts.
- E-95 A.5 normalisation: headcount buckets, funding multiplied; fractional dollar result is not a value; digit/ number grammar (1,200; 12.5; digits next to letters not numbers).
- E-96 Citations in the result cite excerpts that pass the rule: verify offline by reimplementing A in the probe and checking every returned citation against the mock log's served texts.
