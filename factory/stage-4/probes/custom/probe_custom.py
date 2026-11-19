"""Examiner targeted probes, stage 4, on the crafted corpus (custom/gen_corpus.py). From the spec only.

Rows: R-06,R-08,R-09,R-10,R-15,R-16,R-19,R-22..R-25,R-27,R-29,R-34,R-35,R-44,R-58,R-61,R-64.
Run through custom/rig.sh (own mock web + services), not through the harness runner.
"""
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import fixtures as fx
from harness.http import Api, RESET_TIMEOUT, assert_status, new_key

pytestmark = pytest.mark.stage(4)
BASE = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
ALL = fx.FIELDS + ("executives", "investors")


def T(k):
    return (BASE + timedelta(days=k)).isoformat()


def same(a, b):
    return fx.instant(a) == fx.instant(b)


class Runner:
    def __init__(self, world, web, clock, settle):
        self.world, self.web, self.clock, self.settle = world, web, clock, settle
        self.seen = set()

    def run(self, domain, epoch, k, client=None):
        """clock -> T(k), mock -> epoch, then build (first) or refresh; waits; returns body."""
        client = client or self.world.alice
        assert_status(self.clock(T(k)), 204)
        self.web.epoch(epoch)
        if domain in self.seen:
            assert_status(client.post(f"/dossiers/{domain}/refresh", idempotency_key=new_key()), 202)
        else:
            assert_status(client.post("/dossiers", json={"domain": domain}, idempotency_key=new_key()), 202)
            self.seen.add(domain)
        return self.settle(domain, client)


@pytest.fixture
def R(world, web, clock, settle):
    return Runner(world, web, clock, settle)


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


def cands(body, name, value=None):
    return [c for c in body["fields"][name]["candidates"] if value is None or c["value"] == value]


# ============================================================ (1) multi-build corroborated_since
def test_k01_ceo_standing_origins_over_builds(world, web, R):
    d = "acme-robotics.test"
    b0 = R.run(d, 0, 0)
    f = b0["fields"]["ceo"]
    assert f["value"] == "Dana Ruiz" and f["origins"] == ["acme-robotics.test"], f
    assert f["corroborated"] is False and f["corroborated_since"] is None
    b1 = R.run(d, 1, 1)
    f = b1["fields"]["ceo"]
    assert f["origins"] == ["acme-robotics.test", "newsa.test"] and f["corroborated"] is True, f
    assert same(f["corroborated_since"], T(1)), f["corroborated_since"]
    # build 2: newsa page gone; standing origins remain (R-15)
    b2 = R.run(d, 2, 2)
    f = b2["fields"]["ceo"]
    assert f["origins"] == ["acme-robotics.test"] and f["corroborated"] is False, f
    assert same(f["corroborated_since"], T(1)), ("standing origins lost", f["corroborated_since"])
    # build 3: new selected value -> starts with none
    b3 = R.run(d, 3, 3)
    f = b3["fields"]["ceo"]
    assert f["value"] == "Sam Ortiz" and f["corroborated"] is False and f["corroborated_since"] is None, f
    # a failed build (all providers fail) at T4 contributes nothing (R-61)
    for p in fx.PROVIDERS:
        web.fault(p, list(fx.METHODS), "error")
    bf = R.run(d, 4, 4)
    assert bf["state"] == "failed"
    assert bf["fields"]["ceo"]["corroborated_since"] is None
    web.normal()
    b5 = R.run(d, 4, 5)
    f = b5["fields"]["ceo"]
    assert f["value"] == "Sam Ortiz" and f["origins"] == ["acme-robotics.test", "newsb.test"], f
    assert same(f["corroborated_since"], T(5)), ("failed build time used?", f["corroborated_since"])
    # back to Dana Ruiz: a new selected value again starts with none, though the old origins existed
    b6 = R.run(d, 5, 6)
    f = b6["fields"]["ceo"]
    assert f["value"] == "Dana Ruiz" and f["corroborated"] is False and f["corroborated_since"] is None, f
    # as_of keeps answering with the keys
    old = assert_status(world.alice.get(f"/dossiers/{d}", params={"as_of": T(1)}), 200).json()
    assert old["fields"]["ceo"]["origins"] == ["acme-robotics.test", "newsa.test"]
    # the ceo's own history: only value changes add entries
    assert [e["value"] for e in hist(world.alice, d)["ceo"]] == ["Dana Ruiz", "Sam Ortiz", "Dana Ruiz"]


