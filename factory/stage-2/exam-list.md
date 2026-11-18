# Stage 2 exam list (from the stage-2 specification only)

IDs F-xx. Section refs name the stage-2 spec headings; "S1 §n" = stage-1 spec. Stage-1 requirements (E-xx list) continue to apply.
Tags: API = HTTP probe, UI = headless browser probe (375px and desktop), M = needs mock provider admin (log, faults, corpus control), I = export/import.

## A. Global (intro, "applies to all operations")
- F-01 Intro item 3: a field's selected value is what the selection rule picks from its candidates; same candidates -> same value (determinism across builds/refreshes/imports). API
- F-02 S1 requirements still hold (citations served + supporting, <=80 units per build, idempotency, auth, errors, export/import, 10 s build bound). API

## B. Page kind and publication time (§Page kind and publication time)
- F-10 `Kind: own|filing|news|aggregator` header gives the page kind. API M
- F-11 No `Kind` line, or an unlisted value -> kind `own` when URL host (normalised like a domain: lowercase, trailing "." and leading "www." removed) equals the company's domain; else `aggregator`. Includes `www.` host, uppercase host, host with trailing dot, subdomain (not equal -> aggregator), port? (host only). API M
- F-12 `Published: <RFC 3339>` gives publication time; absent or non-RFC3339 value (e.g. `yesterday`, `2026-01-10` date only, no offset) -> no publication time (`published_at` null). API M
- F-13 Kind/Published are read from header lines only (not prose). API M

## C. Page text (§Page text)
- F-20 Page text = text a browser shows after load, no clicks. Evidence is read from that text; JS-rendered facts are found. API M
- F-21 A citation's excerpt appears in the page's browser text. API M
- F-22 Citation/candidate `provider` is the provider that served the text the excerpt was copied from (a rendered extract through nimble is `nimble`; kernel/browserbase if used). API M
- F-23 Graded corpus has no click-only facts: collapsed/disclosure content need not be harvested (no requirement). (informational)

## D. Web access (§Web access) and cost
- F-30 Nimble extract with `render` costs 3 per URL requested incl. URLs with no page; plain extract still 1 (S1). M
- F-31 `kernel` open session cost 0; `browserbase` open 2; each page served to a session 1 (either); browserbase browse run 4; failed open / failed page load / release cost 0. M
- F-32 A service need not use kernel/browserbase; rendered nimble extract alone suffices. (no requirement)
- F-33 At most 4 sessions open per provider; the 5th open is an error (429). A session idle 60 s is closed by provider. Service must not leak sessions: after builds, sessions are released (open sessions at mock = 0). M
- F-34 `spent_units` and the per-build 80-unit cap use these costs; a build never spends >80 including rendered extracts and sessions. M
- F-35 Providers kernel/browserbase reached only via WebRouter with `provider_config` base_url; no other route. (static)

## E. Rate limits (§Rate limits)
- F-40 A provider may answer any call with 429; a 429 costs nothing (not counted in `spent_units`). M
- F-41 Same call (provider, operation, args) repeated <1 s after a 429 is answered 429 again; so a retry within 1 s is wasted; a build should wait >=1 s (waiting does not count toward the 10 s bound). M
- F-42 No call is 429 more than 3 times in a row (except opening a session while 4 open). A build that retries with a delay >=1 s gets its data. M
- F-43 Time spent waiting after a 429 does not count toward the 10 s build bound: a build whose calls each answer within 1 s, plus 429 waits, still ends within 10 s + waits (the build completes `ready`, not `failed`, despite 429s). M
- F-44 Build that meets 429 repeatedly on every call still ends `ready` with the data (not `failed`) after retries; `failed` only when none of its provider calls succeeded. M
- F-45 Requests (API) never 5xx when providers answer 429. API M

