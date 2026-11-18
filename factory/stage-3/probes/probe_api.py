"""Examiner probes, stage 3 (API). Written from the stage-3 specification only.

The oracle is the corpus key (epochs 0/1) plus each page's header, ranked by the stage-2
selection rule as I read it; page-version logic follows "GET /dossiers/{domain}/values".
"""
import json
import os
import threading
import time
from datetime import date, datetime, timedelta

import httpx
import pytest

import fixtures as fx
import web as dw
from harness.http import Api, RESET_TIMEOUT, assert_status, new_key

pytestmark = pytest.mark.stage(3)
T0, T1, T2 = fx.NOW, fx.MIDDLE, fx.LATER
ALL = fx.FIELDS + ("executives",)
AUTH = {"own": 0, "filing": 0, "news": 1, "aggregator": 2}


# ---------------------------------------------------------------- helpers
def page_kind(corpus, url, domain, epoch):
    pg = corpus.page(url, epoch)
    k = dw.header(pg).get("Kind") if pg else None
    if k in dw.KINDS:
        return k
    return "own" if dw.host(url) == domain else "aggregator"


def domains(corpus):
    return corpus.plain()


def movers(corpus):
    return [d for d in domains(corpus) if corpus.moved(d)]


def get(client, d, **params):
    return client.get(f"/dossiers/{d}", params=params or None)


def hist(client, d):
    return assert_status(client.get(f"/dossiers/{d}/history"), 200).json()["fields"]


def feed(client, since=0):
    out = []
    while True:
        b = assert_status(client.get("/changes", params={"since": since, "limit": 200}), 200).json()
        out += b["changes"]
        if not b["has_more"] or not b["changes"]:
            return out
        since = b["changes"][-1]["seq"]


def at(clock, ts):
    assert_status(clock(ts), 204)


def two_builds(world, web, clock, build, refresh, d, epoch1=True):
    """build at T0 (epoch 0); refresh at T1 (epoch 1 when asked). Returns (b0, b1)."""
    b0 = build(d)
    at(clock, T1)
    if epoch1:
        web.epoch(1)
    b1 = refresh(d)
    return b0, b1


def sel(body, name):
    return body["fields"][name]


def titles_selected(field):
    """{title: selected candidate} for an executives field."""
    out = {}
    for c in field["candidates"]:
        if c["selected"]:
            out[c["title"]] = c
    return out


def sel_state(field, name):
    """Comparable selected value: (value, true_from) per spec 'differs' notions."""
    if name == "executives":
        v = field["value"]
        sc = titles_selected(field)
        return {m["title"]: (m["name"], sc[m["title"]]["true_from"]) for m in (v or [])}
    return (field["value"], field["true_from"])


def expect_type(old, new, name):
    """Entry type per spec, or None when nothing is added."""
    if name == "executives":
        diff = [t for t in set(old) | set(new)
                if (t in old) != (t in new) or (t in old and old[t][0] != new[t][0])]
        if not diff:
            return None
        ok = all(t in old and t in new and old[t][1] and new[t][1]
                 and new[t][1] <= old[t][1] for t in diff)
        return "correction" if ok else "change"
    (ov, ot), (nv, nt) = old, new
    if fx.same_value(ov, nv) if ov is not None and nv is not None else ov == nv:
        return None
    if ov is None or nv is None or ot is None or nt is None:
        return "change"
    return "correction" if nt <= ot else "change"


# ------------------------------------------------------------ two times
def test_p01_candidate_true_from(world, build, corpus):
    """Two times: true_from = Effective, else UTC date of Published, else null."""
    bad = []
    for d in domains(corpus):
        body = build(d)
        for f in ALL:
            for c in body["fields"][f]["candidates"]:
                if "true_from" not in c or "learned_at" not in c:
                    bad.append((d, f, "missing keys"))
                    continue
                e = corpus.true_from(c["url"], 0)
                if c["true_from"] != e:
                    bad.append((d, f, c["url"], c["true_from"], e))
    assert not bad, bad[:8]


def test_p02_learned_at_stays_retrieved_moves(world, web, clock, build, refresh, corpus):
    """Candidate learned_at = first build that gathered it; retrieved_at = latest build."""
    d = domains(corpus)[0]
    b0 = build(d)
    at(clock, T1)
    b1 = refresh(d)  # same epoch: same candidates
    for f in ALL:
        old = {(c.get("title"), json.dumps(c["value"]), c["url"], c["provider"]): c
               for c in b0["fields"][f]["candidates"]}
        for c in b1["fields"][f]["candidates"]:
            k = (c.get("title"), json.dumps(c["value"]), c["url"], c["provider"])
            assert fx.instant(c["retrieved_at"]) == fx.instant(T1), c
            want = T0 if k in old else T1
            assert fx.instant(c["learned_at"]) == fx.instant(want), (f, c, k in old)


def test_p03_field_times_and_unknown(world, build, corpus):
    """Field true_from/learned_at: selected candidate's / build time; null when unknown."""
    for d in domains(corpus):
        body = build(d)
        for f in fx.FIELDS:
            fld = body["fields"][f]
            if fld["value"] is None:
                assert fld["true_from"] is None and fld["learned_at"] is None, (d, f, fld)
            else:
                s = fld["candidates"][0]
                assert fld["true_from"] == s["true_from"], (d, f)
                assert fx.instant(fld["learned_at"]) == fx.instant(T0), (d, f, fld)
        ex = body["fields"]["executives"]
        if ex["value"] is None:
            assert ex["true_from"] is None and ex["learned_at"] is None