def test_k02_executives_members_standing_origins(world, web, R):
    d = "foundry-labs.test"
    b0 = R.run(d, 0, 0)
    f = b0["fields"]["executives"]
    assert f["value"] == [{"title": "cfo", "name": "Ana Silva"}, {"title": "coo", "name": "Ben Okafor"}], f
    assert f["origins"] == ["foundry-labs.test", "newsc.test"], f
    assert f["corroborated"] is False and f["corroborated_since"] is None, f  # coo has one origin
    fx.assert_origins("executives", f)
    b1 = R.run(d, 1, 1)
    f = b1["fields"]["executives"]
    assert f["origins"] == ["foundry-labs.test", "newsc.test", "newsd.test"], f
    assert f["corroborated"] is True and same(f["corroborated_since"], T(1)), f
    fx.assert_origins("executives", f)
    b2 = R.run(d, 2, 2)
    f = b2["fields"]["executives"]
    # coo became Cara Diaz (a new member): one origin, so no longer corroborated, no standing set
    assert f["value"][1] == {"title": "coo", "name": "Cara Diaz"}, f
    assert f["corroborated"] is False and f["corroborated_since"] is None, f
    # Ben Okafor returns as coo with one origin only: a member that left starts again (R-19), though he once had two
    b3 = R.run(d, 3, 3)
    f = b3["fields"]["executives"]
    assert f["value"] == [{"title": "cfo", "name": "Ana Silva"}, {"title": "coo", "name": "Ben Okafor"}], f
    assert f["corroborated"] is False and f["corroborated_since"] is None, ("returning member kept old origins", f)


# ============================================================ (2) investors typing (R-35) and rules
def test_t01_investors_history_typing(world, web, R):
    d = "harbor-tech.test"
    expect = [
        (0, ["Bluebird Capital", "General Atlantic", "Northwind Ventures"], "2024-05-02", "initial"),
        (1, ["Bluebird Capital", "General Atlantic", "Greyfriars Holdings", "Northwind Ventures"],
         "2024-05-02", "correction"),
        (2, ["Bluebird Capital", "General Atlantic", "Greyfriars Holdings", "Northwind Ventures",
             "Redwood Partners"], "2025-02-02", "change"),
        (3, ["Bluebird Capital", "General Atlantic", "Greyfriars Holdings", "Redwood Partners"],
         "2025-02-02", "change"),                                  # removal only -> change (ruling)
        (4, ["Bluebird Capital", "General Atlantic", "Greyfriars Holdings", "Redwood Partners", "Zenith Fund"],
         None, "change"),                                          # null true_from -> change
    ]
    for epoch, value, tf, typ in expect:
        b = R.run(d, epoch, epoch)
        assert b["state"] == "ready", b
        f = b["fields"]["investors"]
        assert f["status"] == "known" and f["value"] == value, (epoch, f["value"])
        assert f["true_from"] == tf, (epoch, f["true_from"])
        fx.assert_origins("investors", f)
        h = hist(world.alice, d)["investors"]
        assert h[-1]["type"] == typ, (epoch, [e["type"] for e in h])
        assert h[-1]["value"] == value
    assert [e["type"] for e in hist(world.alice, d)["investors"]] == ["initial", "correction", "change", "change", "change"]
    fe = [e for e in feed(world.alice) if e["field"] == "investors"]
    assert [e["type"] for e in fe] == ["correction", "change", "change", "change"]


