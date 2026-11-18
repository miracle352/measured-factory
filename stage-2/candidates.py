"""Candidates: page kind, publication time, ranking, selection, status, field assembly, import derivation.

Pure functions, no I/O.  Stage-2 spec: "Candidates", "The selection rule", "Status".

    page_kind(headers_kind, url, company_domain) -> 'own' | 'filing' | 'news' | 'aggregator'
    parse_published(text) -> RFC 3339 string (offset kept) | None
    rank_key(cand) / rank(cands)
    assemble_field(cands) -> {"value", "status", "citations", "candidates"}
    derive_import_candidates(field, field_obj, researched_at, domain=None) -> [cand]
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

KINDS = ("own", "filing", "news", "aggregator")
_AUTHORITY = {"own": 0, "filing": 0, "news": 1, "aggregator": 2}
PROVIDER_ORDER = ("nimble", "tavily", "kernel", "browserbase")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_RFC3339 = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$")


def normalise_host(url: str) -> str:
    """Host of a URL, normalised like a stage-1 domain: lowercased, one trailing '.' and one leading 'www.' removed."""
    rest = (url or "").strip().split("://", 1)[-1]
    rest = re.split(r"[/?#]", rest, 1)[0]
    rest = rest.rsplit("@", 1)[-1]
    if rest.startswith("["):
        host = rest
    else:
        host = rest.split(":", 1)[0]
    host = host.strip().lower()
    if host.endswith("."):
        host = host[:-1]
    if host.startswith("www."):
        host = host[4:]
    return host


def page_kind(headers_kind: str | None, url: str, company_domain: str) -> str:
    k = (headers_kind or "").strip()  # exact match, case-sensitive (ruling): "News" takes the default rule
    if k in KINDS:
        return k
    return "own" if normalise_host(url) == (company_domain or "").strip().lower() else "aggregator"


def _parse_dt(text: str) -> datetime | None:
    m = _RFC3339.match((text or "").strip())
    if not m:
        return None
    y, mo, d, h, mi, s = (int(m.group(i)) for i in range(1, 7))
    frac = m.group(7)
    micro = int((frac[1:] + "000000")[:6]) if frac else 0
    tz = m.group(8)
    if tz in ("Z", "z"):
        tzinfo = timezone.utc
    else:
        sign = 1 if tz[0] == "+" else -1
        oh, om = int(tz[1:3]), int(tz[4:6])
        if oh > 23 or om > 59:
            return None
        tzinfo = timezone(sign * timedelta(hours=oh, minutes=om))
    try:
        return datetime(y, mo, d, h, mi, s, micro, tzinfo=tzinfo)
    except ValueError:
        return None


def parse_published(text: str | None) -> str | None:
    dt = _parse_dt(text) if isinstance(text, str) else None
    return dt.isoformat() if dt else None


def _instant(published_at: str | None) -> int | None:
    dt = _parse_dt(published_at) if isinstance(published_at, str) else None
    if dt is None:
        return None
    return (dt - _EPOCH) // timedelta(microseconds=1)


# --------------------------------------------------------------------------- values

def norm_value(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


def value_key(v: Any) -> str:
    """Equality key: two values are the same value when equal as JSON values (strings trimmed)."""
    v = norm_value(v)
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def _value_rank(v: Any):
    v = norm_value(v)
    if isinstance(v, bool):
        return (2, int(v), "")
    if isinstance(v, (int, float)):
        return (0, v, "")
    return (1, 0, v if isinstance(v, str) else json.dumps(v, sort_keys=True, ensure_ascii=False))


# --------------------------------------------------------------------------- ranking

def rank_key(c: dict):
    authority = _AUTHORITY.get(c.get("kind"), 2)       # kind null (imported) has the authority of aggregator
    inst = _instant(c.get("published_at"))
    prov = c.get("provider")
    pidx = PROVIDER_ORDER.index(prov) if prov in PROVIDER_ORDER else len(PROVIDER_ORDER)
    return (authority, 0 if inst is not None else 1, -(inst or 0), c.get("url") or "", pidx,
            prov or "", _value_rank(c.get("value")), c.get("excerpt") or "")


def rank(cands: list[dict]) -> list[dict]:
    return sorted(cands, key=rank_key)


def _dedupe(ranked: list[dict]) -> list[dict]:
    """One candidate per (page, value): the best ranked."""
    seen, out = set(), []
    for c in ranked:
        k = (c.get("url"), value_key(c.get("value")))
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def assemble_field(cands: list[dict]) -> dict:
    ranked = _dedupe(rank(cands or []))
    if not ranked:
        return {"value": None, "status": "unknown", "citations": [], "candidates": []}
    out = []
    for i, c in enumerate(ranked):
        d = {
            "value": norm_value(c.get("value")),
            "url": c.get("url"),
            "excerpt": c.get("excerpt"),
            "provider": c.get("provider"),
            "kind": c.get("kind"),
            "published_at": c.get("published_at"),
            "retrieved_at": c.get("retrieved_at"),
            "selected": i == 0,
        }
        out.append(d)
    top = value_key(out[0]["value"])
    distinct = {value_key(c["value"]) for c in out}
    citations = [{"url": c["url"], "excerpt": c["excerpt"], "provider": c["provider"]}
                 for c in out if value_key(c["value"]) == top]
    return {"value": out[0]["value"], "status": "known" if len(distinct) == 1 else "contested",
            "citations": citations, "candidates": out}


def empty_field() -> dict:
    return assemble_field([])


# --------------------------------------------------------------------------- stage-1 import

def derive_import_candidates(field: str, field_obj: dict | None, researched_at: str | None,
                             domain: str | None = None) -> list[dict]:
    """Candidates for an imported stage-1 field: one per citation (page) whose excerpt supports the field's value.

    With `domain` given the excerpt is checked with support.py; without it every citation of a known field counts
    (stage-1 guaranteed support).  kind/published_at come from the exported citation when it records them, else null.
    """
    if not isinstance(field_obj, dict):
        return []
    value = field_obj.get("value")
    if value is None:
        return []
    out, seen = [], set()
    for cit in field_obj.get("citations") or []:
        if not isinstance(cit, dict) or not cit.get("url") or not cit.get("excerpt"):
            continue
        if domain:
            import support
            if not support.supports(field, value, cit["excerpt"], domain):
                continue
        if cit["url"] in seen:
            continue
        seen.add(cit["url"])
        kind = cit.get("kind")
        out.append({
            "value": value, "url": cit["url"], "excerpt": cit["excerpt"], "provider": cit.get("provider"),
            "kind": kind if kind in KINDS else None,
            "published_at": parse_published(cit.get("published_at")),
            "retrieved_at": researched_at,
        })
    return out


def assemble_import_field(field: str, field_obj: dict | None, researched_at: str | None,
                          domain: str | None = None) -> dict:
    return assemble_field(derive_import_candidates(field, field_obj, researched_at, domain))