def test_p04_selected_learned_at_unchanged_when_same_value(world, web, clock, build, refresh,
                                                           corpus):
    """learned_at of a selected value = build that made it selected (not later same-value builds)."""
    d = domains(corpus)[0]
    build(d)
    at(clock, T1)
    b1 = refresh(d)
    for f in fx.FIELDS:
        if b1["fields"][f]["value"] is not None:
            assert fx.instant(b1["fields"][f]["learned_at"]) == fx.instant(T0), f


# ------------------------------------------------------------- executives
def test_p05_executives_field_shape(world, build, corpus):
    got_any = False
    for d in domains(corpus):
        body = build(d)
        assert list(body["fields"]) == list(ALL), list(body["fields"])
        ex = body["fields"]["executives"]
        exp = corpus.expected(d, "executives", stage=3, epoch=0)
        assert fx.matches(ex["value"], exp), (d, ex["value"], exp)
        cands = ex["candidates"]
        order = {t: i for i, t in enumerate(fx.TITLES)}
        assert [order[c["title"]] for c in cands] == sorted(order[c["title"]] for c in cands), d
        if ex["value"] is None:
            assert ex["status"] == "unknown" and ex["citations"] == [] and not cands, ex
            assert ex["true_from"] is None and ex["learned_at"] is None
            continue
        got_any = True
        fx.assert_field("executives", ex, 3)
        by = {}
        for c in cands:
            by.setdefault(c["title"], []).append(c)
        for t, lst in by.items():
            assert [c["selected"] for c in lst] == [True] + [False] * (len(lst) - 1), (d, t)
        sc = titles_selected(ex)
        assert [m["title"] for m in ex["value"]] == [t for t in fx.TITLES if t in sc]
        for m in ex["value"]:
            assert sc[m["title"]]["value"] == m["name"]
        cites = []
        for m in ex["value"]:
            cites += [{k: c[k] for k in ("url", "excerpt", "provider")} for c in by[m["title"]]
                      if c["value"] == m["name"]]
        assert ex["citations"] == cites, (d, ex["citations"], cites)
        contested = any(len({c["value"] for c in lst}) > 1 for lst in by.values())
        assert ex["status"] == ("contested" if contested else "known"), (d, ex["status"])
        tfs = [sc[m["title"]]["true_from"] for m in ex["value"]]
        want = None if any(t is None for t in tfs) else max(tfs)
        assert ex["true_from"] == want, (d, ex["true_from"], tfs)
    assert got_any, "corpus has no company with executives"


def test_p06_research_asks_six_fields_only(world, build, corpus, web):
    d = domains(corpus)[0]
    web.reset()
    build(d)
    for call in web.log():
        if "research" in str(call.get("method", "")):
            blob = json.dumps(call)
            assert not any(t in blob for t in ('"executives"', '"cfo"', '"coo"', '"cto"')), blob[:400]


# -------------------------------------------------------------------- as_of
def test_p10_as_of_returns_earlier_build(world, web, clock, build, refresh, corpus):
    m = movers(corpus)
    d = (m or domains(corpus))[0]
    b0, b1 = two_builds(world, web, clock, build, refresh, d)
    c = world.alice
    r0 = assert_status(get(c, d, as_of=T0), 200).json()
    assert r0["state"] == "ready" and r0["fields"] == b0["fields"]
    assert r0["researched_at"] == b0["researched_at"]
    assert r0["spent_units"] == b0["spent_units"]
    mid = assert_status(get(c, d, as_of="2026-03-01T20:00:00+00:00"), 200).json()
    assert mid["fields"] == b0["fields"] and mid["spent_units"] == b0["spent_units"]
    r1 = assert_status(get(c, d, as_of=T1), 200).json()
    assert r1["fields"] == b1["fields"] and r1["spent_units"] == b1["spent_units"]
    assert r1["researched_at"] == b1["researched_at"]
    far = assert_status(get(c, d, as_of="2099-01-01T00:00:00Z"), 200).json()
    assert far["fields"] == b1["fields"]
    cur = assert_status(get(c, d), 200).json()
    assert cur == b1


def test_p11_failed_build_never_a_snapshot_but_counts(world, web, clock, build, refresh, corpus):
    d = domains(corpus)[0]
    b0 = build(d)
    at(clock, T1)
    for prov in fx.PROVIDERS:
        web.fault(prov, list(fx.METHODS), "error")
    bf = refresh(d)
    assert bf["state"] == "failed", bf["state"]
    web.normal()
    r = assert_status(get(world.alice, d, as_of=T1), 200).json()
    assert r["state"] == "ready" and r["researched_at"] == b0["researched_at"]
    assert r["fields"] == b0["fields"]
    assert r["spent_units"] == bf["spent_units"]


