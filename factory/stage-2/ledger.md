# Stage 2 ledger

Spec: factory/stage-2/spec.md (stage-1 requirements still apply: factory/stage-1/spec.md, stage-1 ledger rows stay met).
Owners: A = builder-a, B = builder-b. Check: S = supplied harness, P = examiner probe.
Status: open until examiner accepts.

Layout (stage-2/, copy of stage-1/): 
- A: `candidates.py` (NEW: page kind, published time, ranking, selection, status, field assembly, import-candidate derivation), `build.py` (rendered extract, 429, costs, candidates from evidence), `support.py`, `measure.py`, `ui_evidence.py` (NEW: evidence + contested screens).
- B: `server.py`, `store.py` (candidates in state, negotiation, import, auth continuity), `ui.py` (NEW: shell/CSS/JS helpers, `/`, `/dossiers/{domain}`, `/signup`, `/login`), Dockerfile, RUN.md, requirements.txt.

Interfaces:
- `candidates.page_kind(headers_kind, url, company_domain) -> 'own'|'filing'|'news'|'aggregator'`; `candidates.parse_published(text) -> iso string or None`.
- `candidates.assemble_field(cands: list[dict]) -> {"value","status","citations","candidates"}` (ranks, marks selected, builds citations/status). Candidate dict keys: value,url,excerpt,provider,kind,published_at,retrieved_at.
- `candidates.derive_import_candidates(field, field_obj, researched_at) -> list[cand]` for stage-1 imports (see ruling in rulings.md).
- `build.run_build(domain, now_iso, should_abort)` returns fields already in assembled form (with `candidates`).
- `ui.render_page(title, main_html, script="", active="") -> str` (shared shell, nav, `current-user`, `logout-button`); `ui_evidence.evidence_main(domain)` / `contested_main()` -> (main_html, script) used by B's routes.