def test_t02_extraction_rules(world, web, R):
    d = "harbor-tech.test"
    b = R.run(d, 0, 0)
    names = {c["value"] for c in b["fields"]["investors"]["candidates"]}
    # amount rule (R-24), suffix runs (R-23)
    assert "General Atlantic" in names and "Bluebird Capital" in names and "Northwind Ventures" in names
    # 'led by Dana Ruiz' names no investor; negated, bare-word, company-name-only runs name none
    for bad in ("Dana Ruiz", "Phantom Capital", "Sequoia", "Capital", "Harbor Tech Capital", "Tech Capital"):
        assert bad not in names, (bad, names)
    assert len(names) == 3, names
    for c in b["fields"]["investors"]["candidates"]:
        assert c["selected"] is True and c["kind"] == "own"
    # every candidate's excerpt supports its name (R-25): single sentence containing the name
    for c in b["fields"]["investors"]["candidates"]:
        assert c["value"] in c["excerpt"] and c["excerpt"].count(".") >= 1


def test_t03_membership_runs_and_lookalikes(world, web, R):
    d = "ledger-works.test"
    b = R.run(d, 0, 0)
    f = b["fields"]["investors"]
    members = ["Acme Widget Fund Holdings", "Mirage Capital", "Quartz Capital", "Sequoia", "Solo Partners"]
    assert f["value"] == members, f["value"]
    got = {c["value"] for c in f["candidates"]}
    assert {"Ghost Capital", "Lone Ventures"} <= got, got       # candidates, not members
    for c in f["candidates"]:
        assert c["selected"] is (c["value"] in members), c
    for c in cands(b, "investors", "Ghost Capital"):
        assert c["kind"] == "aggregator" and c["origin"] == d, c   # lookalike: kind and origin (R-03/R-07)
    assert {c["origin"] for c in cands(b, "investors", "Mirage Capital")} == {d, "daily.test"}
    assert {c["origin"] for c in cands(b, "investors", "Quartz Capital")} == {"newsx.test", "newsy.test"}
    assert f["corroborated"] is False                            # Solo Partners etc. have one origin
    # company-name removal splits a run: no name from "Orbit Ledger Works Capital"
    for bad in ("Orbit Ledger Works Capital", "Orbit", "Capital", "Orbit Capital", "Works Capital", "Ledger Works Capital"):
        assert bad not in got and bad not in members, (bad, got)
    # lookalike check on the page itself via citations of members
    assert all(cit["url"] for cit in f["citations"])


# ============================================================ (3) /values for investors
def test_v01_investors_values_at_true_at(world, web, R):
    d = "harbor-tech.test"
    for e in range(5):
        R.run(d, e, e)

    def vals(true_at, as_of=None):
        p = {"true_at": true_at}
        if as_of:
            p["as_of"] = as_of
        return assert_status(world.alice.get(f"/dossiers/{d}/values", params=p), 200).json()["fields"]["investors"]

    f = vals("2023-06-01")
    assert f["value"] == ["General Atlantic", "Greyfriars Holdings"] and f["true_from"] == "2023-01-01", f
    urls = [c["url"] for c in f["citations"]]
    assert urls == sorted(urls, key=lambda u: ["General Atlantic", "Greyfriars Holdings"].index(
        "General Atlantic" if u.endswith("/series") else "Greyfriars Holdings")), urls
    f = vals("2025-03-01")
    assert f["value"] == ["Bluebird Capital", "General Atlantic", "Greyfriars Holdings", "Redwood Partners"], f
    assert f["true_from"] == "2025-02-02"
    f = vals("2025-03-01", T(1))      # as of the second build: Northwind still present, no Redwood yet
    assert f["value"] == ["Bluebird Capital", "General Atlantic", "Greyfriars Holdings", "Northwind Ventures"], f
    assert f["true_from"] == "2024-05-02"
    f = vals("2021-01-01")
    assert f["value"] is None and f["true_from"] is None and f["citations"] == [], f
    f = vals("2024-06-01", T(4))     # hD (null true_from) never holds
    assert "Zenith Fund" not in (f["value"] or []), f


# ============================================================ (4) originals and lineage
ENTRY = {"https://daily-a.test/cd1", "https://daily-b.test/cd2", "https://chain1.test/p", "https://hop1.test/p",
         "https://void.test/p", "https://selfcopy.test/s", "https://cyc-x.test/1", "https://mirror.test/f",
         "https://mirror2.test/f"}


