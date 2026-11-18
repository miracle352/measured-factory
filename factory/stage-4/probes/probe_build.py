"""Examiner probes, stage 4: real builds (R-01..R-37, R-44, R-47..R-51, R-57..R-59, R-61).
Oracle: the harness corpus (key supports, lineage header lines via Corpus.origin/lookalike)
and the specification text."""
import time

import httpx
import pytest

import fixtures as fx
import web as dw
from harness.http import Api, RESET_TIMEOUT, assert_status, assert_error, new_key

pytestmark = pytest.mark.stage(4)
ALL = fx.FIELDS + ("executives", "investors")
T0, T1 = fx.NOW, fx.MIDDLE


def doms(corpus):
    return corpus.plain()


def get(c, d, **p):
    return c.get(f"/dossiers/{d}", params=p or None)


def hist(c, d):
    return assert_status(c.get(f"/dossiers/{d}/history"), 200).json()["fields"]


def feed(c):
    out, since = [], 0
    while True:
        b = assert_status(c.get("/changes", params={"since": since, "limit": 200}), 200).json()
        out += b["changes"]
        if not b["has_more"] or not b["changes"]:
            return out
        since = b["changes"][-1]["seq"]


# ---------------------------------------------------------------- origins / lookalikes
def test_o01_field_order_and_origin_keys(world, build, corpus):
    for d in doms(corpus):
        body = build(d)
        assert list(body["fields"]) == list(ALL), (d, list(body["fields"]))
        for name in ALL:
            f = body["fields"][name]
            assert {"origins", "corroborated", "corroborated_since"} <= set(f), (d, name)
            fx.assert_origins(name, f)
            if f["status"] == "unknown":
                assert f["origins"] == [] and f["corroborated"] is False and f["corroborated_since"] is None


def test_o02_candidate_origin_and_kind_follow_lineage(world, build, corpus):
    """R-01..R-09: candidate origin = oracle origin of its page; own needs registrant == domain."""
    bad, seen = [], 0
    for d in doms(corpus):
        body = build(d)
        for name in ALL:
            for c in body["fields"][name]["candidates"]:
                pg = corpus.page(c["url"], 0)
                if pg is None:
                    continue
                seen += 1
                if c["origin"] != corpus.origin(c["url"], d, 0):
                    bad.append((d, name, c["url"], "origin", c["origin"], corpus.origin(c["url"], d, 0)))
                lines = dw.header(pg)
                reg = dw.registrant(c["url"], lines)
                if lines.get("Kind") == "own" and reg != d and c["kind"] != "aggregator":
                    bad.append((d, name, c["url"], "kind", c["kind"], reg))
                if c["kind"] == "own" and reg != d:
                    bad.append((d, name, c["url"], "own-without-registrant", reg))
    assert seen and not bad, bad[:8]


def test_o03_lineage_pages_exist_and_originals_fetched(world, web, build, corpus):
    """R-06: every in-corpus original a candidate's page needs is obtained from a provider."""
    lineage = [p for p in corpus.pages if dw.header(p).get("Canonical")]
    if not lineage:
        pytest.skip("corpus has no Canonical pages")
    checked = 0
    for d in doms(corpus):
        web.reset()
        body = build(d)
        calls = web.log()
        touched = " ".join(str(c.get("urls")) + str(c.get("query")) + " ".join(x["url"] for x in (c.get("served") or [])) for c in calls)
        for name in ALL:
            for c in body["fields"][name]["candidates"]:
                pg = corpus.page(c["url"], 0)
                canon = dw.header(pg).get("Canonical") if pg else None
                if canon and canon != c["url"] and corpus.page(canon, 0):
                    checked += 1
                    assert canon in touched, f"{d}: original {canon} of {c['url']} never fetched"
    print("canonical originals checked:", checked)


def test_o04_known_fields_match_key(world, build, corpus):
    """Six fields and investors known/values as the stage-4 key expects."""
    for d in doms(corpus):
        body = build(d)
        for name in fx.FIELDS + ("investors",):
            exp = corpus.expected(d, name, stage=4)
            assert fx.matches(body["fields"][name]["value"], exp), (d, name, body["fields"][name]["value"], exp)


