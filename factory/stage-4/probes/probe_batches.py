"""Examiner probes, stage 4: batches (R-38..R-45, R-52..R-59, R-61..R-63). From the spec only.
Not dependent on builder-a's build side."""
import time

import httpx
import pytest

import fixtures as fx
from harness.http import assert_status, assert_error, new_key

pytestmark = pytest.mark.stage(4)


def post(c, body, key=None):
    return c.post("/batches", json=body, idempotency_key=key or new_key())


def doms(corpus, n):
    return corpus.plain()[:n]


def dossier(c, d):
    return assert_status(c.get(f"/dossiers/{d}"), 200).json()


# --- validation (E4-48)
@pytest.mark.parametrize("body", [
    {"budget_units": 100},
    {"domains": [], "budget_units": 100},
    {"domains": ["not a domain!"], "budget_units": 100},
    {"domains": ["a.test", "A.TEST"], "budget_units": 100},
    {"domains": ["a.test"]},
    {"domains": ["a.test"], "budget_units": 0},
    {"domains": ["a.test"], "budget_units": 100001},
    {"domains": ["a.test"], "budget_units": "100"},
    {"domains": ["a.test"], "budget_units": True},
    {"domains": ["a.test"], "budget_units": 1.5},
    {"domains": ["a.test"], "budget_units": None},
    {"domains": [f"d{i}.test" for i in range(51)], "budget_units": 100},
])
def test_b01_validation(world, body):
    assert_error(post(world.alice, body), 422, "validation_failed")


def test_b02_requires_key_and_auth(world):
    r = world.alice.post("/batches", json={"domains": ["a.test"], "budget_units": 5})
    assert r.status_code in (400, 422), r.text
    r = httpx.post(world.alice.base_url + "/batches",
                   json={"domains": ["a.test"], "budget_units": 5},
                   headers={"Idempotency-Key": new_key()})
    assert r.status_code == 401, r.text


def test_b03_shape_order_and_normalisation(world, corpus, run_batch):
    d = doms(corpus, 2)
    created, done = run_batch([d[1].upper(), d[0]], 400)
    assert [x["domain"] for x in created["dossiers"]] == [d[1], d[0]]
    assert created["batch_id"].startswith("b_")
    assert created["budget_units"] == 400 and created["spent_units"] >= 0
    fx.assert_batch(done, [d[1], d[0]], 400)


def test_b04_unknown_batch_404_and_ownership(world, corpus, run_batch):
    assert_error(world.alice.get("/batches/b_999999"), 404, "not_found")
    created, _ = run_batch(doms(corpus, 1), 200)
    assert_error(world.bob.get(f"/batches/{created['batch_id']}"), 404, "not_found")
    assert_status(world.alice.get(f"/batches/{created['batch_id']}"), 200)


def test_b05_idempotency(world, corpus):
    body = {"domains": doms(corpus, 1), "budget_units": 200}
    k = new_key()
    r1 = assert_status(post(world.alice, body, k), 202)
    r2 = assert_status(post(world.alice, body, k), 200)
    assert r1.json()["batch_id"] == r2.json()["batch_id"]
    r3 = post(world.alice, {**body, "budget_units": 201}, k)
    assert_error(r3, 409, "idempotency_key_reuse")
    r4 = assert_status(post(world.alice, body, new_key()), 202)
    assert r4.json()["batch_id"] != r1.json()["batch_id"]


def test_b06_budget_never_exceeded_and_accounting(world, web, corpus, finish_batch):
    ds = doms(corpus, 4)
    web.reset()
    created = assert_status(post(world.alice, {"domains": ds, "budget_units": 25}), 202).json()
    done = finish_batch(created["batch_id"])
    assert done["state"] == "done"
    assert done["spent_units"] <= 25
    billed = web.units()
    assert billed <= 25, f"mock billed {billed} > budget 25"
    assert done["spent_units"] >= billed, (done["spent_units"], billed)
    for d in ds:
        assert dossier(world.alice, d)["state"] in ("ready", "failed")


def test_b07_per_build_cap_80(world, web, corpus, run_batch):
    ds = doms(corpus, 2)
    web.reset()
    _, done = run_batch(ds, 100000)
    spent = [dossier(world.alice, d)["spent_units"] for d in ds]
    assert all(s <= 80 for s in spent), spent
    assert done["spent_units"] == sum(spent)
    assert web.units() <= done["spent_units"]


def test_b08_existing_dossier_not_researched(world, web, corpus, build, run_batch):
    d0, d1 = doms(corpus, 2)
    build(d0)
    before = dossier(world.alice, d0)
    web.reset()
    created, _ = run_batch([d0, d1], 200)
    assert created["dossiers"][0]["state"] in ("ready", "failed")
    assert dossier(world.alice, d0)["spent_units"] == before["spent_units"]
    assert not [c for c in web.log() if d0 in str(c)], "batch called providers for an existing dossier"


def test_b09_all_existing_batch_done_and_free(world, corpus, build, finish_batch):
    d0 = doms(corpus, 1)[0]
    build(d0)
    created = assert_status(post(world.alice, {"domains": [d0], "budget_units": 50}), 202).json()
    assert created["spent_units"] == 0
    assert finish_batch(created["batch_id"])["state"] == "done"


def test_b11_batch_survives_restart(world, corpus, run_batch, restart, api):
    ds = doms(corpus, 2)
    created, done = run_batch(ds, 300)
    restart()
    alice = api().authenticate(fx.ALICE["email"], fx.ALICE["password"])
    assert assert_status(alice.get(f"/batches/{created['batch_id']}"), 200).json() == done
    nxt = assert_status(post(alice, {"domains": ["zz-new.test"], "budget_units": 10}), 202).json()
    assert nxt["batch_id"] != created["batch_id"]


def test_b12_restart_mid_build(world, web, corpus, restart, api):
    ds = doms(corpus, 3)
    web.slow(1.0, ("search", "extract", "research"))
    created = assert_status(post(world.alice, {"domains": ds, "budget_units": 150}), 202).json()
    time.sleep(1.5)
    restart()
    web.normal()
    alice = api().authenticate(fx.ALICE["email"], fx.ALICE["password"])
    deadline = time.monotonic() + 10
    while True:
        b = assert_status(alice.get(f"/batches/{created['batch_id']}"), 200).json()
        if b["state"] == "done" or time.monotonic() > deadline:
            break
        time.sleep(0.2)
    assert b["state"] == "done", f"batch not done 10s after /health 200: {b}"
    assert b["spent_units"] <= 150
    log = web.log()
    billed = sum(c["cost"] for c in log)
    per = {}
    for c in log:
        per[c.get("provider")] = per.get(c.get("provider"), 0) + c["cost"]
    assert billed <= 150, f"providers billed {billed} > batch budget 150 across restart; {per}; sample {log[:2]}"
    assert b["spent_units"] >= billed, (b["spent_units"], billed)
    for d in ds:
        body = dossier(alice, d)
        assert body["state"] in ("ready", "failed")
        assert body["spent_units"] <= 80
    assert_status(alice.post(f"/dossiers/{ds[0]}/refresh", idempotency_key=new_key()), 202)
