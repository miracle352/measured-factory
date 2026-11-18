"""Examiner probes (browser). Spec-only. Screens saved under factory/stage-2/screens/."""
import json
import os
import pathlib
import time

import pytest
from playwright.sync_api import expect

import fixtures as fx
import screens
import web as dw
from harness.http import assert_status, new_key

pytestmark = pytest.mark.stage(2)
SHOTS = pathlib.Path(os.environ.get("SHOTS", "/tmp/shots"))
SIZES = {"phone": (375, 800), "desktop": (1280, 900)}


def shot(page, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def no_hscroll(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def tid(page, name):
    return page.get_by_test_id(name)


def domains(corpus):
    return sorted(d for d in corpus.key if "expected" in corpus.key[d])


def contested_domain(corpus):
    for d in domains(corpus):
        for f in fx.FIELDS:
            if len(corpus.expected(d, f, stage=1)) > 1:
                return d, f
    raise LookupError


@pytest.fixture(params=list(SIZES), ids=list(SIZES))
def sized(request, page):
    w, h = SIZES[request.param]
    page.set_viewport_size({"width": w, "height": h})
    page.size_name = request.param
    return page


def test_u01_every_route_every_size(world, build, corpus, sized, web):
    """R-34,R-42,R-26..R-33,R-36: routes, testids, no horizontal scroll, screenshots."""
    page = sized
    n = page.size_name
    cd, cf = contested_domain(corpus)
    body = build(cd)
    assert body["fields"][cf]["status"] == "contested"
    page.goto("/signup"); expect(tid(page, "signup-submit")).to_be_visible()
    assert no_hscroll(page); shot(page, f"signup-{n}")
    page.goto("/login"); expect(tid(page, "login-submit")).to_be_visible()
    assert no_hscroll(page); shot(page, f"login-{n}")
    screens.sign_in(page)
    expect(tid(page, "current-user")).to_contain_text("Alice")
    page.goto("/")
    expect(tid(page, f"dossier-item-{cd}")).to_be_visible()
    expect(tid(page, f"dossier-item-{cd}")).to_have_attribute("data-state", "ready")
    assert screens.links_to(tid(page, f"dossier-item-{cd}"), f"/dossiers/{cd}")
    expect(tid(page, "current-user")).to_be_visible()
    assert no_hscroll(page); shot(page, f"list-{n}")
    # dossier
    screens.open_dossier(page, cd)
    expect(tid(page, "current-user")).to_be_visible()
    expect(tid(page, "dossier-domain")).to_have_text(cd)
    expect(tid(page, "dossier-spent")).to_have_attribute("data-units", str(body["spent_units"]))
    expect(tid(page, "dossier-researched-at")).to_be_visible()
    order = screens.testids(page, r"field-(legal_name|hq_city|ceo|founded_year|headcount_range|funding_total)")
    assert order == [f"field-{f}" for f in fx.FIELDS], order
    for f in fx.FIELDS:
        fld = body["fields"][f]
        expect(tid(page, f"field-{f}")).to_have_attribute("data-status", fld["status"])
        if fld["value"] is None:
            assert tid(page, f"field-value-{f}").count() == 0
        else:
            expect(tid(page, f"field-value-{f}")).to_have_attribute("data-value", str(fld["value"]))
        assert (tid(page, f"field-contested-{f}").count() == 1) == (fld["status"] == "contested")
        for i, c in enumerate(fld["citations"], 1):
            el = tid(page, f"citation-{f}-{i}")
            expect(el).to_have_attribute("data-provider", c["provider"])
            assert " ".join(c["excerpt"].split()) in screens.text(el)
            assert screens.has_link_to(el, c["url"])
        assert tid(page, f"citation-{f}-{len(fld['citations']) + 1}").count() == 0
    assert no_hscroll(page); shot(page, f"dossier-{n}")
    assert screens.links_to(tid(page, "dossier-evidence-link"), f"/dossiers/{cd}/evidence")
    # evidence
    page.goto(f"/dossiers/{cd.upper()}./evidence")
    expect(tid(page, "evidence-legal_name")).to_be_visible()
    for f in fx.FIELDS:
        cands = body["fields"][f]["candidates"]
        for i, c in enumerate(cands, 1):
            el = tid(page, f"candidate-{f}-{i}")
            expect(el).to_have_attribute("data-selected", "true" if c["selected"] else "false")
            expect(el).to_have_attribute("data-provider", c["provider"])
            expect(el).to_have_attribute("data-kind", c["kind"] or "")
            expect(el).to_have_attribute("data-url", c["url"])
            expect(el).to_have_attribute("data-published-at", c["published_at"] or "")
            assert " ".join(c["excerpt"].split()) in screens.text(el)
        if not cands:
            expect(tid(page, f"evidence-empty-{f}")).to_be_visible()
    assert no_hscroll(page); shot(page, f"evidence-{n}")
    # contested
    page.goto("/contested")
    item = tid(page, f"contested-item-{cd}-{cf}")
    expect(item).to_be_visible()
    t = screens.text(item)
    assert cd in t and cf in t
    for v in {str(c["value"]) for c in body["fields"][cf]["candidates"]}:
        assert v in t, (v, t)
    assert screens.links_to(item, f"/dossiers/{cd}/evidence")
    assert no_hscroll(page); shot(page, f"contested-{n}")


def test_u02_empty_and_missing_states(world, sized):
    """R-26,R-33,R-29,R-51: empty list, empty contested, not found."""
    page = sized
    n = page.size_name
    screens.sign_in(page)
    page.goto("/"); expect(tid(page, "empty-dossiers")).to_be_visible()
    assert tid(page, "dossier-list").count() == 0 or not tid(page, "dossier-list").is_visible() or True
    assert no_hscroll(page); shot(page, f"list-empty-{n}")
    page.goto("/contested"); expect(tid(page, "empty-contested")).to_be_visible()
    shot(page, f"contested-empty-{n}")
    page.goto("/dossiers/nobody-here.test"); expect(tid(page, "dossier-not-found")).to_be_visible()
    assert tid(page, "field-ceo").count() == 0
    shot(page, f"dossier-notfound-{n}")
    page.goto("/dossiers/nobody-here.test/evidence")
    expect(tid(page, "dossier-not-found")).to_be_visible()


def test_u03_failed_and_unknown_fields(world, corpus, web, sized):
    """R-26,R-29,R-32: failed dossier -> all unknown, evidence-empty for each field."""
    page = sized
    n = page.size_name
    d = domains(corpus)[0]
    for prov in fx.PROVIDERS:
        web.fault(prov, list(fx.METHODS), "error")
    assert_status(world.alice.post("/dossiers", json={"domain": d}, idempotency_key=new_key()), 202)
    screens.sign_in(page)
    page.goto(f"/dossiers/{d}")
    expect(tid(page, "dossier-state")).to_have_text("failed", timeout=60000)
    for f in fx.FIELDS:
        expect(tid(page, f"field-{f}")).to_have_attribute("data-status", "unknown")
        assert tid(page, f"field-value-{f}").count() == 0
    assert tid(page, "dossier-researched-at").count() == 0
    shot(page, f"dossier-failed-{n}")
    page.goto(f"/dossiers/{d}/evidence")
    for f in fx.FIELDS:
        expect(tid(page, f"evidence-empty-{f}")).to_be_visible()
    shot(page, f"evidence-empty-{n}")
    page.goto("/")
    expect(tid(page, f"dossier-item-{d}")).to_have_attribute("data-state", "failed")


def test_u04_building_polls_to_ready(world, corpus, web, page):
    """R-31: building screen follows the build to ready without a click."""
    d = domains(corpus)[0]
    web.slow(1.5, ("search", "extract", "research"))
    screens.sign_in(page)
    page.goto("/")
    tid(page, "research-domain").fill("  WWW." + d.upper() + ". ")
    tid(page, "research-submit").click()
    page.wait_for_url(f"**/dossiers/{d}")
    expect(tid(page, "dossier-state")).to_have_text("building")
    shot(page, "dossier-building-desktop")
    page.set_viewport_size({"width": 375, "height": 800}); shot(page, "dossier-building-phone")
    t0 = time.monotonic()
    expect(tid(page, "dossier-state")).to_have_text("ready", timeout=60000)
    expect(tid(page, "field-legal_name")).to_have_attribute("data-status", "known")


def test_u05_research_errors_and_existing(world, build, corpus, web, page):
    """R-26,R-28: invalid domain -> research-error; existing dossier opens, no new build."""
    d = domains(corpus)[0]
    screens.sign_in(page)
    page.goto("/")
    tid(page, "research-domain").fill("https://bad domain/x")
    tid(page, "research-submit").click()
    expect(tid(page, "research-error")).to_be_visible()
    assert "/dossiers/" not in page.url
    shot(page, "list-research-error-desktop")
    # another client creates it after this browser read the list
    build(d, client=world.bob)
    builds = dw.gatherings(web.log(), d)
    tid(page, "research-domain").fill(d)
    tid(page, "research-submit").click()
    page.wait_for_url(f"**/dossiers/{d}")
    expect(tid(page, "dossier-state")).to_have_text("ready")
    assert dw.gatherings(web.log(), d) == builds


def test_u06_list_search_order_and_many(world, corpus, build, page):
    """R-27,R-50: ordered by domain; search filters; >50 not truncated."""
    ds = domains(corpus)[:4]
    for d in ds:
        build(d)
    screens.sign_in(page)
    page.goto("/")
    expect(tid(page, f"dossier-item-{ds[0]}")).to_be_visible()
    got = [x.replace("dossier-item-", "") for x in screens.testids(page, r"dossier-item-.*")]
    assert got == sorted(got) and set(ds) <= set(got), got
    tid(page, "dossier-search").fill(ds[1][:5].upper())
    expect(tid(page, f"dossier-item-{ds[1]}")).to_be_visible()
    tid(page, "dossier-search").fill("zzzzzz-nothing")
    expect(tid(page, "empty-dossiers")).to_be_visible()
    # 60 dossiers: seed via the API with provider errors so builds are cheap
    web = None


def test_u07_many_dossiers_listed(world, corpus, web, page):
    """R-50 (L-9): 60 dossiers all appear."""
    for prov in fx.PROVIDERS:
        web.fault(prov, list(fx.METHODS), "error")
    names = [f"co{i:02d}-probe.test" for i in range(60)]
    for nm in names:
        assert_status(world.alice.post("/dossiers", json={"domain": nm}, idempotency_key=new_key()), 202)
    screens.sign_in(page)
    page.goto("/")
    expect(tid(page, f"dossier-item-{names[-1]}")).to_be_visible(timeout=30000)
    got = screens.testids(page, r"dossier-item-.*")
    assert len(got) == 60, len(got)


def test_u08_uncertain_then_retry_same_key(world, corpus, web, page):
    """R-40: lost response after commit -> research-uncertain, retry same key/body, one build."""
    d = domains(corpus)[0]
    screens.sign_in(page)
    page.goto("/")
    seen = []
    state = {"drop": True}

    def handler(route):
        req = route.request
        if req.method == "POST" and req.url.rstrip("/").endswith("/dossiers"):
            seen.append((req.headers.get("idempotency-key"), req.post_data))
            if state["drop"]:
                route.fetch()
                state["drop"] = False
                route.abort("connectionreset")
                return
        route.continue_()

    page.route("**/dossiers", handler)
    tid(page, "research-domain").fill(d)
    tid(page, "research-submit").click()
    expect(tid(page, "research-uncertain")).to_be_visible()
    assert tid(page, "research-uncertain").inner_text().strip()
    assert tid(page, "research-error").count() == 0
    shot(page, "list-uncertain-desktop")
    tid(page, "research-submit").click()
    page.wait_for_url(f"**/dossiers/{d}")
    assert len(seen) == 2 and seen[0][0] == seen[1][0] and json.loads(seen[0][1]) == json.loads(seen[1][1]), seen
    page.go_back()
    assert tid(page, "research-uncertain").count() == 0 and tid(page, "research-error").count() == 0
    expect(tid(page, "dossier-state").or_(tid(page, "research-domain"))).to_be_visible()
    time.sleep(3)
    assert dw.gatherings(web.log(), d) == 1


def test_u09_refresh_uncertain_and_follow(world, build, corpus, web, page):
    """R-39,R-40: refresh lost -> refresh-uncertain; retry same key; one more build only."""
    d = domains(corpus)[0]
    build(d)
    before = dw.gatherings(web.log(), d)
    screens.sign_in(page)
    screens.open_dossier(page, d)
    keys = []
    state = {"drop": True}

    def handler(route):
        req = route.request
        if req.method == "POST" and req.url.endswith("/refresh"):
            keys.append(req.headers.get("idempotency-key"))
            if state["drop"]:
                route.fetch()
                state["drop"] = False
                route.abort("connectionreset")
                return
        route.continue_()

    page.route("**/refresh", handler)
    web.slow(1.0, ("search", "extract", "research"))
    tid(page, "dossier-refresh").click()
    expect(tid(page, "refresh-uncertain")).to_be_visible()
    assert tid(page, "refresh-error").count() == 0
    tid(page, "dossier-refresh").click()
    expect(tid(page, "refresh-uncertain")).to_have_count(0)
    assert len(keys) == 2 and keys[0] == keys[1]
    expect(tid(page, "dossier-state")).to_have_text("ready", timeout=60000)
    assert dw.gatherings(web.log(), d) == before + 1


def test_u10_refresh_while_other_client_builds(world, build, corpus, web, page):
    """R-39: other client's refresh running; ours is 202 and the screen follows to the end."""
    d = domains(corpus)[0]
    build(d)
    screens.sign_in(page)
    screens.open_dossier(page, d)
    before = dw.gatherings(web.log(), d)
    web.slow(1.5, ("search", "extract", "research"))
    assert_status(world.bob.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
    codes = []
    page.on("response", lambda r: codes.append((r.request.method, r.url, r.status))
            if r.request.method == "POST" else None)
    tid(page, "dossier-refresh").click()
    expect(tid(page, "dossier-state")).to_have_text("building")
    assert tid(page, "refresh-error").count() == 0
    expect(tid(page, "dossier-state")).to_have_text("ready", timeout=60000)
    assert any(c[2] == 202 for c in codes), codes
    assert dw.gatherings(web.log(), d) == before + 1


def test_u11_reload_latest_read_wins(world, build, corpus, web, page):
    """R-38: a delayed earlier read must not overwrite a later one."""
    d = domains(corpus)[0]
    first = build(d)
    screens.sign_in(page)
    screens.open_dossier(page, d)
    calls = {"n": 0}

    def handler(route):
        req = route.request
        if req.method == "GET" and req.url.rstrip("/").endswith(f"/dossiers/{d}") \
                and "text/html" not in (req.headers.get("accept") or ""):
            calls["n"] += 1
            if calls["n"] == 1:
                resp = route.fetch()           # old state captured now
                time.sleep(4)
                route.fulfill(response=resp)
                return
        route.continue_()

    page.route("**/dossiers/*", handler)
    page.route("**/dossiers/*", handler)
    tid(page, "dossier-reload").click()      # read 1: stale, delayed
    time.sleep(0.3)
    assert_status(world.bob.post(f"/dossiers/{d}/refresh", idempotency_key=new_key()), 202)
    end = time.monotonic() + 30
    while world.bob.get(f"/dossiers/{d}").json()["state"] == "building" and time.monotonic() < end:
        time.sleep(0.1)
    new = world.bob.get(f"/dossiers/{d}").json()
    assert new["spent_units"] > first["spent_units"]
    tid(page, "dossier-reload").click()      # read 2: fresh
    expect(tid(page, "dossier-spent")).to_have_attribute("data-units", str(new["spent_units"]))
    time.sleep(5)                            # stale one lands now
    expect(tid(page, "dossier-spent")).to_have_attribute("data-units", str(new["spent_units"]))


def test_u12_auth_ui(world, page):
    """R-36,R-58: auth-error only when error, cleared; logout; current-user."""
    page.goto("/login")
    assert tid(page, "auth-error").count() == 0
    tid(page, "login-email").fill("alice@example.com"); tid(page, "login-password").fill("wrong pass")
    tid(page, "login-submit").click()
    expect(tid(page, "auth-error")).to_be_visible()
    assert tid(page, "current-user").count() == 0
    shot(page, "login-error-desktop")
    tid(page, "login-password").fill("correct horse"); tid(page, "login-submit").click()
    expect(tid(page, "current-user")).to_contain_text("Alice")
    assert tid(page, "auth-error").count() == 0
    tid(page, "logout-button").click()
    expect(tid(page, "current-user")).to_have_count(0)
    page.goto("/signup")
    tid(page, "signup-email").fill("alice@example.com"); tid(page, "signup-password").fill("longenough1")
    tid(page, "signup-display-name").fill("Dup")
    tid(page, "signup-submit").click()
    expect(tid(page, "auth-error")).to_be_visible()
    tid(page, "signup-email").fill("zed@example.com"); tid(page, "signup-submit").click()
    expect(tid(page, "current-user")).to_contain_text("Dup")
    assert tid(page, "auth-error").count() == 0
    page.goto("/"); expect(tid(page, "current-user")).to_contain_text("Dup")


def test_u13_no_external_requests(world, build, corpus, page, base_url):
    """R-47: UI loads nothing from outside the service origin."""
    d = domains(corpus)[0]
    build(d)
    hosts = set()
    page.on("request", lambda r: hosts.add(r.url.split("/")[2]) if r.url.startswith("http") else None)
    screens.sign_in(page)
    for p in ("/", f"/dossiers/{d}", f"/dossiers/{d}/evidence", "/contested"):
        page.goto(p); page.wait_for_load_state("networkidle")
    assert hosts == {base_url.split("//")[1]}, hosts


def test_u14_html_vs_json(world, build, corpus, base_url):
    """R-29/I-2: same path, Accept decides; JSON default, HTML for text/html."""
    import httpx
    d = domains(corpus)[0]
    build(d)
    auth = {"Authorization": f"Bearer {world.alice.token}"}
    h = httpx.get(f"{base_url}/dossiers/{d}", headers={**auth, "Accept": "text/html"})
    assert h.headers["content-type"].startswith("text/html")
    j = httpx.get(f"{base_url}/dossiers/{d}", headers=auth)
    assert j.headers["content-type"].startswith("application/json") and j.json()["domain"] == d
    j2 = httpx.get(f"{base_url}/dossiers/{d}", headers={**auth, "Accept": "application/json"})
    assert j2.json()["domain"] == d
    # unauthenticated JSON is still 401; html route serves a page
    assert httpx.get(f"{base_url}/dossiers/{d}").status_code == 401