## F. Candidates (§Candidates)
- F-50 Every value a page of the evidence supports for a field is a candidate of that field, once per such page. M
- F-51 Evidence now includes the page each research claim cites, whether or not the citation supports its claim; the build reads that page like any other (so a research-cited page may yield candidates even if the claim itself is false). M
- F-52 A research claim whose citation does not support it is not itself a candidate (value from claim w/o support never appears). M
- F-53 Candidate `provider` is a provider that served the excerpt's text (any when several). M
- F-54 Each field has `candidates` (list). Candidate keys: value, url, excerpt, provider, kind, published_at, retrieved_at, selected. API
- F-55 candidate url/excerpt/provider obey citation rules (excerpt copied from served text, 1-500 chars, single sentence supporting the value, from prose not header; url = page it was served for). API M
- F-56 `kind` is page kind; `published_at` is publication time (RFC 3339 w/ offset) or null. API
- F-57 `retrieved_at` = time (clock) of the build that gathered the candidate (the build's time = request receipt time). API
- F-58 `selected` is true on exactly one candidate of a field with candidates and false on the others. API
- F-59 `candidates` lists those of the last build that completed `ready`, in selection-rank order, selected first. While a later build runs, candidates are those of the last ready build; a failed build leaves candidates unchanged. API
- F-60 Field with no candidate: `candidates: []`, status unknown, value null, citations []. A dossier before first ready build: all six fields have `candidates: []`. API
- F-61 Two values are the same value when equal as JSON values; strings compared exactly after trimming whitespace (e.g. integer 2014 vs "2014" distinct; ` Lisbon ` == `Lisbon`). API
- F-62 One candidate per supporting page: the same value supported by two different pages -> two candidates; the same page cited by research and found by search -> still once per page (not duplicated). M
- F-63 Candidates from a page supporting different values for the same field (not possible in one sentence, but across sentences) -> a candidate for each supporting sentence/excerpt? Spec: "every value that a page supports... once for each such page" -> at most one candidate per (page,value) (probe documents behaviour, soft). M

## G. Selection rule (§The selection rule)
- F-70 Rank 1 authority: `own` = `filing` > `news` > `aggregator`. API M
- F-71 Rank 2 recency within same authority: later `published_at` higher; no publication time ranks below every candidate of same authority that has one. `own` vs `filing` same authority, so recency decides between them. API M
- F-72 Rank 3 URL: equal authority and equal published_at -> smaller URL by Unicode code point ranks higher (uppercase before lowercase; non-ASCII by code point not locale). API M
- F-73 Same URL: provider order nimble, tavily, kernel, browserbase. API M
- F-74 Same URL and provider: smaller value ranks higher; integers numerically (e.g. 9 before 10), strings by code point after trimming. API M
- F-75 Lower-authority candidate selected only when no higher-authority candidate exists; an old `own` beats a newer `news`/`aggregator`. API M
- F-76 Equal published_at compared as instants (e.g. `+00:00` vs `Z` vs offset giving same instant are equal; offsets compared as time). API M
- F-77 Rule runs over all of the field's candidates (not only the page of research claim). M
- F-78 Field `value` = selected candidate's value; `citations` = url/excerpt/provider of every candidate with that value, in rank order (selected first), no citations of other values. API
- F-79 Citation count = number of candidates with the selected value (no dedupe / no cap of 3; stage-1's cap-3 ruling no longer applies). API
- F-80 Imported candidate (null kind) has authority of `aggregator`; null published_at. API I

## H. Status (§Status)
- F-90 `known`: has candidates, all same value. API
- F-91 `contested`: candidates carry two or more different values. API
- F-92 `unknown`: no candidates; value null. API
- F-93 A contested field still has selected value and its citations. API
- F-94 A field supported by two pages with the same value is `known`, not contested. API
- F-95 `GET /dossiers` unchanged; `legal_name` listed is the selected value; `q` filter matches selected legal_name. API
- F-96 Status enumeration is exactly known|contested|unknown. API

## I. Routes and content negotiation (§Screens)
- F-100 Routes reachable by URL: `/`, `/dossiers/{domain}`, `/dossiers/{domain}/evidence`, `/contested`, `/signup`, `/login`. UI
- F-101 Other screens reachable through the UI (navigation links between screens; refresh/evidence/contested from the dossier/list). UI
- F-102 `GET /dossiers/{domain}` with `Accept: text/html` returns the UI (HTML), without it JSON (API unchanged, auth required for JSON). API
- F-103 `/`, `/dossiers/{domain}/evidence`, `/contested` are browser routes; they read the API data; domain in browser route normalised as S1 §4 (e.g. `/dossiers/WWW.Acme-Robotics.TEST.` shows acme-robotics.test). UI
- F-104 HTML routes need no runtime assets from the internet (fonts, scripts, css bundled). UI
- F-105 JSON/API behaviour (401, 404, errors) on `GET /dossiers/{domain}` without Accept html unchanged. API
- F-106 Unauthenticated browser visiting `/`, dossier screens: UI handles (redirect or prompt to login, no crash); `/signup`, `/login` accessible signed out. UI

## J. Auth screens
- F-110 `/signup` has signup-email, signup-password, signup-display-name, signup-submit; submitting creates the account and signs the user in. UI
- F-111 `/login` has login-email, login-password, login-submit; success signs in. UI
- F-112 `auth-error` present only when there is an error (taken email, short password, bad email, wrong password); absent otherwise. UI
- F-113 `current-user` visible on every screen when signed in, text contains display name; `logout-button` signs out (current-user disappears, token not usable in browser session). UI
- F-114 Visible labels for inputs; keyboard focus visible. UI

## K. Dossier list `/`
- F-120 `research-domain`, `research-submit` (POST /dossiers with idempotency key), `research-error` (when refused, incl. invalid domain; absent otherwise). UI
- F-121 `dossier-search` filters list as `q` does (domain or legal_name contains, case-insens). UI
- F-122 `dossier-list` container; children ordered by domain ascending. `dossier-item-{domain}` carries `data-state`, text has domain and the legal name when known; links to `/dossiers/{domain}`. UI
- F-123 `empty-dossiers` shown instead of the list when no dossier matches (no dossiers or search without match). UI
- F-124 Successful research (202 or 200) opens `/dossiers/{normalised domain}`. UI
- F-125 Domain that already has a dossier (also one created by another client after the list was read) opens that dossier, starts no build (200 path). UI M
- F-126 Invalid domain -> research-error, no navigation. UI
- F-127 Research with ` WWW.Acme-Robotics.TEST. ` opens normalised path. UI

## L. Dossier screen `/dossiers/{domain}`
- F-130 `dossier-domain` exact normalised domain; `dossier-state` exactly building|ready|failed; `dossier-spent` formatted spent_units with `data-units` integer; `dossier-researched-at` contains formatted researched_at, absent when null. UI
- F-131 Six `field-{field}` in the stage-1 table order, each `data-status`. UI
- F-132 `field-value-{field}` present only when value non-null, with `data-value` (string unchanged; integer plain decimal digits; e.g. 12000000 not `12,000,000`). Visible text is formatted for people (e.g. money, year without grouping). UI
- F-133 `field-contested-{field}` present only when contested. UI
- F-134 `field-citations-{field}` contains citations in API order; `citation-{field}-{n}` (n from 1) contains the excerpt text, a link with href = citation url, `data-provider`. UI
- F-135 `dossier-evidence-link` links to `/dossiers/{domain}/evidence`. UI
- F-136 `dossier-refresh` sends POST refresh; `refresh-error` on refusal; `dossier-reload` re-reads without starting a build (no provider calls, spent_units unchanged). UI
- F-137 `dossier-not-found` shown instead of fields when no dossier (and no six field elements). UI
- F-138 While `building`, screen reads again at least every 2 s until ready/failed, then shows new fields without manual reload. UI
- F-139 After a refresh the same page shows the new state without reload (dossier-state becomes building then ready; data updated). UI
- F-140 Navigation waits for the write to succeed before refreshing data (no navigation to the dossier on failed research). UI
- F-141 Latest read wins: a delayed earlier read must not overwrite a later one, incl. out of order responses (reload vs poll) . UI
- F-142 Another client's refresh while this browser has stale data: this browser's refresh is 202 and the screen follows the running build to its end. UI
- F-143 Lost response to research/refresh (incl. after commit) -> `research-uncertain`/`refresh-uncertain` with nonempty text, not `research-error`/`refresh-error`; request stays retryable with the same key and body; successful retry removes both error and uncertainty elements, shows dossier, starts at most one build. UI
- F-144 Citation shows excerpt as quoted text and links to URL; status, provider, kind, published time understandable (not raw API data). UI
- F-145 `dossier-spent` text is a formatted number; `data-units` plain integer. UI
- F-146 State exposed visually distinct for known/unknown/contested/building/failed/loading/successful/refused/uncertain (distinguishable styling; screenshot review). UI

## M. Evidence screen
- F-150 `evidence-{field}` six containers, children in API candidates order. UI
- F-151 `candidate-{field}-{n}` text contains formatted value and excerpt; attributes data-value, data-provider, data-kind, data-url, data-published-at (RFC 3339, empty when null), data-selected true|false. UI
- F-152 `evidence-empty-{field}` shown instead of candidates when none. UI
- F-153 Evidence of an imported dossier: data-kind empty/null handled (no literal "null"/"None"); published-at empty. UI I
- F-154 Evidence page for an unknown domain shows a not-found state without crash. UI

## N. Contested screen
- F-160 `contested-list` ordered by domain asc then field in table order. UI
- F-161 `contested-item-{domain}-{field}` for every contested field of any dossier; data-value = selected value; text contains domain, field and every distinct candidate value; links to `/dossiers/{domain}/evidence`. UI
- F-162 `empty-contested` instead of the list when none contested; known/unknown fields not listed. UI
- F-163 Contested screen sees dossiers beyond first page of 50/200 (reads all dossiers). UI M

## O. Refresh and competing clients
- F-170 After any successful action the data on the same page shows the new state without manual reload. UI
- F-171 Apart from polling while building, no live update required (no test).
- F-172 Browser refresh while another client's build runs: 202 same body, screen follows the build. UI
- F-173 Retry with same key & body after lost response (including after commit): API returns original/200 replay; at most one build. API UI

## P. Upgrade / import (§Existing clients after an upgrade)
- F-180 Stage-2 service accepts an export from the stage-1 service (track dossier, format_version 1). I
- F-181 A browser signed in before import stays signed in after (token and localStorage/cookie survive; current-user still shown). UI I
- F-182 Imported dossiers appear in list and on screens. UI I
- F-183 Each imported field gains one candidate for every value that text the providers served to the last stage-1 ready build supports (once per page). Stage-1 export holds only citations; ruling: one candidate per stage-1 citation whose excerpt supports the field's value. I
- F-184 Imported candidate: excerpt supports the value; provider is the citation's provider; kind and published_at as exported or null; retrieved_at = dossier's researched_at. I
- F-185 Imported field's value/status/citations follow from candidates by the selection rule and Status (null-kind = aggregator authority; same value -> known; field `unknown` with candidates [] when none). I
- F-186 A research/refresh whose response was lost before export remains retryable after import with the same body and key; the UI recovers the original response and shows the imported dossier. UI I
- F-187 No page reload or new screen required for import. (no test)
- F-188 Imported candidates are replaced by those of the dossier's next completed build (retrieved_at = new build time, kind/published_at real). I M
- F-189 Import still follows stage-1 §10 (replacement not merge, idempotent, 422 on bad version/track, no provider calls, ids/timestamps preserved). API I
- F-190 Stage-2 export re-imported into stage-2 preserves candidates exactly. I

## Q. Product quality & responsive (§Product and visual direction)
- F-200 At 375 CSS px and at desktop widths (e.g. 1280): no horizontal page scroll on all six routes in all states (document scrollWidth <= viewport). UI
- F-201 Inputs have visible labels (label element or visible text bound to inputs); keyboard focus apparent (focus style differs from unfocused). UI
- F-202 Text/control contrast sufficient (>= WCAG AA 4.5:1 normal text, sampled). UI
- F-203 Considered empty/loading/error states; consistent navigation across the required routes (same nav on each). UI
- F-204 Known/unknown/contested/building/failed states visually distinct (differing computed styles/labels). UI
- F-205 Primary actions (research, refresh) visually identifiable. UI
- F-206 People-first formatting: names, years (no thousands separators), headcount ranges, money (e.g. `$12,000,000` or `$12M`), timestamps; technical ids not shown unnecessarily (no raw ISO `T..+00:00` text only? soft). UI
- F-207 Touch targets reasonable at 375 (>= ~32px high; soft). UI
- F-208 No console errors / failed requests on the routes. UI