def test_p12_as_of_times_use_no_later_history(world, web, clock, build, refresh, corpus):
    m = movers(corpus)
    if not m:
        pytest.skip("no mover")
    d = m[0]
    b0, b1 = two_builds(world, web, clock, build, refresh, d)
    r0 = assert_status(get(world.alice, d, as_of=T0), 200).json()
    for f in ALL:
        fld = r0["fields"][f]
        if fld["value"] is None:
            assert fld["true_from"] is None and fld["learned_at"] is None
        else:
            assert fx.instant(fld["learned_at"]) == fx.instant(T0), (f, fld)


def test_p14_equal_times_last_build_wins(world, web, clock, build, refresh, corpus):
    m = movers(corpus)
    if not m:
        pytest.skip("no mover")
    d = m[0]
    b0 = build(d)
    web.epoch(1)  # clock not advanced
    b1 = refresh(d)
    assert fx.instant(b1["researched_at"]) == fx.instant(T0)
    r = assert_status(get(world.alice, d, as_of=T0), 200).json()
    assert r["fields"] == b1["fields"] and r["fields"] != b0["fields"]
    r = assert_status(get(world.alice, d, as_of="2026-03-01T11:00:00+02:00"), 200).json()
    assert r["fields"] == b1["fields"]
    assert r["spent_units"] == b1["spent_units"]


@pytest.mark.parametrize("bad", ["2026-03-01", "2026-03-01T09:00:00", "garbage", "",
                                 "2026-13-01T00:00:00+00:00", "1772355600",
                                 "2026-03-01T09:00:00%2000:00"])
def test_p15_as_of_invalid_is_422(world, build, corpus, bad):
    d = domains(corpus)[0]
    build(d)
    r = get(world.alice, d, as_of=bad)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed", \
        (bad, r.status_code, r.text[:200])


def test_p16_as_of_404s(world, build, corpus):
    d = domains(corpus)[0]
    build(d)
    r = get(world.alice, d, as_of="2026-02-28T23:59:59+00:00")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = get(world.alice, "nothere.test", as_of=T0)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = get(world.alice, "WWW.NoThere.test.", as_of=T0)
    assert r.status_code == 404


def test_p17_as_of_before_first_ready_build_of_failed_first_build(world, web, corpus):
    d = domains(corpus)[0]
    for prov in fx.PROVIDERS:
        web.fault(prov, list(fx.METHODS), "error")
    assert_status(world.alice.post("/dossiers", json={"domain": d}, idempotency_key=new_key()), 202)
    end = time.monotonic() + 30
    while get(world.alice, d).json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    assert get(world.alice, d).json()["state"] == "failed"
    assert get(world.alice, d, as_of="2099-01-01T00:00:00Z").status_code == 404
    web.normal()
    h = hist(world.alice, d)
    assert all(h[f] == [] for f in ALL), h
    v = get(world.alice, d)
    assert v.status_code == 200


# ----------------------------------------------------------------- /values
def versions_oracle(builds, d, f, true_at, corpus):
    """builds: list of (epoch, snapshot body, served urls) in build order. Returns
    list of candidates at true_at per the page-version rules (f may be a title)."""
    per_url = {}  # url -> list of dict(from,end,cands)
    for epoch, body, urls in builds:
        fld = body["fields"]["executives"] if f in fx.TITLES else body["fields"][f]
        by_url = {}
        for c in fld["candidates"]:
            if f in fx.TITLES and c["title"] != f:
                continue
            by_url.setdefault(c["url"], []).append(c)
        # versions are per URL gathered (all fields): use every candidate url of this body
        allc = [c for n in ALL for c in body["fields"][n]["candidates"]]
        tfs = {c["url"]: c["true_from"] for c in allc}
        for u in urls:
            if u not in tfs and corpus.page(u, epoch):
                tfs[u] = corpus.true_from(u, epoch)
        for u, tf in tfs.items():
            lst = per_url.setdefault(u, [])
            new = {"from": tf, "end": None, "cands": by_url.get(u, [])}
            if tf is None:
                lst.clear()
            else:
                lst[:] = [v for v in lst if not (v["from"] is not None and v["from"] >= tf)]
                lst[:] = [v for v in lst if v["from"] is not None]
                if lst:
                    lst[-1]["end"] = tf
            lst.append(new)
    out = []
    for lst in per_url.values():
        for v in lst:
            if v["from"] is not None and v["from"] <= true_at and (v["end"] is None or true_at < v["end"]):
                out += v["cands"]
    return out


def choose(cands):
    if not cands:
        return None
    return sorted(cands, key=fx.rank_key)[0]