| ID | Statement | Owner | Check | Work | Status |
|---|---|---|---|---|---|
| R-01 | Page kind: `Kind: own/filing/news/aggregator` header gives the page's kind | A | P | W-1 | open |
| R-02 | Page with no Kind line or unlisted value: `own` when URL host (normalised as stage-1 domain) == company domain, else `aggregator` | A | P | W-1 | open |
| R-03 | `Published:` RFC 3339 timestamp = publication time; absent or non-RFC3339 value -> no publication time (null) | A | P | W-1 | open |
| R-04 | Page text = what a browser shows after load, no clicks; evidence read from it; citation excerpt must appear in that text | A | S,P | W-2 | open |
| R-05 | Citation/candidate `provider` is the provider that served the text the excerpt was copied from | A | P | W-2 | open |
| R-06 | Candidate = one value, one field, one excerpt, one page; one per page of the evidence that supports it | A | P | W-2 | open |
| R-07 | Evidence also holds the page each research claim cites, supported or not; build reads it like any page; unsupported claim is not a candidate | A | P | W-2 | open |
| R-08 | Candidate shape: value,url,excerpt,provider,kind,published_at(null ok),retrieved_at,selected; `retrieved_at` = build time (clock) | A | P | W-3 | open |
| R-09 | Same value = JSON-equal; strings compared exactly after trimming surrounding whitespace | A | P | W-3 | open |
| R-10 | Rank 1: authority own=filing > news > aggregator | A | P | W-3 | open |
| R-11 | Rank 2: later published_at higher within same authority; no published_at below all same-authority candidates with one | A | P | W-3 | open |
| R-12 | Rank 3: smaller url (code point) higher; same url -> provider order nimble,tavily,kernel,browserbase | A | P | W-3 | open |
| R-13 | Rank 4: same url+provider -> smaller value (ints numeric, strings code point after trim) | A | P | W-3 | open |
| R-14 | Exactly one candidate `selected:true`, rest false; `candidates` listed in rank order, selected first; field value = selected value; field citations = url/excerpt/provider of every candidate with that value in rank order | A | P | W-3 | open |
| R-15 | Lower-authority candidate selected only when no higher-authority candidate exists; rule runs over all candidates; same candidates -> same value (deterministic) | A | P | W-3 | open |
| R-16 | Status: known (candidates, all same value), contested (>=2 different values; still has value+citations), unknown (no candidates; value null, citations [], candidates []) | A | S,P | W-3b | open |
| R-17 | `candidates` = those of the last build that completed ready; failed build leaves fields/candidates unchanged | B | P | W-6 | open |
| R-18 | Each field in every dossier response carries `candidates`; `GET /dossiers` unchanged; its `legal_name` is the selected value | B | S,P | W-6 | open |
| R-19 | Extract via nimble may use `provider_options={"render": True}` to get browser text; neither browser vendor required | A | P | W-4 | open |
| R-20 | Optional `kernel`/`browserbase`: if used, base URLs passed in `provider_config` beside tavily/nimble; env keys read by WebRouter; unset/empty base URL never passed | A | P | W-4 | open |
| R-21 | Costs: rendered nimble extract 3/URL requested (incl. no page returned); kernel open 0; browserbase open 2; page served to a session 1; browse via browserbase 4; failed open/load/release 0; accounted in the 80-unit cap | A | S,P | W-4 | open |
| R-22 | Max 4 open sessions per provider; unused 60s closed; sessions always released by builds (no leak, also on abort/failure) | A | P | W-4 | open |
| R-23 | Rate limits: any call may get 429 and costs nothing; same call within <1s of its 429 is 429 again; never >3 in a row; session open 429 while 4 open until one closes | A | S,P | W-5 | open |
| R-24 | Build retries 429'd calls (waits >= 1s) and still finishes; time waiting after 429 does not count toward the stage-1 10s build time limit; stage-1 §8 timing still honoured otherwise | A | P | W-5 | open |
| R-25 | Gathering strategy chosen by measurement (>=2 approaches, cost per correct result incl. rendered extracts and 429s) recorded in measurements.md; build spend <= 80 | A | P | W-7 | open |
| R-26 | Content negotiation: `GET /dossiers/{domain}` returns UI for `Accept: text/html`, JSON otherwise (no Accept / application/json) | B | P | W-6 | open |
| R-27 | `/`, `/dossiers/{domain}/evidence`, `/contested`, `/signup`, `/login` are browser routes (HTML) reachable by URL; domain in browser routes normalised as stage-1 §4; other screens reachable through the UI (links) | B | P | W-8 | open |
| R-28 | Browser routes read the API's dossier data (same data); UI reads via API with auth of signed-in user | B | P | W-8 | open |
| R-29 | Signup screen: signup-email, signup-password, signup-display-name, signup-submit; creates account and signs in | B | P | W-9 | open |
| R-30 | Login screen: login-email, login-password, login-submit | B | P | W-9 | open |
| R-31 | `auth-error` present only when there is an error (wrong password, duplicate email, validation) | B | P | W-9 | open |
| R-32 | `current-user` visible on every screen when signed in, text contains display name; `logout-button` works (signs out) | B | P | W-9 | open |
| R-33 | List `/`: `research-domain`, `research-submit` (POST /dossiers), `research-error` on refusal (incl. invalid domain) | B | P | W-10 | open |
| R-34 | `dossier-search` filters as `q`; `dossier-list` children ordered by domain ascending; `dossier-item-{domain}` with `data-state`, text has domain and legal name when known, links to `/dossiers/{domain}`; `empty-dossiers` instead of list when none match | B | P | W-10 | open |
| R-35 | Research success (202 or 200) opens `/dossiers/{domain}` (normalised); a domain that already has a dossier (even created by another client after list read) opens it and starts no build | B | P | W-10 | open |
| R-36 | Dossier screen: `dossier-domain` exactly normalised domain; `dossier-state` exactly building/ready/failed; `dossier-spent` formatted with `data-units` integer; `dossier-researched-at` formatted, absent when null | B | P | W-11 | open |
| R-37 | `field-{field}` six, in stage-1 §4 table order, `data-status`; `field-value-{field}` formatted value with `data-value` (string unchanged, int plain digits) present only when non-null; `field-contested-{field}` marker only when contested | B | P | W-11 | open |
| R-38 | `field-citations-{field}` container in API order; `citation-{field}-{n}` (n from 1) text contains excerpt, contains link href = citation url, `data-provider` | B | P | W-11 | open |
| R-39 | `dossier-evidence-link` -> `/dossiers/{domain}/evidence`; `dossier-not-found` shown instead of fields when no dossier | B | P | W-11 | open |
| R-40 | `dossier-refresh` sends POST /dossiers/{domain}/refresh; `refresh-error` on refusal; `dossier-reload` reads again without starting a build | B | P | W-12 | open |
| R-41 | While `building` screen re-reads at least every 2s until ready/failed and shows new fields without manual reload (also when another client's refresh is running; refresh from this browser while another build runs answered 202 and screen follows the running build) | B | P | W-12 | open |
| R-42 | Latest read wins: delayed earlier read (incl. building polls, reload) never overwrites a later one, out-of-order responses | B | P | W-12 | open |
| R-43 | After any successful action the page shows new state without manual reload; navigation waits for the write to succeed before refreshing data | B | P | W-12 | open |
| R-44 | Lost research/refresh response (incl. after commit): show `research-uncertain`/`refresh-uncertain` with nonempty text, not `*-error`; request stays retryable with same Idempotency-Key and body; successful retry removes both error and uncertainty elements, shows dossier, at most one build | B | P | W-12 | open |
| R-45 | Evidence screen: `evidence-{field}` x6 containers, children in API candidates order | A | P | W-13 | open |
| R-46 | `candidate-{field}-{n}` text contains formatted value and excerpt; attributes data-value, data-provider, data-kind, data-url, data-published-at (RFC3339 or empty), data-selected true/false | A | P | W-13 | open |
| R-47 | `evidence-empty-{field}` shown instead of candidates when none | A | P | W-13 | open |
| R-48 | Contested screen: `contested-list` children by domain asc then field table order; `contested-item-{domain}-{field}` with data-value (selected), text has domain, field, every distinct candidate value, links to evidence; `empty-contested` instead of list when none | A | P | W-13 | open |
| R-49 | Product quality: clear value+status, citations beside it, quoted excerpt as text and link to URL; consistent visual system; known/unknown/contested/building/failed/loading/success/refused/uncertain visually distinct; primary actions identifiable | B(shell)+A | P | W-9,W-13 | open |
| R-50 | Humans first: format names, years, headcount ranges, money, timestamps readable; status/provider/kind/published time understandable (labels, not raw keys); no internal keys/ids shown | B+A | P | W-11,W-13 | open |
| R-51 | Usable at 375px and desktop with no horizontal page scroll; visible labels on inputs; visible focus; sufficient contrast; empty/loading/error states; consistent navigation across routes | B+A | P | W-9,W-13 | open |
| R-52 | Import accepts a stage-1 service export (same team format_version 1) and also a stage-2 export (round trip) | B | S,P | W-14 | open |
| R-53 | Browser signed in before export/import stays signed in after (tokens valid; UI auth state survives; no re-login) | B | P | W-14 | open |
| R-54 | Imported dossiers appear in list and on screens; each imported field gains one candidate per value supported by served text of last stage-1 ready build, once per supporting page (ruling: stage-1 export holds citations only -> one candidate per citation whose excerpt supports the field value); kind/published_at from export or null; retrieved_at = researched_at; provider = citation provider | A(derive)+B | P | W-14 | open |
| R-55 | Imported field value/status/citations follow from its candidates by selection rule and Status; imported candidate kind null has authority of aggregator | A+B | P | W-14 | open |
| R-56 | Research/refresh whose response was lost before export is retryable after import with same body and key; UI recovers original response and shows the imported dossier | B | P | W-14 | open |
| R-57 | Imported dossier candidates replaced by those of its next completed build | B | P | W-14 | open |
| R-58 | Stage-2 export still opaque round trip: stage-2 service export (with candidates) imports unchanged; repeat import restores state | B | S,P | W-14 | open |
| R-59 | General: all stage-1 requirements still hold (supplied stage-1 check passes); stage-1 `status` values known/unknown still valid shapes | A+B | S | W-6 | open |
