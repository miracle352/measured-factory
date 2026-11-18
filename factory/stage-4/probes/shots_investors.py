"""Headless-browser screenshots of the investors section (stage 4, R-37).

Starts stage-4/server.py on a temp state dir, signs a fake token into localStorage and answers the JSON API
calls the screens make with fixed dossiers (known investors, unknown investors, contested field elsewhere).
usage: python shots_investors.py <stage-4 dir> <out dir>
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

SRC, OUT = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
PORT = 18734
BASE = f"http://127.0.0.1:{PORT}"


def cand(v, url, kind, origin, sel):
    return {"value": v, "url": url, "excerpt": f"Investors in Acme Robotics include {v}.", "provider": "nimble",
            "kind": kind, "published_at": "2026-02-01T00:00:00+00:00", "retrieved_at": "2026-03-01T09:00:00+00:00",
            "true_from": "2026-02-01", "origin": origin, "selected": sel}


def field(value, status="unknown", cands=(), origins=(), corro=False):
    return {"value": value, "status": status, "true_from": "2026-02-01" if value else None,
            "citations": [{"url": c["url"], "excerpt": c["excerpt"], "provider": c["provider"]}
                          for c in cands if c["selected"]],
            "candidates": list(cands), "origins": list(origins), "corroborated": corro,
            "corroborated_since": "2026-03-01T09:00:00+00:00" if corro else None}


def six(contested=False):
    f = {n: field(None) for n in ("legal_name", "hq_city", "ceo", "founded_year", "headcount_range",
                                  "funding_total")}
    f["ceo"] = field("Dana Ruiz", "known", [dict(cand("Dana Ruiz", "https://acme-robotics.test/about", "own",
                                                       "acme-robotics.test", True))])
    if contested:
        f["hq_city"] = field("Porto", "contested", [cand("Porto", "https://acme-robotics.test/c", "own", "a.test", True),
                                                    cand("Lisbon", "https://n.test/c", "news", "n.test", False)])
    f["executives"] = field(None)
    return f


KNOWN = dict(six(), investors={**field(
    ["Bluebird Capital", "Northwind Ventures"], "known",
    [cand("Bluebird Capital", "https://acme-robotics.test/investors", "own", "acme-robotics.test", True),
     cand("Northwind Ventures", "https://dealwire.test/a", "news", "dealwire.test", True),
     cand("Northwind Ventures", "https://registry.test/b", "filing", "registry.test", True)],
    ["acme-robotics.test", "dealwire.test", "registry.test"], False)})
DOSSIERS = {
    "acme-robotics.test": dict(KNOWN, domain="acme-robotics.test", state="ready", spent_units=40,
                               researched_at="2026-03-01T09:00:00+00:00", fields=dict(KNOWN, **{}), build_id=None),
    "brightgear.test": {"domain": "brightgear.test", "state": "ready", "spent_units": 10,
                        "researched_at": "2026-03-01T09:00:00+00:00",
                        "fields": dict(six(contested=True), investors=field(None))},
}
for d in DOSSIERS.values():
    d.pop("build_id", None)
    for k in list(d):
        if k in ("legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total", "executives",
                 "investors"):
            d.pop(k)
DOSSIERS["acme-robotics.test"]["fields"] = KNOWN


def main():
    state = tempfile.mkdtemp()
    env = dict(os.environ, PORT=str(PORT), DOSSIER_STATE_DIR=state)
    srv = subprocess.Popen([sys.executable, "server.py"], cwd=SRC, env=env, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(BASE + "/health", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        with sync_playwright() as p:
            br = p.chromium.launch()
            for name, (w, h) in {"phone": (375, 800), "desktop": (1280, 900)}.items():
                page = br.new_page(viewport={"width": w, "height": h})

                def handler(route):
                    req = route.request
                    if "text/html" in (req.headers.get("accept") or "") or req.resource_type == "document":
                        return route.continue_()
                    path = req.url[len(BASE):].split("?")[0]
                    if path == "/dossiers":
                        return route.fulfill(status=200, content_type="application/json", body=json.dumps(
                            {"dossiers": [{"domain": d, "state": "ready"} for d in DOSSIERS], "has_more": False}))
                    d = path.split("/")[2] if path.startswith("/dossiers/") else None
                    if d in DOSSIERS:
                        return route.fulfill(status=200, content_type="application/json",
                                             body=json.dumps(DOSSIERS[d]))
                    return route.continue_()

                page.route("**/*", handler)
                page.goto(BASE + "/login")
                page.evaluate("localStorage.setItem('dossier.token','x');localStorage.setItem('dossier.user','Ada')")
                for label, path in (("known", "/dossiers/acme-robotics.test"),
                                    ("unknown", "/dossiers/brightgear.test"), ("contested", "/contested")):
                    page.goto(BASE + path)
                    page.wait_for_timeout(1500)
                    ok = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
                    tids = page.evaluate("[...document.querySelectorAll('[data-testid]')].map(e=>e.dataset.testid)"
                                         ".filter(t=>/investor/i.test(t))")
                    text = page.inner_text("body")
                    print(name, label, "no-overflow", ok, "investor-testids", tids,
                          "internal-keys", [k for k in ("origins", "corroborated", "investors", "selected")
                                            if k in text])
                    page.screenshot(path=str(OUT / f"investors-{label}-{name}.png"), full_page=True)
                page.close()
            br.close()
    finally:
        srv.terminate()


main()
