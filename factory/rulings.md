# Rulings

## Stage 1
- Amount with a double space inside (`$12  million`): treated as one space (spec silent; examiner agreed).
- Bare `$12` is itself an amount, so `$12 millions` supports 12.
- Excerpt containing a non-whole-dollar amount supports nothing (A.5).
- Failed build: build returns fields=None; store keeps old fields, adds spent_units, researched_at unchanged.
- Strategy: nimble lite domain search + nimble research (all six fields) + extracts + at most 6 follow-up searches; tavily never called.
- Multiple supported values: highest source trust, then latest date, then most pages; cite at most 3 excerpts for that value.

## Stage 2
- Stage-1 export holds only citations (no served text): imported candidates = one per stage-1 citation whose excerpt supports the field's value (kind/published_at null, provider = citation provider, retrieved_at = researched_at). Candidates with kind null rank as aggregator.
- Stage 2: field `citations` lists every candidate with the selected value (no cap of 3); stage-1 "cite at most 3" ruling is superseded.
- Stage 2: `Kind:` header value matches the listed values exactly (surrounding whitespace trimmed, case-sensitive); anything else, including `News`, takes the default rule. Same for `Published`: strict RFC 3339.

## Stage 3
- Stage-2 exports of our own service hold only the latest fields (no builds list). Import treats them as one ready build at `researched_at` (as for stage-1), imported candidates' learned_at = retrieved_at; page-version true_from = UTC date part of the candidate's published_at, else null (Effective is not recoverable). If an export does carry a `builds` list, keep it (time, outcome, spent) and its candidates.
- All new endpoints (`/changes`, `/history`, `/values`, as_of) require a bearer token (401 otherwise), as every non-listed endpoint in §6.
- Validation (422) is checked before 404 on as_of / true_at, as in earlier stages.
