"""Examiner probes (API). Written from the stage-2 spec; the oracle is the corpus key's
supports plus each page's header, ranked by my own reading of the selection rule."""
import json
import time
from datetime import datetime

import httpx
import pytest

import fixtures as fx
import web as dw
from harness.http import Api, RESET_TIMEOUT, assert_status, new_key

pytestmark = pytest.mark.stage(2)
AUTH = {"own": 0, "filing": 0, "news": 1, "aggregator": 2}


def page_kind(corpus, url, domain):
    """Spec: Kind header if listed, else own iff normalised host == domain, else aggregator."""
    k = dw.header(corpus.page(url)).get("Kind")
    if k in dw.KINDS:
        return k
    return "own" if dw.host(url) == domain else "aggregator"


def page_pub(corpus, url):
    s = dw.header(corpus.page(url)).get("Published")
    return dw.rfc3339(s) if s else None


def expected_cands(corpus, domain, field):
    out = []
    for s in corpus.evidence(domain, 0):
        if s["field"] == field:
            out.append({"value": s["value"], "url": s["url"],
                        "kind": page_kind(corpus, s["url"], domain),
                        "pub": page_pub(corpus, s["url"])})
    return out


def rank(c):
    pub = c["pub"]
    v = c["value"]
    return (AUTH[c["kind"]], pub is None, -(pub.timestamp() if pub else 0), c["url"],
            (isinstance(v, str), v.strip() if isinstance(v, str) else v))


def domains(corpus):
    return sorted(d for d in corpus.key if "expected" in corpus.key[d])


def wait_done(client, d, seconds=40):
    end = time.monotonic() + seconds
    while True:
        r = client.get(f"/dossiers/{d}")
        assert r.status_code == 200, r.status_code
        if r.json()["state"] != "building" or time.monotonic() > end:
            return r.json()
        time.sleep(0.1)


def test_p01_candidates_match_oracle(world, build, corpus):
    """R-09,R-10,R-12..R-24: candidate set, order, selected, status, kind, published."""
    bad = []
    for d in domains(corpus):
        body = build(d)
        if body["state"] != "ready":
            bad.append((d, "state", body["state"]))
            continue
        for f in fx.FIELDS:
            fld = body["fields"][f]
            exp = sorted(expected_cands(corpus, d, f), key=rank)
            got = fld["candidates"]
            gk = sorted((c["url"], json.dumps(c["value"])) for c in got)
            ek = sorted((c["url"], json.dumps(c["value"])) for c in exp)
            if gk != ek:
                bad.append((d, f, "set", gk, ek))
                continue
            order = [(c["url"], json.dumps(c["value"])) for c in got]
            if order != [(c["url"], json.dumps(c["value"])) for c in exp]:
                bad.append((d, f, "order", order))
            for c in got:
                e = next(x for x in exp if x["url"] == c["url"] and x["value"] == c["value"])
                if c["kind"] != e["kind"]:
                    bad.append((d, f, "kind", c["url"], c["kind"], e["kind"]))
                gp = dw.rfc3339(c["published_at"]) if c["published_at"] else None
                if gp != e["pub"]:
                    bad.append((d, f, "pub", c["url"], c["published_at"], str(e["pub"])))
            vals = {json.dumps(c["value"]) for c in got}
            st = "unknown" if not got else "known" if len(vals) == 1 else "contested"
            if fld["status"] != st:
                bad.append((d, f, "status", fld["status"], st))
            if sum(c["selected"] for c in got) != (1 if got else 0):
                bad.append((d, f, "selected-count"))
    assert not bad, bad[:10]


def test_p02_shape_and_provenance(world, build, corpus, web, assert_citations):
    """R-12,R-14,R-15,R-23,R-17: shape, retrieved_at, citations, excerpts are served text."""
    d = domains(corpus)[0]
    body = build(d)
    assert_citations(body)
    calls = web.log()
    for f in fx.FIELDS:
        fx.assert_candidates(f, body["fields"][f])
        for c in body["fields"][f]["candidates"]:
            assert fx.instant(c["retrieved_at"]) == fx.instant(fx.NOW)
            assert dw.served(calls, c["provider"], c["url"], c["excerpt"]), c


def test_p03_cost_cap_and_spent(world, build, corpus, web):
    """R-06: every company <=80 units per build; spent_units == logged units."""
    for d in domains(corpus):
        web.reset()
        body = build(d)
        assert web.units() <= 80, (d, web.units())
        assert body["spent_units"] == web.units(), (d, body["spent_units"], web.units())


def test_p04_list_legal_name_is_selected(world, build, corpus):
    """R-25."""
    d = domains(corpus)[0]
    body = build(d)
    lst = assert_status(world.alice.get("/dossiers"), 200).json()["dossiers"]
    e = next(x for x in lst if x["domain"] == d)
    assert e["legal_name"] == body["fields"]["legal_name"]["value"]


@pytest.mark.parametrize("mode", ["rate_limit", "throttle"])
def test_p05_429_no_cost_no_failure(world, build, corpus, web, mode):
    """R-08,R-53: 429s cost nothing, no 5xx; throttle (first attempt 429) still ends ready."""
    for prov in fx.PROVIDERS:
        web.fault(prov, list(fx.METHODS), mode)
    d = domains(corpus)[1]
    body = build(d, seconds=60)
    log = web.log()
    assert all(c["cost"] == 0 for c in log if c["status"] == 429), \
        [c for c in log if c["status"] == 429 and c["cost"]][:3]
    assert body["spent_units"] == web.units()
    assert web.units() <= 80
    if mode == "throttle":
        assert body["state"] == "ready", body["state"]
        assert any(c["status"] == 429 for c in log)
        for f in fx.FIELDS:
            fx.assert_candidates(f, body["fields"][f])


