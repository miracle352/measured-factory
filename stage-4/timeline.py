"""Change over time (stage 3): entry typing, page versions, values at a date.  Pure functions, no I/O.

    classify(field, prev, new)           -> 'change' | 'correction' | None
    member_true_froms(field_obj)         -> {title: true_from}   (selected candidate of each title)
    values_at(builds, true_at, as_of)    -> {field: {"value", "true_from", "citations"}}   (7 fields)
    import_pages(candidates_by_field)    -> [{"url", "true_from", "candidates": {field: [cand]}}]

`prev` / `new` are field dicts holding at least "value" and "true_from"; for `executives` they must also hold
"candidates" (the assembled ones) so that each member's true_from can be read from its title's selected candidate.
`prev` None or {} is the same as a null value.
"""
from __future__ import annotations

from datetime import datetime, timezone

import candidates as C

FIELDS = ("legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total", "executives",
          "investors")
EXEC_TITLES = C.EXEC_TITLES


def _value(f: dict | None):
    return None if not isinstance(f, dict) else f.get("value")


def member_true_froms(field_obj: dict | None) -> dict:
    """{title: true_from} of the selected candidate of each title."""
    out = {}
    if not isinstance(field_obj, dict):
        return out
    for c in field_obj.get("candidates") or []:
        if c.get("selected") and c.get("title") in EXEC_TITLES:
            out[c["title"]] = c.get("true_from")
    return out


def _members(field_obj: dict | None) -> dict:
    v = _value(field_obj)
    if not isinstance(v, list):
        return {}
    return {m.get("title"): m.get("name") for m in v if isinstance(m, dict)}


def investor_members(cands: list[dict]) -> list[str]:
    """Pure: sorted names that are members of an investors field with these candidates."""
    return C.investor_members(cands)


def investor_true_froms(field_obj: dict | None) -> dict:
    """{name: true_from} for each name of the value: earliest non-null true_from of the candidates with the name."""
    out = {}
    if not isinstance(field_obj, dict):
        return out
    v = field_obj.get("value")
    for n in (v if isinstance(v, list) else []):
        tfs = [c.get("true_from") for c in field_obj.get("candidates") or []
               if c.get("value") == n and c.get("true_from") is not None]
        out[n] = min(tfs) if tfs else None
    return out


def _correction_dates(new_tf, old_tf) -> bool:
    return new_tf is not None and old_tf is not None and new_tf <= old_tf


def classify(field: str, prev: dict | None, new: dict | None) -> str | None:
    """Type of the history/feed entry for a changed selected value; None when the value did not change."""
    if field == "executives":
        a, b = _members(prev), _members(new)
        atf, btf = member_true_froms(prev), member_true_froms(new)
        differing = [t for t in EXEC_TITLES
                     if ((t in a) != (t in b)) or (t in a and t in b and C.value_key(a[t]) != C.value_key(b[t]))]
        if not differing:
            return None
        ok = all(t in a and t in b and _correction_dates(btf.get(t), atf.get(t)) for t in differing)
        return "correction" if ok else "change"
    if field == "investors":
        a = set(_value(prev) or [])
        b = set(_value(new) or [])
        if a == b:
            return None
        if a - b:
            return "change"                      # a name that left the value is never a correction
        old_tf = (prev or {}).get("true_from")
        tfs = investor_true_froms(new)
        ok = all(_correction_dates(tfs.get(n), old_tf) for n in b - a)
        return "correction" if ok else "change"
    pv, nv = _value(prev), _value(new)
    if C.value_key(pv) == C.value_key(nv):
        return None
    if pv is not None and nv is not None and _correction_dates(
            (new or {}).get("true_from"), (prev or {}).get("true_from")):
        return "correction"
    return "change"


# --------------------------------------------------------------------------- page versions

def _instant(text) -> datetime | None:
    if not isinstance(text, str):
        return None
    dt = C._parse_dt(text)
    if dt is None:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _holding_versions(builds: list[dict], as_of_iso: str | None, true_at: str) -> list[dict]:
    """Page versions (dicts with "true_from" and "candidates") that hold on true_at, known at as_of."""
    cutoff = _instant(as_of_iso) if as_of_iso is not None else None
    per_url: dict[str, list[list]] = {}     # url -> [[start, end, page], ...] in gathering order
    order: list[str] = []
    for b in builds or []:
        if b.get("outcome") != "ready":
            continue
        if cutoff is not None:
            t = _instant(b.get("time"))
            if t is None or t > cutoff:
                continue
        for page in b.get("pages") or []:
            url = page.get("url")
            tf = page.get("true_from")
            if url not in per_url:
                per_url[url] = []
                order.append(url)
            vs = per_url[url]
            if tf is None:
                vs.clear()                                  # replaces every earlier version of the URL
            else:
                vs[:] = [v for v in vs if v[0] is None or v[0] < tf]
                if vs:
                    vs[-1][1] = tf                          # the latest earlier version stops holding
            vs.append([tf, None, page])
    out = []
    for url in order:
        for start, end, page in per_url[url]:
            if start is None or start > true_at:
                continue
            if end is not None and end <= true_at:
                continue
            out.append(page)
    return out


def values_at(builds: list[dict], true_at: str, as_of_iso: str | None = None) -> dict:
    """For each of the seven fields the value that the evidence known at as_of says held on true_at."""
    pages = _holding_versions(builds, as_of_iso, true_at)
    out = {}
    for f in FIELDS:
        cands = []
        for p in pages:
            for c in (p.get("candidates") or {}).get(f) or []:
                d = dict(c)
                d["true_from"] = p.get("true_from")
                cands.append(d)
        a = C.assemble_field(cands, f)
        if a["value"] is None:
            out[f] = {"value": None, "true_from": None, "citations": []}
        else:
            out[f] = {"value": a["value"], "true_from": a["true_from"], "citations": a["citations"]}
    return out


def import_pages(candidates_by_field: dict) -> list[dict]:
    """Page versions for imported candidates: one per URL, true_from = UTC date part of published_at, else null."""
    pages: dict[str, dict] = {}
    for f, cands in (candidates_by_field or {}).items():
        for c in cands or []:
            url = c.get("url")
            if not url:
                continue
            p = pages.get(url)
            if p is None:
                p = pages[url] = {"url": url, "true_from": C.published_date(c.get("published_at")),
                                  "candidates": {}}
            p["candidates"].setdefault(f, []).append(dict(c, true_from=p["true_from"]))
    return list(pages.values())