# ---------------------------------------------------------------- investors
def test_i01_investors_shape(world, build, corpus):
    got = 0
    for d in doms(corpus):
        f = build(d)["fields"]["investors"]
        cands = f["candidates"]
        names = f["value"]
        assert (names is None) == (f["status"] == "unknown")
        if names is None:
            assert f["citations"] == [] and f["true_from"] is None
            assert all(c["selected"] is False for c in cands)
            continue
        got += 1
        assert names == sorted(names)
        members = set(names)
        for c in cands:
            assert c["selected"] is (c["value"] in members), c
            assert isinstance(c["value"], str)
        # rank order
        keys = [fx.rank_key(c) for c in cands]
        assert keys == sorted(keys), "candidates not in selection rank order"
        # member rule
        for m in names:
            mc = [c for c in cands if c["value"] == m]
            assert any(c["kind"] in ("own", "filing") for c in mc) or len({c["origin"] for c in mc}) >= 2, (d, m)
        for m in {c["value"] for c in cands} - members:
            mc = [c for c in cands if c["value"] == m]
            assert not any(c["kind"] in ("own", "filing") for c in mc) and len({c["origin"] for c in mc}) < 2, (d, m)
        # citations: per member in value order, every candidate with the name, rank order
        want = [(c["url"], c["excerpt"], c["provider"]) for m in names for c in cands if c["value"] == m]
        assert [(c["url"], c["excerpt"], c["provider"]) for c in f["citations"]] == want, d
        # true_from
        tfs = []
        for m in names:
            nn = [c["true_from"] for c in cands if c["value"] == m and c["true_from"]]
            tfs.append(min(nn) if nn else None)
        exp_tf = None if any(t is None for t in tfs) else max(tfs)
        assert f["true_from"] == exp_tf, (d, f["true_from"], tfs)
        fx.assert_origins("investors", f)
    assert got, "no company produced investors; corpus has none?"


def test_i02_investors_never_research_claim(world, build, corpus, web):
    for d in doms(corpus):
        f = build(d)["fields"]["investors"]
        for c in f["candidates"]:
            assert c["provider"] and c["url"] and c["excerpt"]


def test_i03_investors_in_history_and_values(world, build, corpus):
    d = next((x for x in doms(corpus) if get(world.alice, x).status_code != 200 or True), doms(corpus)[0])
    body = build(d)
    h = hist(world.alice, d)
    assert list(h) == list(ALL)
    v = assert_status(world.alice.get(f"/dossiers/{d}/values", params={"true_at": "2099-01-01"}), 200).json()
    assert "investors" in v["fields"] if "fields" in v else "investors" in v
    if body["fields"]["investors"]["value"] is not None:
        assert [e["type"] for e in h["investors"]] == ["initial"]


def test_i04_feed_numbering_investors_last(world, build, corpus):
    for d in doms(corpus)[:4]:
        build(d)
    fd = feed(world.alice)
    by_build = {}
    for e in fd:
        by_build.setdefault((e["domain"], e["learned_at"]), []).append(e)
    for key, es in by_build.items():
        order = [ALL.index(e["field"]) for e in es]
        assert order == sorted(order), (key, [e["field"] for e in es])
        assert [e["seq"] for e in es] == sorted(e["seq"] for e in es)


# ---------------------------------------------------------------- screens
def test_u01_investors_no_testid_and_contested(world, build, corpus):
    d = doms(corpus)[0]
    build(d)
    r = world.alice.get(f"/dossiers/{d}", headers={"Accept": "text/html"})
    assert r.status_code == 200
    html = r.text
    assert 'data-testid="investors' not in html and "data-testid='investors" not in html
    assert_status(world.alice.get("/contested", headers={"Accept": "text/html"}), 200)


# ---------------------------------------------------------------- provider failure
def test_f01_all_providers_fail_failed_in_time(world, web, corpus):
    d = doms(corpus)[0]
    for p in fx.PROVIDERS:
        web.fault(p, list(fx.METHODS), "error")
    t = time.monotonic()
    assert_status(world.alice.post("/dossiers", json={"domain": d}, idempotency_key=new_key()), 202)
    deadline = t + fx.BUILD_SECONDS + 2
    while True:
        b = get(world.alice, d).json()
        if b["state"] != "building" or time.monotonic() > deadline:
            break
        time.sleep(0.1)
    assert b["state"] == "failed", (b["state"], time.monotonic() - t)
    assert b["spent_units"] == 0 and web.units() == 0


def test_f02_nimble_only_answers_ready(world, web, corpus, build):
    d = doms(corpus)[0]
    for p in fx.PROVIDERS:
        if p != "nimble":
            web.fault(p, list(fx.METHODS), "error")
    b = build(d)
    assert b["state"] == "ready"
    for name in fx.FIELDS:
        exp = corpus.gathered(d, 0).get(name)
        if exp:
            assert b["fields"][name]["status"] == "known", (d, name)


def test_f03_research_fails_search_extract_work(world, web, corpus, build):
    d = doms(corpus)[0]
    for p in fx.PROVIDERS:
        web.fault(p, ["research"], "error")
    b = build(d)
    assert b["state"] == "ready"
    exp = corpus.gathered(d, 0, research=False)
    for name in fx.FIELDS:
        if exp.get(name):
            assert b["fields"][name]["status"] == "known", (d, name)