def test_l01_origins_originals_and_hops(world, web, R):
    d = "copy-desk.test"
    web.reset()
    b = R.run(d, 0, 0)
    assert b["state"] == "ready"
    f = b["fields"]["investors"]
    want = {
        "Syndic Capital": {"pressroom.test"},     # two copies of one original: one source (R-09)
        "Chain Capital": {"chain5.test"},         # fourth Canonical not followed -> host (R-08)
        "Hop Capital": {"reghop4.test"},          # three hops followed to the original's registrant
        "Void Capital": {"nowhere.test"},         # no provider serves the original -> host
        "Self Capital": {"selfreg.test"},         # Canonical equal to own URL: rule 2 skipped (R-64)
        "Cycle Capital": {"cyc-x.test"},          # cycle ends at the fourth follow (R-64/R-08)
        "Wire Capital": {"wire.test"},            # First-Published-By first, normalised (R-05)
    }
    for name, origins in want.items():
        cs = cands(b, "investors", name)
        assert cs, f"no candidate {name}"
        entry = [c for c in cs if c["url"] in ENTRY]
        assert entry, (name, [c["url"] for c in cs])
        assert {c["origin"] for c in entry if c["url"] in ENTRY} == origins, (name, [(c["url"], c["origin"]) for c in cs])
    # one source (or kind news with one origin) is not a member; copies that reach distinct origins are
    members = f["value"] or []
    for n in ("Syndic Capital", "Void Capital", "Self Capital", "Wire Capital", "Hop Capital"):
        assert n not in members, (n, members)
    assert f["status"] == ("unknown" if f["value"] is None else "known")
    # originals obtained from a provider (R-06): non-searchable pages were fetched
    touched = " ".join(str(c.get("urls")) for c in web.log())
    for u in ("https://pressroom.test/cd", "https://chain2.test/p", "https://chain3.test/p",
              "https://chain4.test/p", "https://hop2.test/p", "https://hop3.test/p",
              "https://hop4.test/p", "https://cyc-y.test/2"):
        assert u in touched, f"original {u} never requested"
    log = web.log()
    cum, over = 0, []
    for c in log:
        cum += c["cost"]
        over.append((c["seq"], c["provider"], c["method"], c.get("depth"), c["cost"], c["status"], cum))
    assert web.units() <= 80, ("provider billed", web.units(), "dossier spent_units", b["spent_units"], [(o[0], o[2], o[4], o[6]) for o in over if o[4]])
    assert b["spent_units"] == web.units(), (b["spent_units"], web.units())


def test_l02_originals_respect_shared_budget(world, web):
    d = "copy-desk.test"
    web.reset()
    r = assert_status(world.alice.post("/batches", json={"domains": [d], "budget_units": 6},
                                       idempotency_key=new_key()), 202).json()
    end = time.monotonic() + fx.SETTLE_SECONDS
    while True:
        bt = assert_status(world.alice.get(f"/batches/{r['batch_id']}"), 200).json()
        if bt["state"] == "done" or time.monotonic() > end:
            break
        time.sleep(0.2)
    assert bt["state"] == "done"
    assert bt["spent_units"] <= 6 and web.units() <= 6, (bt["spent_units"], web.units())
    dos = assert_status(world.alice.get(f"/dossiers/{d}"), 200).json()
    assert dos["state"] in ("ready", "failed") and dos["spent_units"] == bt["spent_units"]


# ============================================================ (4b) fields after budget exhaustion
def _full_text(log):
    """Text a build obtained in full: extract results and search results that are not `lite` snippets."""
    out = []
    for c in log:
        if c["status"] >= 400:
            continue
        if c["method"] == "extract" or c.get("depth") not in (None, "lite"):
            out += [s["text"] for s in (c.get("served") or [])]
    return " ".join(out)


