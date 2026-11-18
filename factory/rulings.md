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