def check_values(client, d, true_at, as_of, builds, corpus):
    r = assert_status(client.get(f"/dossiers/{d}/values",
                                 params={"true_at": true_at, "as_of": as_of}), 200).json()
    assert r["domain"] == d and r["true_at"] == true_at
    assert fx.instant(r["as_of"]) == fx.instant(as_of)
    assert list(r["fields"]) == list(ALL), list(r["fields"])
    bad = []
    for f in fx.FIELDS:
        got = r["fields"][f]
        cs = versions_oracle(builds, d, f, true_at, corpus)
        best = choose(cs)
        if best is None:
            if (got["value"], got["true_from"], got["citations"]) != (None, None, []):
                bad.append((f, "expected empty", got))
            continue
        want_c = [{k: c[k] for k in ("url", "excerpt", "provider")} for c in sorted(cs, key=fx.rank_key)
                  if fx.same_value(c["value"], best["value"])]
        if not (fx.same_value(got["value"], best["value"]) and got["true_from"] == best["true_from"]
                and got["citations"] == want_c):
            bad.append((f, got, best["value"], best["true_from"], want_c))
    ex = r["fields"]["executives"]
    mem = []
    for t in fx.TITLES:
        b = choose(versions_oracle(builds, d, t, true_at, corpus))
        if b:
            mem.append({"title": t, "name": b["value"]})
    if (ex["value"] or []) != mem:
        bad.append(("executives", ex["value"], mem))
    if not mem and (ex["value"] is not None or ex["citations"] != [] or ex["true_from"] is not None):
        bad.append(("executives empty", ex))
    assert not bad, bad[:5]
    return r


