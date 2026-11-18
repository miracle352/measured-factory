"""Examiner probes (browser), stage 3. Spec-only: the screens that show `executives`
(stage-3 spec, Executives: no six-field data-testids for it; /contested ignores it).
Screens are saved under factory/stage-3/screens/ as live-*.png (live service, not mocked)."""
import os
import pathlib

import pytest
from playwright.sync_api import expect

import fixtures as fx
import screens
from harness.http import assert_status

pytestmark = pytest.mark.stage(3)
SHOTS = pathlib.Path(os.environ.get("SHOTS") or ("/out/shots" if os.path.isdir("/out") else "/tmp/shots"))
SIZES = {"phone": (375, 800), "desktop": (1280, 900)}


def shot(page, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"live-{name}.png"), full_page=True)


def domains(corpus):
    return sorted(d for d in corpus.key if "expected" in corpus.key[d])


@pytest.fixture(params=list(SIZES), ids=list(SIZES))
def sized(request, page):
    w, h = SIZES[request.param]
    page.set_viewport_size({"width": w, "height": h})
    page.size_name = request.param
    return page


def ex_testids(page):
    return page.evaluate("""() => [...document.querySelectorAll('[data-testid]')]
        .map(e => e.getAttribute('data-testid')).filter(t => /executives/i.test(t))""")


def test_u01_executives_on_dossier_and_evidence(world, build, corpus, sized):
    page = sized
    n = page.size_name
    screens.sign_in(page)
    shown = unknown = 0
    for d in domains(corpus):
        body = build(d)
        ex = body["fields"]["executives"]
        page.goto(f"/dossiers/{d}")
        expect(page.get_by_test_id("dossier-state")).to_have_text("ready")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), d
        assert ex_testids(page) == [], (d, ex_testids(page))
        text = page.inner_text("body")
        if ex["value"]:
            for m in ex["value"]:
                assert m["name"] in text, (d, m)
            shown += 1
            if shown <= 3:
                shot(page, f"{n}-dossier-{d}-exec-{ex['status']}")
        else:
            unknown += 1
            if unknown == 1:
                shot(page, f"{n}-dossier-{d}-exec-unknown")
        page.goto(f"/dossiers/{d}/evidence")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), d
        assert ex_testids(page) == [], (d, ex_testids(page))
        text = page.inner_text("body")
        for c in ex["candidates"]:
            assert c["value"] in text, (d, c["value"])
        if ex["value"] and shown <= 3:
            shot(page, f"{n}-evidence-{d}-exec-{ex['status']}")
    assert shown, "no corpus company has executives; nothing covered"


def test_u02_contested_ignores_executives(world, build, corpus, sized):
    page = sized
    n = page.size_name
    bodies = {d: build(d) for d in domains(corpus)}
    six = {(d, f) for d, b in bodies.items() for f in fx.FIELDS
           if b["fields"][f]["status"] == "contested"}
    screens.sign_in(page)
    page.goto("/contested")
    if six:
        expect(page.get_by_test_id("contested-list")).to_be_visible()
        expect(page.locator('[data-testid^="contested-item-"]').first).to_be_visible()
    else:
        expect(page.get_by_test_id("empty-contested")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert ex_testids(page) == []
    items = page.evaluate("""() => [...document.querySelectorAll('[data-testid^="contested-item-"]')]
        .map(e => e.getAttribute('data-testid'))""")
    assert not [i for i in items if i.endswith("-executives")], items
    six = {(d, f) for d, b in bodies.items() for f in fx.FIELDS
           if b["fields"][f]["status"] == "contested"}
    assert len(items) == len(six), (items, six)
    if not six:
        expect(page.get_by_test_id("empty-contested")).to_be_visible()
    shot(page, f"{n}-contested")