@pytest.mark.parametrize("budget", [1, 2, 3, 4, 6, 9])
def test_b01_budget_exhausted_fields_known_exactly_when_supported(world, web, reset, budget):
    d = "acme-robotics.test"
    reset(fx.fixture())
    web.reset()
    alice = world.alice.__class__(world.alice.base_url).authenticate(fx.ALICE["email"], fx.ALICE["password"])
    r = assert_status(alice.post("/batches", json={"domains": [d], "budget_units": budget},
                                 idempotency_key=new_key()), 202).json()
    end = time.monotonic() + fx.SETTLE_SECONDS
    while True:
        bt = assert_status(alice.get(f"/batches/{r['batch_id']}"), 200).json()
        if bt["state"] == "done" or time.monotonic() > end:
            break
        time.sleep(0.2)
    log = web.log()
    summary = [(c["method"], c.get("depth"), c["cost"], c["status"]) for c in log]
    assert bt["state"] == "done" and bt["spent_units"] <= budget and web.units() <= budget, (bt, summary)
    dos = assert_status(alice.get(f"/dossiers/{d}"), 200).json()
    assert dos["state"] in ("ready", "failed"), dos["state"]
    f = dos["fields"]["ceo"]
    obtained = "Acme Robotics CEO: Dana Ruiz." in _full_text(log)
    if obtained:
        assert dos["state"] == "ready" and f["value"] == "Dana Ruiz", (budget, dos["state"], f["status"], summary)
    else:
        assert f["status"] == "unknown", (budget, f, summary)
    for name in ALL:
        fx.assert_origins(name, dos["fields"][name])


# ============================================================ (5) stage-3 export with builds -> stage 4
def _s3_login(prev):
    return assert_status(prev.post("/auth/login", token=None, json={
        "email": fx.ALICE["email"], "password": fx.ALICE["password"]}), 200).json()["token"]


def _strip(body):
    """A stage-3 field as stage 4 answers it: drop the keys this stage adds."""
    out = {}
    for name, f in body["fields"].items():
        if name == "investors":
            continue
        g = {k: v for k, v in f.items() if k not in ("origins", "corroborated", "corroborated_since")}
        if "candidates" in g:
            g["candidates"] = [{k: v for k, v in c.items() if k != "origin"} for c in g["candidates"]]
        out[name] = g
    return out