def gather(world, web, corpus, d, epochs, clock, times):
    """Build d once per (epoch,time); returns [(epoch, body, served urls)]."""
    builds = []
    for i, (e, t) in enumerate(zip(epochs, times)):
        at(clock, t)
        web.reset(e)
        if i == 0:
            assert_status(world.alice.post("/dossiers", json={"domain": d},
                                           idempotency_key=new_key()), 202)
        else:
            assert_status(world.alice.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
        end = time.monotonic() + 30
        while True:
            b = get(world.alice, d).json()
            if b["state"] != "building" or time.monotonic() > end:
                break
            time.sleep(0.1)
        assert b["state"] == "ready"
        urls = {it["url"] for call in web.log() for it in call["served"]}
        builds.append((e, assert_status(get(world.alice, d, as_of=t), 200).json(), urls))
    return builds


def candidate_dates(builds):
    ds = set()
    for _, body, _ in builds:
        for f in ALL:
            for c in body["fields"][f]["candidates"]:
                if c["true_from"]:
                    ds.add(c["true_from"])
    out = set()
    for s in ds:
        dt = date.fromisoformat(s)
        out |= {s, (dt - timedelta(days=1)).isoformat(), (dt + timedelta(days=1)).isoformat()}
    out |= {"1900-01-01", "2099-12-31"}
    return sorted(out)


def test_p20_values_single_build_each_date(world, web, clock, corpus):
    d = domains(corpus)[0]
    builds = gather(world, web, corpus, d, [0], clock, [T0])
    for ta in candidate_dates(builds):
        check_values(world.alice, d, ta, T0, builds, corpus)


def test_p21_values_validation_and_404(world, build, corpus):
    d = domains(corpus)[0]
    build(d)
    c = world.alice
    for params in [{}, {"true_at": "2025-6-1"}, {"true_at": "2025-13-40"},
                   {"true_at": "2025-06-01T00:00:00Z"}, {"true_at": "abc"}, {"true_at": ""},
                   {"true_at": "2025-02-30"},
                   {"true_at": "2025-06-01", "as_of": "2026-03-01"},
                   {"true_at": "2025-06-01", "as_of": "2026-03-01T09:00:00"},
                   {"true_at": "2025-06-01", "as_of": ""}]:
        r = c.get(f"/dossiers/{d}/values", params=params)
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed", \
            (params, r.status_code, r.text[:120])
    r = c.get("/dossiers/nothere.test/values", params={"true_at": "2025-06-01"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = c.get(f"/dossiers/{d}/values", params={"true_at": "2025-06-01",
                                                "as_of": "2026-02-01T00:00:00+00:00"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = world.alice.get(f"/dossiers/{d}/values", params={"true_at": "2025-06-01"})
    assert r.status_code == 200
    assert api_no_auth(world, d).status_code == 401


def api_no_auth(world, d):
    return httpx.get(f"{world.alice.base_url}/dossiers/{d}/values?true_at=2025-06-01", timeout=5)


def test_p22_values_before_everything_is_empty(world, build, corpus):
    d = domains(corpus)[0]
    build(d)
    r = assert_status(world.alice.get(f"/dossiers/{d}/values", params={"true_at": "1000-01-01"}), 200).json()
    assert list(r["fields"]) == list(ALL)
    for f in ALL:
        assert (r["fields"][f]["value"], r["fields"][f]["true_from"],
                r["fields"][f]["citations"]) == (None, None, []), f


def test_p23_values_as_of_defaults_to_now(world, build, clock, corpus):
    d = domains(corpus)[0]
    build(d)
    at(clock, "2026-06-01T12:00:00+00:00")
    r = assert_status(world.alice.get(f"/dossiers/{d}/values", params={"true_at": "2099-01-01"}), 200).json()
    assert fx.instant(r["as_of"]) == fx.instant("2026-06-01T12:00:00+00:00")
    cur = get(world.alice, d).json()
    for f in fx.FIELDS:
        cs = [c for c in cur["fields"][f]["candidates"] if c["true_from"]]
        b = choose(cs)
        assert (r["fields"][f]["value"] if b else None) == (b["value"] if b else None), f


def test_p24_values_two_builds_versions(world, web, clock, corpus):
    m = movers(corpus)
    if not m:
        pytest.skip("no mover")
    d = m[0]
    builds = gather(world, web, corpus, d, [0, 1], clock, [T0, T1])
    for ta in candidate_dates(builds):
        for as_of in (T0, T1):
            check_values(world.alice, d, ta, as_of, builds[: 1 if as_of == T0 else 2], corpus)


def test_p25_values_three_builds_versions(world, web, clock, corpus):
    m = movers(corpus)
    if not m:
        pytest.skip("no mover")
    d = m[0]
    builds = gather(world, web, corpus, d, [0, 1, 0], clock, [T0, T1, T2])
    for ta in candidate_dates(builds):
        check_values(world.alice, d, ta, T2, builds, corpus)
        check_values(world.alice, d, ta, T1, builds[:2], corpus)


# ------------------------------------------------- history & changes
def run_two(world, web, clock, build, refresh, d):
    b0, b1 = two_builds(world, web, clock, build, refresh, d)
    return b0, b1


def test_p30_history_and_feed_match_selected_changes(world, web, clock, build, refresh, corpus):
    bad = []
    expected_feed = []
    all_b = {}
    for d in movers(corpus) or domains(corpus)[:1]:
        all_b[d] = build(d)
    at(clock, T1)
    web.epoch(1)
    for d in all_b:
        b1 = refresh(d)
        b0 = all_b[d]
        h = hist(world.alice, d)
        assert list(h) == list(ALL), list(h)
        for f in ALL:
            old, new = sel_state(b0["fields"][f], f), sel_state(b1["fields"][f], f)
            t = expect_type(old, new, f)
            n0 = 1 if b0["fields"][f]["value"] is not None else 0
            got = h[f]
            want_len = n0 + (1 if t else 0)
            if len(got) != want_len:
                bad.append((d, f, "len", len(got), want_len, [e["type"] for e in got]))
                continue
            if n0:
                if got[0]["type"] != "initial":
                    bad.append((d, f, "first not initial"))
                if fx.instant(got[0]["learned_at"]) != fx.instant(T0):
                    bad.append((d, f, "initial learned_at"))
            if t:
                e = got[-1]
                if e["type"] != t:
                    bad.append((d, f, "type", e["type"], t))
                if e["value"] is None and e["learned_at"] is None:
                    pass  # spec: learned_at is null for an unknown selected value
                elif e["learned_at"] is None or fx.instant(e["learned_at"]) != fx.instant(T1):
                    bad.append((d, f, "learned_at", e["learned_at"]))
                if e["value"] != b1["fields"][f]["value"]:
                    bad.append((d, f, "value"))
                if e["value"] is None and (e["true_from"] is not None or e["citations"] != []):
                    bad.append((d, f, "null entry shape"))
                if e["value"] is not None and e["true_from"] != b1["fields"][f]["true_from"]:
                    bad.append((d, f, "true_from"))
                expected_feed.append((d, f, t, b0["fields"][f]["value"], b1["fields"][f]["value"]))
    fd = feed(world.alice)
    got_feed = [(e["domain"], e["field"], e["type"], e["from"], e["to"]) for e in fd]
    if sorted(map(json.dumps, got_feed)) != sorted(map(json.dumps, expected_feed)):
        bad.append(("feed", got_feed, expected_feed))
    seqs = [e["seq"] for e in fd]
    assert seqs == sorted(set(seqs)) and all(isinstance(s, int) and s > 0 for s in seqs), seqs
    for e in fd:
        assert fx.instant(e["learned_at"]) == fx.instant(T1)
    assert not bad, bad[:6]


def test_p31_feed_order_within_build_follows_field_order(world, web, clock, build, refresh, corpus):
    d = max(movers(corpus) or domains(corpus), key=lambda x: len(corpus.moved(x)))
    two_builds(world, web, clock, build, refresh, d)
    names = [e["field"] for e in feed(world.alice) if e["domain"] == d]
    assert names == sorted(names, key=ALL.index), names


def test_p32_first_build_initial_no_feed(world, build, corpus):
    d = domains(corpus)[0]
    b = build(d)
    assert feed(world.alice) == []
    h = hist(world.alice, d)
    for f in ALL:
        if b["fields"][f]["value"] is None:
            assert h[f] == [], f
        else:
            assert [e["type"] for e in h[f]] == ["initial"], (f, h[f])
            assert fx.instant(h[f][0]["learned_at"]) == fx.instant(T0)
            assert h[f][0]["true_from"] == b["fields"][f]["true_from"]
            assert h[f][0]["citations"] == b["fields"][f]["citations"]


def test_p34_same_value_adds_nothing(world, web, clock, build, refresh, corpus):
    d = domains(corpus)[0]
    build(d)
    h0 = hist(world.alice, d)
    at(clock, T1)
    refresh(d)
    assert hist(world.alice, d) == h0
    assert feed(world.alice) == []


def test_p35_failed_build_adds_nothing(world, web, clock, build, refresh, corpus):
    m = movers(corpus)
    d = (m or domains(corpus))[0]
    build(d)
    h0 = hist(world.alice, d)
    at(clock, T1)
    web.epoch(1)
    for prov in fx.PROVIDERS:
        web.fault(prov, list(fx.METHODS), "error")
    assert refresh(d)["state"] == "failed"
    web.normal()
    assert hist(world.alice, d) == h0 and feed(world.alice) == []


def test_p36_concurrent_refreshes_one_build_entries_once(world, web, clock, build, corpus):
    ds = (movers(corpus) or domains(corpus))[:3]
    for d in ds:
        build(d)
    at(clock, T1)
    web.epoch(1)
    errs = []

    def go(d):
        try:
            r = world.alice.post(f"/dossiers/{d}/refresh", idempotency_key=new_key())
            if r.status_code != 202:
                errs.append((d, r.status_code))
        except Exception as e:  # noqa
            errs.append((d, repr(e)))
    th = [threading.Thread(target=go, args=(d,)) for d in ds for _ in range(6)]
    [t.start() for t in th]
    [t.join() for t in th]
    assert not errs, errs
    for d in ds:
        end = time.monotonic() + 40
        while get(world.alice, d).json()["state"] == "building" and time.monotonic() < end:
            time.sleep(0.1)
    fd = feed(world.alice)
    keys = [(e["domain"], e["field"]) for e in fd]
    assert len(keys) == len(set(keys)), keys
    assert len({e["seq"] for e in fd}) == len(fd)
    for d in ds:
        for f in corpus.moved(d):
            assert (d, f) in keys, (d, f, keys)


def test_p37_reads_during_build_are_consistent(world, web, clock, build, refresh, corpus):
    d = (movers(corpus) or domains(corpus))[0]
    b0 = build(d)
    at(clock, T1)
    web.epoch(1)
    web.slow(0.6)
    assert_status(world.alice.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
    bad = []
    end = time.monotonic() + 3
    while time.monotonic() < end:
        r = get(world.alice, d, as_of=T0)
        if r.status_code != 200 or r.json()["fields"] != b0["fields"]:
            bad.append(r.status_code)
        cur = get(world.alice, d).json()
        if cur["state"] == "building" and cur["fields"] != b0["fields"]:
            bad.append("building shows new fields")
        if cur["state"] != "building":
            break
    web.normal(("search",))
    assert not bad, bad[:5]


# ---------------------------------------------------- history / changes api
def test_p40_history_seven_fields_and_404(world, build, corpus):
    d = domains(corpus)[0]
    build(d)
    r = assert_status(world.alice.get(f"/dossiers/WWW.{d.upper()}./history"), 200).json()
    assert r["domain"] == d and list(r["fields"]) == list(ALL)
    assert world.alice.get("/dossiers/nothere.test/history").status_code == 404
    assert get(world.alice, d).json()["fields"].keys() == dict.fromkeys(ALL).keys()


def test_p42_history_requires_auth(world, build, corpus):
    d = domains(corpus)[0]
    build(d)
    assert httpx.get(f"{world.alice.base_url}/dossiers/{d}/history", timeout=5).status_code == 401
    assert httpx.get(f"{world.alice.base_url}/changes", timeout=5).status_code == 401


def test_p50_feed_shape_users_share(world, web, clock, build, refresh, corpus):
    d = (movers(corpus) or domains(corpus))[0]
    two_builds(world, web, clock, build, refresh, d)
    a = assert_status(world.alice.get("/changes"), 200).json()
    b = assert_status(world.bob.get("/changes"), 200).json()
    assert a == b and a["has_more"] is False
    for e in a["changes"]:
        assert set(e) >= {"seq", "domain", "field", "type", "from", "to", "true_from", "learned_at"}
        assert e["type"] in ("change", "correction")


def test_p52_since_limit_pagination(world, web, clock, build, refresh, corpus):
    ds = movers(corpus)
    if not ds:
        pytest.skip("no mover")
    for d in ds:
        build(d)
    at(clock, T1)
    web.epoch(1)
    for d in ds:
        refresh(d)
    full = feed(world.alice)
    if len(full) < 2:
        pytest.skip("fewer than two feed entries")
    first = assert_status(world.alice.get("/changes", params={"limit": 1}), 200).json()
    assert first["changes"] == full[:1] and first["has_more"] is True
    r = assert_status(world.alice.get("/changes", params={"since": full[0]["seq"]}), 200).json()
    assert r["changes"] == full[1:] and r["has_more"] is False
    r = assert_status(world.alice.get("/changes", params={"since": full[-1]["seq"]}), 200).json()
    assert r == {"changes": [], "has_more": False}
    r = assert_status(world.alice.get("/changes", params={"since": 10 ** 9}), 200).json()
    assert r == {"changes": [], "has_more": False}
    r = assert_status(world.alice.get("/changes", params={"limit": len(full)}), 200).json()
    assert r["has_more"] is False and r["changes"] == full
    r = assert_status(world.alice.get("/changes", params={"limit": len(full) - 1}), 200).json()
    assert r["has_more"] is True


@pytest.mark.parametrize("params", [{"since": "-1"}, {"since": "1e3"}, {"since": "4.0"},
                                    {"since": "+4"}, {"since": "abc"}, {"since": ""},
                                    {"limit": "0"}, {"limit": "201"}, {"limit": "x"},
                                    {"limit": "1e2"}, {"limit": "-5"}])
def test_p53_feed_param_validation(world, params):
    r = world.alice.get("/changes", params=params)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed", \
        (params, r.status_code, r.text[:120])


def test_p54_limit_boundaries_ok(world):
    for lim in ("1", "200", "50"):
        assert_status(world.alice.get("/changes", params={"limit": lim}), 200)
    assert_status(world.alice.get("/changes", params={"since": "0", "extra": "ignored"}), 200)


# ----------------------------------------------------------------- imports
def test_p62_stage3_export_import_roundtrip(world, web, clock, build, refresh, corpus, base_url):
    ds = (movers(corpus) or domains(corpus))[:2]
    for d in ds:
        build(d)
    at(clock, T1)
    web.epoch(1)
    for d in ds:
        refresh(d)
    snap = {}
    for d in ds:
        snap[d] = dict(cur=get(world.alice, d).json(), h=hist(world.alice, d),
                       a0=get(world.alice, d, as_of=T0).json(),
                       v=world.alice.get(f"/dossiers/{d}/values",
                                         params={"true_at": "2099-01-01", "as_of": T0}).json())
    fd = feed(world.alice)
    exp = assert_status(httpx.get(f"{base_url}/_test/export", timeout=10), 200).json()
    key = new_key()
    world.alice.post("/dossiers", json={"domain": "zzz-extra.test"}, idempotency_key=key)
    end = time.monotonic() + 30
    while get(world.alice, "zzz-extra.test").json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    web.reset()
    assert httpx.post(f"{base_url}/_test/import", json=exp, timeout=10).status_code == 204
    assert web.log() == []
    for d in ds:
        assert get(world.alice, d).json() == snap[d]["cur"]
        assert hist(world.alice, d) == snap[d]["h"]
        assert get(world.alice, d, as_of=T0).json() == snap[d]["a0"]
        assert world.alice.get(f"/dossiers/{d}/values",
                               params={"true_at": "2099-01-01", "as_of": T0}).json() == snap[d]["v"]
    assert feed(world.alice) == fd
    assert httpx.post(f"{base_url}/_test/import", json=exp, timeout=10).status_code == 204
    assert feed(world.alice) == fd and hist(world.alice, ds[0]) == snap[ds[0]]["h"]
    # a build after import adds nothing new when nothing changed (epoch 1 unchanged, clock later)
    at(clock, T2)
    web.reset(1)
    refresh(ds[0])
    assert feed(world.alice) == fd


def _old_world(prev, web, corpus, domain):
    httpx.post(f"{prev.base_url}/_test/reset", json=fx.fixture(), timeout=RESET_TIMEOUT)
    web.reset()
    tok = assert_status(prev.post("/auth/login", token=None, json={
        "email": fx.ALICE["email"], "password": fx.ALICE["password"]}), 200).json()["token"]
    prev.token = tok
    key = new_key()
    assert_status(prev.post("/dossiers", json={"domain": domain}, idempotency_key=key), 202)
    end = time.monotonic() + 40
    while True:
        b = assert_status(prev.get(f"/dossiers/{domain}"), 200).json()
        if b["state"] != "building" or time.monotonic() > end:
            return tok, key, b


def test_p60_import_from_previous_stage(world, web, corpus, previous_api, base_url, clock):
    """Stage-1/2 import (run.sh third arg selects the previous stage)."""
    prev = previous_api
    d = domains(corpus)[0]
    tok, key, b = _old_world(prev, web, corpus, d)
    assert b["state"] == "ready"
    exp = httpx.get(f"{prev.base_url}/_test/export", timeout=10).json()
    web.reset()
    assert httpx.post(f"{base_url}/_test/import", json=exp, timeout=10).status_code == 204
    assert web.log() == []
    cur = Api(base_url, token=tok)
    body = assert_status(cur.get(f"/dossiers/{d}"), 200).json()
    assert list(body["fields"]) == list(ALL)
    ex = body["fields"]["executives"]
    assert ex["value"] is None and ex["status"] == "unknown" and ex["citations"] == []
    assert ex["true_from"] is None and ex["learned_at"] is None
    h = hist(cur, d)
    assert h["executives"] == []
    for f in fx.FIELDS:
        v = b["fields"][f]["value"]
        if v is None:
            assert h[f] == [], f
        else:
            assert [e["type"] for e in h[f]] == ["initial"], (f, h[f])
            assert fx.instant(h[f][0]["learned_at"]) == fx.instant(b["researched_at"])
            assert fx.same_value(h[f][0]["value"], body["fields"][f]["value"])
    assert feed(cur) == []
    # as_of: at researched_at returns imported fields; earlier is 404
    r = get(cur, d, as_of=b["researched_at"])
    assert r.status_code == 200 and r.json()["researched_at"] == b["researched_at"]
    assert r.json()["state"] == "ready"
    for f in fx.FIELDS:
        assert r.json()["fields"][f]["value"] == body["fields"][f]["value"], f
        if body["fields"][f]["value"] is not None:
            assert fx.instant(r.json()["fields"][f]["learned_at"]) == fx.instant(b["researched_at"])
    ra = fx.instant(b["researched_at"]) - timedelta(seconds=1)
    assert get(cur, d, as_of=ra.isoformat()).status_code == 404
    # imported candidates learned_at == retrieved_at
    for f in fx.FIELDS:
        for c in body["fields"][f]["candidates"]:
            assert fx.instant(c["learned_at"]) == fx.instant(c["retrieved_at"]), c
    # replay of the original idempotent request still 200
    assert cur.post("/dossiers", json={"domain": d}, idempotency_key=key).status_code == 200
    # first build after import compares with imported values; executives appear as change
    at(clock, T1)
    assert_status(cur.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
    end = time.monotonic() + 40
    while get(cur, d).json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    nb = get(cur, d).json()
    assert nb["state"] == "ready"
    h2 = hist(cur, d)
    if nb["fields"]["executives"]["value"] is not None:
        assert [e["type"] for e in h2["executives"]] == ["change"], h2["executives"]
        assert any(e["field"] == "executives" and e["type"] == "change" for e in feed(cur))
    # the imported build stays an as_of snapshot with executives unknown
    r = get(cur, d, as_of=b["researched_at"]).json()
    assert r["fields"]["executives"]["value"] is None
    cur.close()


def test_p61_import_with_null_researched_at(world, web, corpus, previous_api, base_url):
    """A previous-stage dossier that never completed ready answers every as_of with 404."""
    prev = previous_api
    d = domains(corpus)[0]
    httpx.post(f"{prev.base_url}/_test/reset", json=fx.fixture(), timeout=RESET_TIMEOUT)
    web.reset()
    for prov in fx.PROVIDERS:
        web.fault(prov, list(fx.METHODS), "error")
    tok = assert_status(prev.post("/auth/login", token=None, json={
        "email": fx.ALICE["email"], "password": fx.ALICE["password"]}), 200).json()["token"]
    prev.token = tok
    assert_status(prev.post("/dossiers", json={"domain": d}, idempotency_key=new_key()), 202)
    end = time.monotonic() + 40
    while prev.get(f"/dossiers/{d}").json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    exp = httpx.get(f"{prev.base_url}/_test/export", timeout=10).json()
    web.reset()
    assert httpx.post(f"{base_url}/_test/import", json=exp, timeout=10).status_code == 204
    cur = Api(base_url, token=tok)
    body = assert_status(cur.get(f"/dossiers/{d}"), 200).json()
    assert body["researched_at"] is None
    for as_of in (T0, "2099-01-01T00:00:00Z"):
        assert get(cur, d, as_of=as_of).status_code == 404
    assert all(v == [] for v in hist(cur, d).values())
    cur.close()


# ---------------------------------------------------------------- restarts
@pytest.fixture
def can_restart(request):
    if not request.config.getoption("--control-dir"):
        pytest.skip("no --control-dir: restart needs the docker/control harness")


def test_p70_restart_keeps_everything(world, web, clock, build, refresh, corpus, base_url,
                                      can_restart, restart):
    d = (movers(corpus) or domains(corpus))[0]
    key = new_key()
    assert_status(world.alice.post("/dossiers", json={"domain": d}, idempotency_key=key), 202)
    end = time.monotonic() + 30
    while get(world.alice, d).json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    at(clock, T1)
    web.epoch(1)
    rkey = new_key()
    assert_status(world.alice.post(f"/dossiers/{d}/refresh", idempotency_key=rkey), 202)
    end = time.monotonic() + 30
    while get(world.alice, d).json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    tok = world.alice.token
    before = dict(cur=get(world.alice, d).json(), h=hist(world.alice, d), feed=feed(world.alice),
                  a0=get(world.alice, d, as_of=T0).json(), lst=world.alice.get("/dossiers").json(),
                  v=world.alice.get(f"/dossiers/{d}/values", params={"true_at": "2099-01-01", "as_of": T1}).json())
    restart()
    c = Api(base_url, token=tok)
    assert get(c, d).json() == before["cur"]
    assert hist(c, d) == before["h"]
    assert feed(c) == before["feed"]
    assert get(c, d, as_of=T0).json() == before["a0"]
    assert c.get("/dossiers").json() == before["lst"]
    assert c.get(f"/dossiers/{d}/values", params={"true_at": "2099-01-01", "as_of": T1}).json() == before["v"]
    login = httpx.post(f"{base_url}/auth/login", json={"email": fx.ALICE["email"],
                                                       "password": fx.ALICE["password"]}, timeout=5)
    assert login.status_code == 200
    rep = c.post("/dossiers", json={"domain": d}, idempotency_key=key)
    assert rep.status_code == 200
    rep2 = c.post(f"/dossiers/{d}/refresh", idempotency_key=rkey)
    assert rep2.status_code == 200 and rep2.json()["domain"] == d
    # clock holds the time it read: a build now is stamped T1
    nb_before = len(feed(c))
    assert_status(c.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
    end = time.monotonic() + 30
    while get(c, d).json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    assert fx.instant(get(c, d).json()["researched_at"]) == fx.instant(T1)
    # later entries get larger seq; restart again, still consistent
    at(clock, T2)
    web.epoch(0)
    assert_status(c.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
    end = time.monotonic() + 30
    while get(c, d).json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    fd = feed(c)
    seqs = [e["seq"] for e in fd]
    assert seqs == sorted(set(seqs)), seqs
    assert fd[: len(before["feed"])] == before["feed"]
    h2 = hist(c, d)
    restart()
    c2 = Api(base_url, token=tok)
    assert feed(c2) == fd and hist(c2, d) == h2
    c2.close()
    c.close()