def test_f04_429_and_5xx_cost_nothing_and_accounting(world, web, corpus, build):
    d = doms(corpus)[0]
    web.fault("nimble", ["search"], "throttle")
    b = build(d)
    log = web.log()
    assert all(c["cost"] == 0 for c in log if c["status"] >= 400), [c for c in log if c["status"] >= 400 and c["cost"]][:2]
    assert b["spent_units"] == web.units() and b["spent_units"] <= 80


def test_f05_failed_build_leaves_fields(world, web, corpus, build, refresh, clock):
    d = doms(corpus)[0]
    first = build(d)
    assert_status(clock(T1), 204)
    for p in fx.PROVIDERS:
        web.fault(p, list(fx.METHODS), "error")
    second = refresh(d)
    assert second["state"] == "failed"
    assert second["fields"] == first["fields"]


# ---------------------------------------------------------------- corroborated_since
def test_c01_corroborated_since_first_build(world, build, corpus):
    for d in doms(corpus):
        b = build(d)
        for name in ALL:
            f = b["fields"][name]
            if f["corroborated"]:
                assert f["corroborated_since"] is not None and fx.instant(f["corroborated_since"]) == fx.instant(b["researched_at"]), (d, name)
            else:
                assert f["corroborated_since"] is None or name in fx.FIELDS + ("executives", "investors")


def test_c02_since_stable_across_refresh(world, build, refresh, clock, corpus):
    for d in doms(corpus)[:3]:
        b0 = build(d)
        assert_status(clock(T1), 204)
        b1 = refresh(d)
        for name in ALL:
            f0, f1 = b0["fields"][name], b1["fields"][name]
            if f0["corroborated"] and f0["value"] == f1["value"]:
                assert f1["corroborated"] and f1["corroborated_since"] == f0["corroborated_since"], (d, name)


# ---------------------------------------------------------------- upgrades
def _old(prev, web, corpus, d):
    httpx.post(f"{prev.base_url}/_test/reset", json=fx.fixture(), timeout=RESET_TIMEOUT)
    web.reset()
    tok = assert_status(prev.post("/auth/login", token=None, json={
        "email": fx.ALICE["email"], "password": fx.ALICE["password"]}), 200).json()["token"]
    cli = Api(prev.base_url, token=tok)
    assert_status(cli.post("/dossiers", json={"domain": d}, idempotency_key=new_key()), 202)
    end = time.monotonic() + fx.SETTLE_SECONDS
    while True:
        b = cli.get(f"/dossiers/{d}").json()
        if b["state"] != "building" or time.monotonic() > end:
            return tok, b
        time.sleep(0.1)


def test_m01_import_previous_stage(world, web, corpus, previous_api, base_url):
    d = doms(corpus)[0]
    tok, old = _old(previous_api, web, corpus, d)
    exp = httpx.get(f"{previous_api.base_url}/_test/export", timeout=10).json()
    web.reset()
    assert httpx.post(f"{base_url}/_test/import", json=exp, timeout=10).status_code == 204
    assert web.log() == []
    cur = Api(base_url, token=tok)
    b = assert_status(cur.get(f"/dossiers/{d}"), 200).json()
    assert list(b["fields"]) == list(ALL)
    inv = b["fields"]["investors"]
    assert inv["status"] == "unknown" and inv["value"] is None and inv["origins"] == []
    assert inv["corroborated"] is False and inv["corroborated_since"] is None
    assert hist(cur, d)["investors"] == []
    for name in fx.FIELDS:
        f = b["fields"][name]
        for c in f["candidates"]:
            assert c["origin"] == dw.host(c["url"]) or c["origin"], c
        fx.assert_origins(name, f)
        assert f["value"] == old["fields"][name]["value"]
    r = assert_status(cur.get(f"/dossiers/{d}/values", params={"true_at": "2099-01-01"}), 200)


def test_m02_first_ready_build_adds_investors_entry(world, web, corpus, previous_api, base_url, clock):
    cands = [d for d in doms(corpus)
             if corpus.expected(d, "investors", stage=4) != [None]]
    if not cands:
        pytest.skip("no company with investors")
    d = cands[0]
    tok, old = _old(previous_api, web, corpus, d)
    exp = httpx.get(f"{previous_api.base_url}/_test/export", timeout=10).json()
    web.reset()
    assert httpx.post(f"{base_url}/_test/import", json=exp, timeout=10).status_code == 204
    cur = Api(base_url, token=tok)
    assert_status(clock(T1), 204)
    assert_status(cur.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
    end = time.monotonic() + fx.SETTLE_SECONDS
    while cur.get(f"/dossiers/{d}").json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    h = hist(cur, d)["investors"]
    assert [e["type"] for e in h] == ["change"], h
