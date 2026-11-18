"""Measure cost per correct result of build strategies against the local mock web (stage 2, W-7: rendered vs plain
extract, with and without 429s).

    python measure.py [--mock http://localhost:18080] [--token local-admin] [--corpus <dir with key.json>]
                      [--out ../factory/stage-2/measure-raw.md] [--epochs 0,1] [--weather]

Needs the mock web running (see challenges/dossier/web/README.md).  For every company in key.json and every
epoch it resets the mock, runs each strategy's build against `<mock>/nimble`, and scores the result against
key.json["expected"]["1"][epoch]:

  correct field   = known, value equals the expected value (or one of the accepted values)
  wrong field     = known, value not accepted
  missed field    = unknown although an expected value exists
  invalid cite    = a citation whose excerpt is not in text the mock log says it served for that url,
                    or that does not satisfy support.supports
  cost per correct result = units spent (mock log ground truth) / correct fields
Raw numbers per company/epoch/strategy are written to the output markdown file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STRATEGIES = {
    "R rendered extract + research + followups": {},
    "P plain extract + research + followups": {"render": False},
    "R0 rendered extract + research, no followups": {"followups": False},
    "R1 rendered extract, no research, followups": {"research": False},
}


def admin(base, token, path, body=None, get=False):
    req = urllib.request.Request(base + "/_mock/" + path, data=None if get else json.dumps(body or {}).encode(),
                                 headers={"X-Mock-Admin": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def accepted(expected_value):
    return expected_value if isinstance(expected_value, list) else [expected_value]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", default=os.environ.get("MOCK_URL", "http://localhost:18080"))
    ap.add_argument("--token", default=os.environ.get("MOCK_ADMIN_TOKEN", "local-admin"))
    ap.add_argument("--corpus", default=os.path.expanduser(
        "~/hack/sf-buildathon-2026/challenges/dossier/web/corpus/sample"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "factory", "stage-2", "measure-raw.md"))
    ap.add_argument("--epochs", default="0,1")
    ap.add_argument("--only", default="")
    ap.add_argument("--weather", action="store_true", help="turn the mock's seeded 429 weather on for every build")
    ap.add_argument("--web", default=os.path.expanduser("~/hack/sf-buildathon-2026/challenges/dossier/web"))
    args = ap.parse_args()

    os.environ.setdefault("NIMBLE_API_KEY", "local")
    os.environ["NIMBLE_BASE_URL"] = args.mock + "/nimble"
    import build
    import support
    sys.path.insert(0, args.web)
    from mockweb.corpus import load as load_corpus
    corpus = load_corpus(args.corpus)

    with open(os.path.join(args.corpus, "key.json"), encoding="utf8") as fh:
        key = json.load(fh)
    epochs = [int(e) for e in args.epochs.split(",")]
    rows = []
    for dom in sorted(key):
        if args.only and args.only not in dom:
            continue
        exp_by_epoch = (key[dom].get("expected") or {}).get("2")
        if not exp_by_epoch:
            continue
        for ep in epochs:
            expected = exp_by_epoch.get(str(ep))
            if not expected:
                continue
            for sname, kw in STRATEGIES.items():
                admin(args.mock, args.token, "reset", {"epoch": ep})
                if args.weather:
                    admin(args.mock, args.token, "weather", {"on": True})
                t0 = time.time()
                res = build.run_build(dom, "2026-03-01T09:00:00+00:00", lambda: False, options=build.Options(**kw))
                dt = time.time() - t0
                calls = admin(args.mock, args.token, "log", get=True)["calls"]
                log_cost = sum(c["cost"] for c in calls)
                dom_searches = sum(1 for c in calls if c["method"] == "search" and c["query"] == dom
                                   and c["status"] == 200)
                served: dict[str, list[str]] = {}
                for c in calls:
                    for s in c.get("served") or []:
                        served.setdefault(s.get("url") or "", []).append(support.collapse_ws(s.get("text") or ""))
                correct = wrong = missed = invalid = 0
                if res.fields:
                    for f in support.FIELDS:
                        got = res.fields[f]
                        exp = expected.get(f)
                        if got["status"] == "known":
                            if exp is not None and got["value"] in accepted(exp):
                                correct += 1
                            else:
                                wrong += 1
                            for c in got["citations"]:
                                ex = support.collapse_ws(c["excerpt"])
                                pg = corpus.page(ep, c["url"])
                                ok = pg is not None and ex in support.collapse_ws(
                                    support.split_header(pg.initial)[1])  # text a browser shows after load
                                ok = ok and support.supports(f, got["value"], c["excerpt"], dom)
                                if not ok:
                                    invalid += 1
                        elif exp is not None:
                            missed += 1
                # candidate recall: supports from key.json that a browser shows (page text at this epoch)
                want = hit = 0
                have = {(c["url"], f, json.dumps(c["value"])) for f in support.FIELDS
                        for c in (res.fields or {}).get(f, {}).get("candidates", [])}
                for sp in key[dom].get("supports") or []:
                    pg = corpus.page(ep, sp["url"])
                    if pg is None or support.collapse_ws(sp["excerpt"]) not in support.collapse_ws(
                            support.split_header(pg.initial)[1]):
                        continue
                    want += 1
                    hit += (sp["url"], sp["field"], json.dumps(sp["value"])) in have
                refused = sum(1 for c in calls if c['status'] == 429)
                rows.append(dict(refused=refused, want=want, hit=hit, domain=dom, epoch=ep, strategy=sname, outcome=res.outcome, spent=res.spent_units,
                                 log_cost=log_cost, calls=len(calls), dom_searches=dom_searches, correct=correct,
                                 wrong=wrong, missed=missed, invalid=invalid, seconds=round(dt, 2)))
                print(rows[-1], flush=True)

    lines = ["# Stage 2 measurement (raw)", "",
             f"Mock: {args.mock}  corpus: sample  epochs: {args.epochs}  generated by stage-2/measure.py (weather: {args.weather})", "",
             "| domain | epoch | strategy | outcome | spent | mock-log cost | calls | domain searches | correct | "
             "wrong | missed | invalid cites | candidates found/expected | 429s | seconds |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['domain']} | {r['epoch']} | {r['strategy']} | {r['outcome']} | {r['spent']} | "
                     f"{r['log_cost']} | {r['calls']} | {r['dom_searches']} | {r['correct']} | {r['wrong']} | "
                     f"{r['missed']} | {r['invalid']} | {r['hit']}/{r['want']} | {r['refused']} | {r['seconds']} |")
    lines += ["", "## Totals per strategy", "",
              "| strategy | builds | units (mock log) | correct | wrong | missed | invalid cites | candidates found/expected | 429s | max spend | "
              "cost per correct result |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for sname in STRATEGIES:
        rs = [r for r in rows if r["strategy"] == sname]
        if not rs:
            continue
        units = sum(r["log_cost"] for r in rs)
        correct = sum(r["correct"] for r in rs)
        cpc = f"{units / correct:.2f}" if correct else "n/a"
        lines.append(f"| {sname} | {len(rs)} | {units} | {correct} | {sum(r['wrong'] for r in rs)} | "
                     f"{sum(r['missed'] for r in rs)} | {sum(r['invalid'] for r in rs)} | "
                     f"{sum(r['hit'] for r in rs)}/{sum(r['want'] for r in rs)} | {sum(r['refused'] for r in rs)} | "
                     f"{max(r['log_cost'] for r in rs)} | {cpc} |")
    mismatches = [r for r in rows if r["spent"] != r["log_cost"] or r["dom_searches"] != 1]
    lines += ["", "Builds whose own spend differs from the mock log, or without exactly one domain search: "
                  f"{len(mismatches)}"]
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