def test_p06_provider_errors_no_5xx(world, corpus, web):
    """R-53: all providers 500 -> failed, readable, all unknown, candidates []."""
    d = domains(corpus)[0]
    for prov in fx.PROVIDERS:
        web.fault(prov, list(fx.METHODS), "error")
    r = world.alice.post("/dossiers", json={"domain": d}, idempotency_key=new_key())
    assert r.status_code == 202
    body = wait_done(world.alice, d)
    assert body["state"] == "failed"
    fx.assert_all_unknown(body, 2)
    assert all(f["candidates"] == [] for f in body["fields"].values())


def test_p07_failed_refresh_keeps_candidates(world, build, corpus, web, settle):
    """R-57."""
    d = domains(corpus)[0]
    before = build(d)
    for prov in fx.PROVIDERS:
        web.fault(prov, list(fx.METHODS), "error")
    assert_status(world.alice.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
    after = settle(d)
    assert after["state"] == "failed"
    assert after["fields"] == before["fields"]
    assert after["researched_at"] == before["researched_at"]


def test_p08_rendered_text_is_used(world, build, corpus):
    """R-04,R-05: fields planted on rendered pages come out as the browser text says."""
    stale = [(d, s) for d in domains(corpus) for s in corpus.key[d]["supports"] if s.get("static")]
    browser_only = [(p.company, p.url) for p in corpus.companies_pages()] if hasattr(
        corpus, "companies_pages") else []
    bad = []
    seen = 0
    for d in domains(corpus):
        pages = [p for p in corpus.companies[d].pages if p.browser_only]
        if not pages:
            continue
        seen += 1
        body = build(d)
        for p in pages:
            for s in (x for x in corpus.key[d]["supports"] if x["url"] == p.url):
                cands = body["fields"][s["field"]]["candidates"]
                has = any(c["url"] == p.url and c["value"] == s["value"] for c in cands)
                if s.get("static") and has:
                    bad.append(("stale value from extract text", d, p.url, s["value"]))
                if not s.get("static") and corpus.page(p.url) and not has and p.searchable:
                    bad.append(("browser-text value missing", d, p.url, s["value"]))
    if not seen:
        pytest.skip("corpus has no browser-only page (sample corpus); F-20 uncovered here")
    assert not bad, bad


def test_p10_existing_dossier_no_build(world, build, corpus, web):
    """R-28 API side: POST of an existing domain (other spelling) is 200, no provider call."""
    d = domains(corpus)[0]
    build(d)
    web.reset()
    r = world.bob.post("/dossiers", json={"domain": "WWW." + d.upper() + "."},
                       idempotency_key=new_key())
    assert r.status_code == 200 and r.json()["domain"] == d
    assert web.log() == []


def test_p11_export_import_roundtrip_keeps_candidates(world, build, corpus, base_url):
    """R-49."""
    d = domains(corpus)[0]
    before = build(d)
    exp = httpx.get(f"{base_url}/_test/export", timeout=10)
    assert exp.status_code == 200
    world.alice.post("/dossiers", json={"domain": domains(corpus)[1]}, idempotency_key=new_key())
    assert httpx.post(f"{base_url}/_test/import", json=exp.json(), timeout=10).status_code == 204
    after = assert_status(world.alice.get(f"/dossiers/{d}"), 200).json()
    assert after == before


def test_p12_import_of_stage1_export(world, corpus, previous_api, base_url, web):
    """R-43,R-44,R-45,R-46: upgrade from stage 1."""
    prev = previous_api
    httpx.post(f"{prev.base_url}/_test/reset", json=fx.fixture(), timeout=RESET_TIMEOUT)
    web.reset()
    tok = assert_status(prev.post("/auth/login", token=None, json={
        "email": fx.ALICE["email"], "password": fx.ALICE["password"]}), 200).json()["token"]
    prev.token = tok
    d1 = domains(corpus)[0]
    key = new_key()
    assert_status(prev.post("/dossiers", json={"domain": d1}, idempotency_key=key), 202)
    b = wait_done(prev, d1)
    assert b["state"] == "ready"
    exp = httpx.get(f"{prev.base_url}/_test/export", timeout=10).json()
    web.reset()
    assert httpx.post(f"{base_url}/_test/import", json=exp, timeout=10).status_code == 204
    assert web.log() == [], "import made provider calls"
    cur = Api(base_url, token=tok)
    body = assert_status(cur.get(f"/dossiers/{d1}"), 200).json()
    assert body["researched_at"] == b["researched_at"] and body["spent_units"] == b["spent_units"]
    lst = assert_status(cur.get("/dossiers"), 200).json()["dossiers"]
    assert any(x["domain"] == d1 for x in lst)
    for f in fx.FIELDS:
        fld = body["fields"][f]
        fx.assert_candidates(f, fld, imported=True)
        assert fld["value"] == b["fields"][f]["value"] or fld["candidates"], (f, fld)
        for c in fld["candidates"]:
            assert fx.instant(c["retrieved_at"]) == fx.instant(b["researched_at"])
            assert c["kind"] is None or c["kind"] in dw.KINDS
    rep = cur.post("/dossiers", json={"domain": d1}, idempotency_key=key)
    assert rep.status_code == 200
    assert_status(cur.post(f"/dossiers/{d1}/refresh", idempotency_key=new_key()), 202)
    nb = wait_done(cur, d1)
    assert nb["state"] == "ready"
    assert all(c["kind"] is not None for f in fx.FIELDS for c in nb["fields"][f]["candidates"])
    cur.close()