def test_m01_stage3_export_with_builds(world, web, clock, previous_api, base_url):
    d = "acme-robotics.test"
    prev = previous_api
    httpx.post(f"{prev.base_url}/_test/reset", json=fx.fixture(), timeout=RESET_TIMEOUT)
    web.reset()
    tok = _s3_login(prev)
    cli = Api(prev.base_url, token=tok)

    def s3(epoch, k, first):
        assert_status(httpx.post(f"{prev.base_url}/_test/clock", json={"now": T(k)}, timeout=10), 204)
        web.epoch(epoch)
        if first:
            assert_status(cli.post("/dossiers", json={"domain": d}, idempotency_key=new_key()), 202)
        else:
            assert_status(cli.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
        end = time.monotonic() + fx.SETTLE_SECONDS
        while cli.get(f"/dossiers/{d}").json()["state"] == "building" and time.monotonic() < end:
            time.sleep(0.1)

    s3(0, 0, True)
    s3(1, 1, False)
    old_cur = cli.get(f"/dossiers/{d}").json()
    old_a0 = cli.get(f"/dossiers/{d}", params={"as_of": T(0)}).json()
    old_v = cli.get(f"/dossiers/{d}/values", params={"true_at": "2099-01-01", "as_of": T(1)}).json()
    old_v0 = cli.get(f"/dossiers/{d}/values", params={"true_at": "2099-01-01", "as_of": T(0)}).json()
    exp = assert_status(httpx.get(f"{prev.base_url}/_test/export", timeout=10), 200).json()
    web.reset()
    assert httpx.post(f"{base_url}/_test/import", json=exp, timeout=10).status_code == 204
    assert web.log() == []
    cur = Api(base_url, token=tok)
    new_cur = assert_status(cur.get(f"/dossiers/{d}"), 200).json()
    assert list(new_cur["fields"]) == list(ALL)
    assert _strip(new_cur) == _strip(old_cur)
    new_a0 = assert_status(cur.get(f"/dossiers/{d}", params={"as_of": T(0)}), 200).json()
    assert _strip(new_a0) == _strip(old_a0)
    assert new_a0["researched_at"] == old_a0["researched_at"]
    new_v = assert_status(cur.get(f"/dossiers/{d}/values", params={"true_at": "2099-01-01", "as_of": T(1)}), 200).json()
    assert {k: v for k, v in new_v["fields"].items() if k != "investors"} == old_v["fields"]
    new_v0 = assert_status(cur.get(f"/dossiers/{d}/values", params={"true_at": "2099-01-01", "as_of": T(0)}), 200).json()
    assert {k: v for k, v in new_v0["fields"].items() if k != "investors"} == old_v0["fields"]
    # R-16: each exported build's candidates count as gathered at that build's time; origin = URL host (R-13)
    f = new_cur["fields"]["ceo"]
    assert f["value"] == "Dana Ruiz"
    assert {c["origin"] for c in f["candidates"]} == {"acme-robotics.test", "newsa.test"}, f["candidates"]
    assert f["origins"] == ["acme-robotics.test", "newsa.test"] and f["corroborated"] is True
    assert same(f["corroborated_since"], T(1)), f["corroborated_since"]
    f0 = new_a0["fields"]["ceo"]
    assert f0["origins"] == ["acme-robotics.test"] and f0["corroborated"] is False, f0
    # investors: unknown everywhere (R-59), including the kept build
    for body in (new_cur, new_a0):
        inv = body["fields"]["investors"]
        assert inv["status"] == "unknown" and inv["value"] is None and inv["origins"] == [], inv
        assert inv["corroborated"] is False and inv["corroborated_since"] is None
    assert hist(cur, d)["investors"] == []
    # a stage-4 refresh after import keeps the ceo's standing origins (value unchanged)
    assert_status(clock(T(2)), 204)
    assert_status(cur.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
    end = time.monotonic() + fx.SETTLE_SECONDS
    while cur.get(f"/dossiers/{d}").json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    again = cur.get(f"/dossiers/{d}").json()["fields"]["ceo"]
    assert same(again["corroborated_since"], T(1)), again


# ============================================================ (6) exports of older stages (stage-1/2/3 services)
def test_m03_import_older_export(world, web, clock, previous_api, base_url):
    d = "harbor-tech.test"
    prev = previous_api
    httpx.post(f"{prev.base_url}/_test/reset", json=fx.fixture(), timeout=RESET_TIMEOUT)
    web.reset()
    tok = _s3_login(prev)
    cli = Api(prev.base_url, token=tok)
    web.epoch(0)
    assert_status(cli.post("/dossiers", json={"domain": d}, idempotency_key=new_key()), 202)
    end = time.monotonic() + fx.SETTLE_SECONDS
    while cli.get(f"/dossiers/{d}").json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    old = cli.get(f"/dossiers/{d}").json()
    assert old["state"] == "ready"
    exp = assert_status(httpx.get(f"{prev.base_url}/_test/export", timeout=10), 200).json()
    web.reset()
    assert httpx.post(f"{base_url}/_test/import", json=exp, timeout=10).status_code == 204
    assert web.log() == []
    cur = Api(base_url, token=tok)
    new = assert_status(cur.get(f"/dossiers/{d}"), 200).json()
    assert list(new["fields"]) == list(ALL)
    for name in fx.FIELDS:
        assert new["fields"][name]["value"] == old["fields"][name]["value"], name
        for c in new["fields"][name]["candidates"]:
            assert c["origin"], c
        fx.assert_origins(name, new["fields"][name])
        assert [(c["url"], c["excerpt"]) for c in new["fields"][name]["citations"]] ==             [(c["url"], c["excerpt"]) for c in old["fields"][name]["citations"]] if "excerpt" in str(old["fields"][name]["citations"]) else True
    inv = new["fields"]["investors"]
    assert inv["status"] == "unknown" and inv["value"] is None and inv["origins"] == [] and inv["corroborated"] is False
    assert hist(cur, d)["investors"] == []
    before = {n: [e["type"] for e in hist(cur, d)[n]] for n in fx.FIELDS}
    # the first stage-4 ready build learns the investors: a `change` (the imported build was the first ready one)
    assert_status(clock(T(3)), 204)
    assert_status(cur.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
    end = time.monotonic() + fx.SETTLE_SECONDS
    while cur.get(f"/dossiers/{d}").json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    assert cur.get(f"/dossiers/{d}").json()["state"] == "ready"
    h = hist(cur, d)
    assert [e["type"] for e in h["investors"]] == ["change"], h["investors"]
    assert {n: [e["type"] for e in h[n]] for n in fx.FIELDS} == before
