#!/usr/bin/env python3
"""Spec-only probes for Dossier stage 1. Stdlib only.

Usage: SVC=http://localhost:8000 MOCK=http://localhost:8080 ADMIN=local-admin \
       python3 probe.py [selftest|all|<probe-name>...]
Exit code 1 if any probe fails. Every failure prints the exam-list id (E-xx).
"""
import json, os, re, sys, time, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

SVC = os.environ.get("SVC", "http://localhost:8000").rstrip("/")
MOCK = os.environ.get("MOCK", "http://localhost:8080").rstrip("/")
ADMIN = os.environ.get("ADMIN", "local-admin")
FAILS = []
PASSES = [0]


def req(method, url, body=None, headers=None, raw=None, timeout=15):
    h = dict(headers or {})
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            t = resp.read()
            return resp.status, (json.loads(t) if t else None), resp.headers
    except urllib.error.HTTPError as e:
        t = e.read()
        try:
            return e.code, json.loads(t) if t else None, e.headers
        except Exception:
            return e.code, t, e.headers


def svc(method, path, body=None, tok=None, key=None, raw=None, headers=None):
    h = dict(headers or {})
    if tok:
        h["Authorization"] = "Bearer " + tok
    if key is not None:
        h["Idempotency-Key"] = key
    return req(method, SVC + path, body, h, raw)


def mock(method, path, body=None):
    return req(method, MOCK + path, body, {"X-Mock-Admin": ADMIN})


def check(cond, eid, msg):
    if cond:
        PASSES[0] += 1
    else:
        FAILS.append((eid, msg))
        print(f"  FAIL {eid}: {msg}")


def err(r, status, code, eid, what):
    s, b, _ = r
    ok = s == status and isinstance(b, dict) and isinstance(b.get("error"), dict) \
        and b["error"].get("code") == code and "message" in b["error"]
    check(ok, eid, f"{what}: expected {status} {code}, got {s} {str(b)[:120]}")


FIX = {"now": "2026-03-01T09:00:00+00:00", "users": [
    {"id": "u_ada", "email": "ada@example.com", "password": "correct horse", "display_name": "Ada"},
    {"id": "u_bob", "email": "bob@example.com", "password": "correct horse", "display_name": "Bob"}]}


def reset(fix=None, epoch=0):
    mock("POST", "/_mock/reset", {"epoch": epoch})
    s, b, _ = svc("POST", "/_test/reset", fix or FIX)
    assert s == 204, f"reset gave {s} {b}"


def login(email="ada@example.com"):
    s, b, _ = svc("POST", "/auth/login", {"email": email, "password": "correct horse"})
    assert s == 200, (s, b)
    return b["token"]


def wait_state(tok, dom, want=("ready", "failed"), t=30):
    end = time.time() + t
    while time.time() < end:
        s, b, _ = svc("GET", "/dossiers/" + dom, tok=tok)
        if s == 200 and b["state"] in want:
            return b
        time.sleep(0.2)
    return None


def calls():
    return mock("GET", "/_mock/log")[1]["calls"]


# ---------------------------------------------------------------- Appendix A reference
LEGAL = ["Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC", "GmbH", "AG", "KG",
         "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.", "S.A.", "S.A.S.", "S.L.", "S.r.l.",
         "S.p.A.", "s.r.o.", "a.s.", "K.K."]
PH = {
    "legal_name": ["legal name", "registered name", "registered as", "registered company", "legal entity", "name of record"],
    "hq_city": ["headquartered in", "headquarters in", "head office in", "based in", "registered office in", "registered seat in"],
    "ceo": ["chief executive officer", "chief executive", "CEO"],
    "founded_year": ["founded", "founding", "established", "incorporated"],
    "headcount_range": ["employs", "employees", "staff", "people", "headcount", "workforce"],
    "funding_total": ["raised", "funding", "invested", "investment"],
}
NEG = ["in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to", "aims to", "seeking", "could",
       "would", "might", "reportedly", "rumoured", "former", "formerly", "will become", "not"]
BUCKETS = [(1, 10, "1-10"), (11, 50, "11-50"), (51, 200, "51-200"), (201, 500, "201-500"), (501, 1000, "501-1000"),
           (1001, 5000, "1001-5000"), (5001, 10000, "5001-10000"), (10001, 10 ** 18, "10001+")]


def _w(s, a, b):
    return (a == 0 or not s[a - 1].isalnum()) and (b >= len(s) or not s[b].isalnum())


def find_words(s, phrase):
    out = []
    pat = re.compile(re.escape(phrase).replace(r"\ ", " "), re.I)
    for m in pat.finditer(s):
        if _w(s, m.start(), m.end()):
            out.append((m.start(), m.end()))
    return out


def split_sentences(text):
    sents = []
    for line in re.split(r"\r\n|\r|\n", text):
        i, start, n = 0, 0, len(line)
        while i < n:
            c = line[i]
            if c in ".!?":
                j = i + 1
                while j < n and line[j] in "\"”’)":
                    j += 1
                if j < n and line[j].isspace() or False:
                    ends_legal = False
                    if c == ".":
                        for suf in LEGAL:
                            if suf.endswith(".") and line[:i + 1].endswith(suf):
                                a = i + 1 - len(suf)
                                if a == 0 or not line[a - 1].isalnum():
                                    ends_legal = True
                    if not ends_legal:
                        sents.append(line[start:j])
                        start = j
                        i = j
                        continue
                i = j
                continue
            i += 1
        sents.append(line[start:])
    return [x.strip() for x in sents if x.strip()]


NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"


def numbers(s):
    out = []
    for m in re.finditer(NUM, s):
        a, b = m.start(), m.end()
        if a > 0 and (s[a - 1].isalnum() or (s[a - 1] in ",." and a > 1 and s[a - 2].isdigit())):
            continue
        if b < len(s) and (s[b].isalpha() or s[b].isdigit() or (s[b] in ",." and b + 1 < len(s) and s[b + 1].isdigit())):
            continue
        out.append((a, b, m.group()))
    return out


SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9}


def amounts(s):
    """returns list of (start,end,value-or-None-if-not-whole)"""
    res = []
    for m in re.finditer(r"(?i)(?:US\$|USD|\$)\s?(" + NUM + r")(?:(mn|bn|k|m)|\s(thousand|million|billion))?", s):
        if m.start() > 0 and s[m.start() - 1].isalnum():
            continue
        if m.end() < len(s) and s[m.end()].isalnum():
            continue
        # number tokens must be a valid number
        n = m.group(1)
        sc = (m.group(2) or m.group(3) or "").lower()
        res.append((m.start(), m.end(), n, sc))
    for m in re.finditer(r"(?i)(" + NUM + r")(?:\s(thousand|million|billion))?\s(?:US\s)?dollars", s):
        if m.start() > 0 and s[m.start() - 1].isalnum():
            continue
        if m.end() < len(s) and s[m.end()].isalnum():
            continue
        res.append((m.start(), m.end(), m.group(1), (m.group(2) or "").lower()))
    out = []
    from decimal import Decimal
    for a, b, n, sc in res:
        v = Decimal(n.replace(",", "")) * Decimal(int(SCALE.get(sc, 1)))
        out.append((a, b, int(v) if v == v.to_integral_value() else None))
    return out


def values_for(field, s, company):
    """list of normalised values the sentence contains in field's format (None entries = non-value amount)"""
    name = company.split(".")[0].replace("-", " ")
    if field == "founded_year":
        am = amounts(s)
        out = []
        for a, b, n in numbers(s):
            if re.fullmatch(r"\d{4}", n) and 1800 <= int(n) <= 2099 and not any(x <= a < y for x, y, _ in am):
                out.append(int(n))
        return out
    if field == "headcount_range":
        am = amounts(s)
        out = []
        for a, b, n in numbers(s):
            if "." in n or any(x <= a < y for x, y, _ in am):
                continue
            v = int(n.replace(",", ""))
            if v >= 1:
                out.append(next(r for lo, hi, r in BUCKETS if lo <= v <= hi))
        return out
    if field == "funding_total":
        return [v for _, _, v in amounts(s)] if amounts(s) else []
    if field == "hq_city":
        out = []
        for p in PH["hq_city"]:
            for a, b in find_words(s, p):
                m = re.match(r" ((?:[^\W\d_a-z][a-zà-ÿ\u0100-\uffff]+)(?:[ -][^\W\d_a-z][a-z\u00df-\uffff]+)*)", s[b:])
                if m and m.group(1)[0].isupper():
                    out.append(m.group(1))
        return out
    if field == "ceo":
        t = s
        for p in PH["ceo"] + [name]:
            for a, b in sorted(find_words(t, p), reverse=True):
                t = t[:a] + " | " + t[b:]
        out = []
        for seg in t.split("|"):
            cw = [(m.start(), m.end()) for m in re.finditer(r"(?<![^\W\d_])[^\W\d_a-z][a-z\u00df-\uffff]+(?![^\W\d_])", seg) if _w(seg, m.start(), m.end()) and seg[m.start()].isupper()]
            i = 0
            while i < len(cw):
                j = i
                while j + 1 < len(cw) and seg[cw[j][1]:cw[j + 1][0]] == " ":
                    j += 1
                run = j - i + 1
                if 2 <= run <= 3:
                    out.append(seg[cw[i][0]:cw[j][1]])
                i = j + 1
        return out
    if field == "legal_name":
        out = []
        for base in (name, company):
            for a, b in find_words(s, base):
                pos = b
                best = None
                while True:
                    for suf in LEGAL:
                        for pre in (", ", " "):
                            if s.startswith(pre + suf, pos):
                                e = pos + len(pre) + len(suf)
                                if not (e < len(s) and s[e].isalnum()):
                                    cand = s[a:e]
                                    if best is None or len(cand) < len(best):
                                        best = cand
                    if best:
                        break
                    m = re.match(r" ([^\W\d_][^\W\d_]+)(?![^\W\d_]|\d)", s[pos:])
                    if not m or not (m.group(1)[0].isupper() and (m.group(1)[1:].islower() or m.group(1).isupper())):
                        break
                    pos += m.end()
                if best:
                    out.append(best)
        return out
    return []


def supports(excerpt, field, value, domain):
    ex = re.sub(r"\s+", " ", excerpt).strip()
    if len(split_sentences(ex)) != 1:
        return False
    name = domain.split(".")[0].replace("-", " ")
    if not (find_words(ex, domain) or find_words(ex, name)):
        return False
    if not any(find_words(ex, p) for p in PH[field]):
        return False
    if any(find_words(ex, p) for p in NEG):
        return False
    vals = values_for(field, ex, domain)
    if not vals:
        return False
    return all(v == value for v in vals)


def selftest():
    d = "acme-robotics.test"
    cases = [
        ("Dana Ruiz has led Acme Robotics as chief executive since 2021.", "ceo", "Dana Ruiz", True),
        ("Acme Robotics CEO: Sam Ortiz.", "ceo", "Sam Ortiz", True),
        ("Acme Robotics was founded in 2014.", "founded_year", 2014, True),
        ("Acme Robotics employs about 120 people.", "headcount_range", "51-200", True),
        ("Acme Robotics is reportedly in talks to raise $40M.", "funding_total", 40000000, False),
        ("Acme Robotics opened a sales office in Porto.", "hq_city", "Porto", False),
        ("Acme Robotics has raised $12M.", "funding_total", 12000000, True),
        ("Acme Robotics has raised 12 million dollars.", "funding_total", 12000000, True),
        ("Acme Robotics was founded in 2014 and in 2015.", "founded_year", 2014, False),
    ]
    ok = True
    for ex, f, v, want in cases:
        got = supports(ex, f, v, d)
        if got != want:
            print("SELFTEST MISMATCH", ex, f, v, "want", want, "got", got)
            ok = False
    print("selftest", "ok" if ok else "FAILED")
    return ok


# ---------------------------------------------------------------- probes
def p_health_auth():
    reset()
    s, b, _ = svc("GET", "/health")
    check(s == 200 and b == {"status": "ok"}, "E-21", f"health {s} {b}")
    check(calls() == [], "E-21", "health made provider calls")
    r = svc("POST", "/auth/signup", {"email": "c@example.com", "password": "longenough", "display_name": "C"})
    check(r[0] == 201 and set(r[1]) >= {"user_id", "display_name", "token"}, "E-60", f"signup {r[0]} {r[1]}")
    err(svc("POST", "/auth/signup", {"email": "c@example.com", "password": "longenough", "display_name": "C"}), 409, "email_taken", "E-61", "dup email")
    err(svc("POST", "/auth/signup", {"email": "d@example.com", "password": "short", "display_name": "C"}), 422, "validation_failed", "E-61", "short pw")
    err(svc("POST", "/auth/signup", {"email": "nope", "password": "longenough", "display_name": "C"}), 422, "validation_failed", "E-61", "bad email")
    err(svc("POST", "/auth/signup", {"email": "e@example.com", "password": "longenough", "display_name": ""}), 422, "validation_failed", "E-61", "empty name")
    err(svc("POST", "/auth/signup", {"email": "e@example.com", "password": "longenough", "display_name": "x" * 101}), 422, "validation_failed", "E-61", "101 name")
    r = svc("POST", "/auth/signup", {"email": "e@example.com", "password": "longenough", "display_name": "x" * 100})
    check(r[0] == 201, "E-61", f"100-char display_name {r[0]}")
    err(svc("POST", "/auth/login", {"email": "ada@example.com", "password": "wrong"}), 401, "unauthenticated", "E-61", "wrong pw")
    err(svc("POST", "/auth/login", {"email": "zz@example.com", "password": "correct horse"}), 401, "unauthenticated", "E-61", "unknown email")
    err(svc("POST", "/auth/signup", raw=b"{bad"), 400, "malformed_request", "E-51", "unparseable")
    err(svc("POST", "/auth/signup", {"email": 5, "password": "longenough", "display_name": "C"}), 400, "malformed_request", "E-51", "wrong type")
    s, b, _ = svc("POST", "/auth/login", {"email": "ada@example.com", "password": "correct horse", "extra": 1})
    check(s == 200 and b["user_id"] == "u_ada", "E-24", f"seeded login {s} {b}")
    t1 = login(); t2 = login()
    check(svc("GET", "/dossiers", tok=t1)[0] == 200 and svc("GET", "/dossiers", tok=t2)[0] == 200, "E-63", "two tokens")
    for tok in (None, "garbage", ""):
        err(svc("GET", "/dossiers", tok=tok), 401, "unauthenticated", "E-62", f"token {tok!r}")
    err(svc("POST", "/dossiers", {"domain": "a.test"}, tok="bad"), 401, "unauthenticated", "E-62", "401 before missing key")
    err(svc("POST", "/dossiers/a.test/refresh", tok="bad"), 401, "unauthenticated", "E-62", "401 refresh before key")
    err(svc("GET", "/dossiers/a.test"), 401, "unauthenticated", "E-62", "get no token")


def p_reset_clock():
    reset()
    bad = dict(FIX, users=FIX["users"] + [{"id": "u_x", "email": "ada@example.com", "password": "correct horse", "display_name": "X"}])
    err(svc("POST", "/_test/reset", bad), 422, "validation_failed", "E-23", "dup email fixture")
    check(svc("POST", "/auth/login", {"email": "ada@example.com", "password": "correct horse"})[0] == 200, "E-23", "state changed by failed reset")
    err(svc("POST", "/_test/reset", {"users": []}), 422, "validation_failed", "E-23", "missing now")
    err(svc("POST", "/_test/clock", {"now": "2026-03-01T09:30:00"}), 422, "validation_failed", "E-25", "no offset")
    r = svc("POST", "/_test/clock", {"now": "2026-03-02T09:30:00+02:00"})
    check(r[0] == 204, "E-25", f"clock set {r[0]}")
    err(svc("POST", "/_test/clock", {"now": "2026-03-01T00:00:00+00:00"}), 422, "validation_failed", "E-25", "clock backwards")
    # reset to past now must be allowed (reset sets the clock)
    r = svc("POST", "/_test/reset", FIX)
    check(r[0] == 204, "E-26", "reset after clock moved")
    tok = login()
    svc("POST", "/dossiers", {"domain": "halvorsen-robotics.test"}, tok=tok, key="k1")
    b = wait_state(tok, "halvorsen-robotics.test")
    if b and b["state"] == "ready":
        check(b["researched_at"] is not None and b["researched_at"].startswith("2026-03-01T09:00:00"), "E-26", f"researched_at {b['researched_at']}")
    # sign up and reset clears
    svc("POST", "/auth/signup", {"email": "n@example.com", "password": "longenough", "display_name": "N"})
    reset()
    check(svc("POST", "/auth/login", {"email": "n@example.com", "password": "longenough"})[0] == 401, "E-22", "user survived reset")
    check(svc("GET", "/dossiers", tok=login())[1]["dossiers"] == [], "E-22", "dossiers survived reset")


def p_validation():
    reset(); tok = login()
    for d in ["https://a.test", "a.test/x", "localhost", "a_b.test", "-a.test", "a-.test", "a..test", "", " ", "a.test.."
              , ("a" * 64) + ".test", ".".join(["a" * 60] * 5) + ".test", "a b.test", "www.", "a.b:80"]:
        err(svc("POST", "/dossiers", {"domain": d}, tok=tok, key="v" + str(abs(hash(d)))), 422, "validation_failed", "E-30", f"domain {d[:30]!r}")
    err(svc("POST", "/dossiers", {}, tok=tok, key="vm"), 422, "validation_failed", "E-85", "domain missing")
    err(svc("POST", "/dossiers", {"domain": 5}, tok=tok, key="vt"), 400, "malformed_request", "E-51", "domain wrong type")
    err(svc("POST", "/dossiers", raw=b"{x", tok=tok, key="vp", headers={"Content-Type": "application/json"}), 400, "malformed_request", "E-51", "bad json")
    err(svc("POST", "/dossiers", {"domain": "a.test"}, tok=tok), 400, "missing_idempotency_key", "E-70", "no key")
    err(svc("POST", "/dossiers", {"domain": "a.test"}, tok=tok, key=""), 400, "missing_idempotency_key", "E-70", "empty key")
    err(svc("POST", "/dossiers", {"domain": "a.test"}, tok=tok, key="k" * 256), 422, "validation_failed", "E-53", "256 key")
    err(svc("GET", "/dossiers/not_a_domain!", tok=tok), 422, "validation_failed", "E-30", "GET invalid path domain") if False else None
    err(svc("GET", "/dossiers/unknown-co.test", tok=tok), 404, "not_found", "E-86", "unknown dossier")
    err(svc("POST", "/dossiers/unknown-co.test/refresh", tok=tok, key="r1"), 404, "not_found", "E-87", "refresh unknown")
    for q in ["limit=0", "limit=201", "limit=1e9", "limit=4.0", "limit=+4", "limit=abc", "offset=-1", "offset=1e1", "offset=+0", "limit="]:
        err(svc("GET", "/dossiers?" + q, tok=tok), 422, "validation_failed", "E-53", q)
    for q in ["limit=1", "limit=200", "offset=0", "x=1&limit=5", ""]:
        check(svc("GET", "/dossiers?" + q, tok=tok)[0] == 200, "E-53", "valid " + q)
    check(calls() == [], "E-83", "validation made provider calls")


FIELDS = ["legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total"]


def verify_dossier(d, dom, label):
    """E-01/E-34/E-36/E-37: every citation must be served text and support the value"""
    log = calls()
    served = {}
    for c in log:
        for sv in c["served"]:
            served.setdefault(sv.get("url"), []).append(sv["text"])
    check(list(d["fields"]) == FIELDS or set(d["fields"]) == set(FIELDS), "E-32", f"{label} field set {list(d['fields'])}")
    for f in FIELDS:
        fld = d["fields"][f]
        if fld["status"] == "unknown":
            check(fld["value"] is None and fld["citations"] == [], "E-34", f"{label}.{f} unknown shape")
            continue
        check(fld["status"] == "known" and fld["value"] is not None and len(fld["citations"]) >= 1, "E-34", f"{label}.{f} known shape")
        v = fld["value"]
        types = {"founded_year": int, "funding_total": int}
        if f in types:
            check(type(v) is int, "E-32", f"{label}.{f} not int: {v!r}")
        if f == "headcount_range":
            check(v in [x[2] for x in BUCKETS], "E-32", f"{label} headcount {v!r}")
        if isinstance(v, str):
            check(v == v.strip(), "E-33", f"{label}.{f} whitespace in value")
        for c in fld["citations"]:
            ex = c["excerpt"]
            check(c["provider"] in ("nimble", "tavily"), "E-35", f"{label}.{f} provider {c['provider']}")
            check(1 <= len(ex) <= 500, "E-36", f"{label}.{f} excerpt length {len(ex)}")
            texts = served.get(c["url"], [])
            # "served text" for the page: any text the provider returned for that url (snippet/body/full)
            norm = lambda t: re.sub(r"\s+", " ", t)
            in_served = any(norm(ex) in norm(t) for t in texts)
            check(in_served, "E-01/E-36", f"{label}.{f} excerpt not found in any text served for {c['url']}: {ex[:80]!r}")
            for t in texts:
                if norm(ex) in norm(t):
                    # must be in prose, not header
                    head, sep, prose = t.partition("\n\n")
                    if sep and norm(ex) in norm(head) and norm(ex) not in norm(prose):
                        check(False, "E-36", f"{label}.{f} excerpt from header: {ex[:60]!r}")
            check(supports(ex, f, v, dom), "E-37/E-96", f"{label}.{f}={v!r} excerpt does not support (Appendix A): {ex!r}")


def build_cost(dom_log):
    return sum(c["cost"] for c in dom_log)


def p_build_core():
    reset(); tok = login()
    dom = "halvorsen-robotics.test"
    r = svc("POST", "/dossiers", {"domain": "WWW." + dom.upper() + "."}, tok=tok, key="b1")
    check(r[0] == 202 and r[1]["domain"] == dom and r[1]["state"] == "building" and len(r[1]["dossier_id"]) <= 64, "E-84/E-31", f"create {r[0]} {r[1]}")
    d0 = svc("GET", "/dossiers/" + dom, tok=tok)[1]
    check(all(d0["fields"][f]["status"] == "unknown" for f in FIELDS) if d0["state"] == "building" else True, "E-86", "fields not unknown before first ready")
    t0 = time.time()
    d = wait_state(tok, dom, t=20)
    check(d is not None, "E-81", "build did not end within 20s")
    if not d:
        return
    check(time.time() - t0 <= 10.5, "E-81", f"build took {time.time()-t0:.1f}s")
    check(d["state"] == "ready", "E-80", f"state {d['state']}")
    check(d["researched_at"] == "2026-03-01T09:00:00+00:00" or (d["researched_at"] or "").startswith("2026-03-01T09:00:00"), "E-86", f"researched_at {d['researched_at']}")
    log = calls()
    check(build_cost(log) == d["spent_units"], "E-89", f"spent_units {d['spent_units']} != mock log cost {build_cost(log)}")
    check(d["spent_units"] <= 80, "E-02", f"spent {d['spent_units']} > 80")
    check(all(c["method"] != "extract" or c["provider"] != "nimble" or c["cost"] == len(c["urls"]) for c in log), "E-100", "nimble extract set render (cost != 1/url)")
    ok_searches = [c for c in log if c["method"] == "search" and c["status"] == 200]
    exact = [c for c in ok_searches if c["query"] == dom]
    check(len(exact) == 1, "E-42", f"expected exactly one successful search with query == domain, got {len(exact)}; queries={[c['query'] for c in ok_searches]}")
    check(all(c["query"] != dom for c in ok_searches if c not in exact), "E-42", "extra exact-domain search")
    for c in log:
        if c["method"] == "search":
            check(c["max_results"] is None or True, "E-100", "")
        if c["method"] == "research":
            check(c["fields"] is not None and all(f in FIELDS for f in c["fields"]), "E-102", f"research fields {c['fields']}")
            check(c["fields"] == sorted(FIELDS), "E-41", f"research did not ask for all six: {c['fields']}")
    check(all(c["provider"] in ("nimble", "tavily") for c in log), "E-12", "unexpected provider")
    check(any(c["provider"] == "nimble" for c in log), "E-12", "nimble not used")
    verify_dossier(d, dom, dom)
    # reads make no provider call
    n = len(calls())
    svc("GET", "/dossiers/" + dom, tok=tok); svc("GET", "/dossiers?q=halv", tok=tok); svc("GET", "/dossiers/www." + dom, tok=tok)
    check(len(calls()) == n, "E-83", "reads made provider calls")
    # existing dossier: 200, no build
    r = svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="b2")
    check(r[0] == 200 and r[1]["state"] == "ready" and r[1]["dossier_id"] == d["dossier_id"], "E-84", f"existing -> {r[0]} {r[1]}")
    check(len(calls()) == n, "E-84", "existing dossier POST made provider calls")
    # normalised path
    check(svc("GET", "/dossiers/Www.Halvorsen-Robotics.TEST.", tok=tok)[1]["domain"] == dom, "E-31", "path normalisation")
    return d


def p_refresh_cost():
    reset(); tok = login(); dom = "halvorsen-robotics.test"
    svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="a")
    d1 = wait_state(tok, dom)
    c1 = len(calls())
    t1 = "2026-03-05T10:00:00+00:00"
    svc("POST", "/_test/clock", {"now": t1})
    r = svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="r1")
    check(r[0] == 202 and r[1]["state"] == "building" and r[1]["dossier_id"] == d1["dossier_id"], "E-87", f"refresh {r[0]} {r[1]}")
    r2 = svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="r2")
    check(r2[0] == 202 and r2[1] == r[1], "E-87", f"second refresh while building {r2}") if True else None
    d2 = wait_state(tok, dom)
    log = calls()
    check(len(log) > c1, "E-87", "refresh made no provider calls")
    check(d2["spent_units"] == build_cost(log), "E-89", f"spent {d2['spent_units']} vs {build_cost(log)}")
    check(d2["spent_units"] > d1["spent_units"], "E-87", "spent did not grow")
    check(d2["researched_at"].startswith("2026-03-05T10:00:00"), "E-86", f"researched_at {d2['researched_at']}")
    per_build = d2["spent_units"] - d1["spent_units"]
    check(per_build <= 80, "E-02", f"refresh build spent {per_build}")
    # exactly one exact-domain search in second build
    second = log[c1:]
    ex = [c for c in second if c["method"] == "search" and c["status"] == 200 and c["query"] == dom]
    check(len(ex) == 1, "E-42", f"refresh: {len(ex)} exact-domain searches")
    # replay r1 after change
    rr = svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="r1")
    check(rr[0] == 200 and rr[1] == r[1], "E-78", f"replay refresh {rr}")
    check(len(calls()) == len(log), "E-78", "replay made provider calls")
    # refresh body ignored for replay
    rr = svc("POST", f"/dossiers/{dom}/refresh", {"anything": 1}, tok=tok, key="r1")
    check(rr[0] == 200, "E-75", f"refresh replay with body {rr[0]}")
    # different path same key: normal
    other = "brightwater-labs.test"
    svc("POST", "/dossiers", {"domain": other}, tok=tok, key="shared")
    r = svc("POST", f"/dossiers/{other}/refresh", tok=tok, key="shared")
    check(r[0] == 202, "E-72", f"same key different path {r[0]} {r[1]}")
    check(svc("POST", f"/dossiers/{other.upper()}/refresh", tok=tok, key="shared")[0] == 409, "E-73", "case-different path with same key should be 409") if False else None


def p_idempotency():
    reset(); tok = login(); tok2 = login("bob@example.com")
    dom = "quillmate.test"
    r1 = svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="K")
    check(r1[0] == 202, "E-71", f"first {r1[0]}")
    r2 = svc("POST", "/dossiers", {"domain": dom, "unknown": [1]}, tok=tok, key="K")
    check(r2[0] == 200 and r2[1] == r1[1], "E-74", f"replay with unknown field {r2}")
    r2 = svc("POST", "/dossiers", raw=('{ "domain" :"%s" }' % dom).encode(), tok=tok, key="K", headers={"Content-Type": "application/json"})
    check(r2[0] == 200 and r2[1] == r1[1], "E-74", f"replay whitespace {r2[0]}")
    err(svc("POST", "/dossiers", {"domain": "ostrava-mobility.test"}, tok=tok, key="K"), 409, "idempotency_key_reuse", "E-71", "different body")
    err(svc("POST", "/dossiers", {"domain": dom.upper()}, tok=tok, key="K"), 409, "idempotency_key_reuse", "E-73", "case-different domain")
    err(svc("POST", "/dossiers", {"domain": 5}, tok=tok, key="K"), 409, "idempotency_key_reuse", "E-79", "claimed key before validation (wrong type)") if False else None
    err(svc("POST", "/dossiers", {"domain": "!!bad"}, tok=tok, key="K"), 409, "idempotency_key_reuse", "E-79", "claimed key before field validation")
    r = svc("POST", "/dossiers", {"domain": dom}, tok=tok2, key="K")
    check(r[0] == 200 and r[1]["dossier_id"] == r1[1]["dossier_id"], "E-65/E-72", f"other user same key, existing dossier -> {r[0]} {r[1]}")
    # failed first use reusable
    err(svc("POST", "/dossiers", {"domain": "bad domain"}, tok=tok, key="F"), 422, "validation_failed", "E-76", "first fail")
    r = svc("POST", "/dossiers", {"domain": "ostrava-mobility.test"}, tok=tok, key="F")
    check(r[0] == 202, "E-76", f"key reuse after 4xx -> {r[0]}")
    wait_state(tok, dom); wait_state(tok, "ostrava-mobility.test")
    n = len(calls())
    r = svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="K")
    check(r[0] == 200 and r[1] == r1[1], "E-78", f"replay after change returns original (state building): {r}")
    check(len(calls()) == n, "E-78", "replay made provider calls")
    # key scope for refresh and posts independent
    err(svc("POST", f"/dossiers/{dom}/refresh", tok=tok), 400, "missing_idempotency_key", "E-70", "refresh no key")
    err(svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="k" * 256), 422, "validation_failed", "E-53", "refresh 256 key")
    ra = svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="R")
    rb = svc("POST", f"/dossiers/{dom}/refresh", tok=tok2, key="R")
    check(ra[0] == 202 and rb[0] == 202, "E-72", f"two users same refresh key {ra[0]} {rb[0]}")
    err(svc("POST", f"/dossiers/{dom.upper()}/refresh", tok=tok, key="R"), 409, "idempotency_key_reuse", "E-73", "refresh path case differs same key") if False else None


def p_concurrent_create():
    reset(); tok = login(); tok2 = login("bob@example.com")
    dom = "tidemark-energy.test"
    with ThreadPoolExecutor(20) as ex:
        res = list(ex.map(lambda i: svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="same"), range(20)))
    codes = sorted(r[0] for r in res)
    check(codes.count(202) == 1 and codes.count(200) == 19, "E-77", f"same key concurrent: {codes}")
    check(len({json.dumps(r[1], sort_keys=True) for r in res}) == 1, "E-77", "bodies differ")
    wait_state(tok, dom)  # let the first build finish so its calls do not leak into the next log
    reset(); tok = login()
    with ThreadPoolExecutor(20) as ex:
        res = list(ex.map(lambda i: svc("POST", "/dossiers", {"domain": dom if i % 2 else "www." + dom}, tok=tok, key=f"diff{i}"), range(20)))
    check(all(r[0] in (200, 202) for r in res) and sum(r[0] == 202 for r in res) == 1, "E-84", f"different keys: {sorted(r[0] for r in res)}")
    check(len({r[1]["dossier_id"] for r in res}) == 1, "E-84", "multiple dossiers for one domain")
    d = wait_state(tok, dom)
    log = calls()
    check(d is not None and d["spent_units"] == build_cost(log) and d["spent_units"] <= 80, "E-02/E-89", f"concurrent create spend {d and d['spent_units']} vs {build_cost(log)}")
    check(len([c for c in log if c["method"] == "search" and c["status"] == 200 and c["query"] == dom]) == 1, "E-84", "more than one build ran")
    # concurrent refreshes with different keys: one build
    n = len(log)
    with ThreadPoolExecutor(10) as ex:
        res = list(ex.map(lambda i: svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key=f"rf{i}"), range(10)))
    check(all(r[0] == 202 and r[1] == res[0][1] for r in res), "E-87", f"concurrent refresh {[r[0] for r in res]}")
    d2 = wait_state(tok, dom)
    new = calls()[n:]
    check(len([c for c in new if c["method"] == "search" and c["status"] == 200 and c["query"] == dom]) == 1, "E-87", "concurrent refresh ran >1 build")
    check(d2["spent_units"] == build_cost(calls()), "E-89", "spent mismatch after refreshes")


def p_list():
    reset(); tok = login()
    doms = ["quillmate.test", "ashgrove-solar.test", "brightwater-labs.test", "corvid-security.test"]
    for d in doms:
        svc("POST", "/dossiers", {"domain": d}, tok=tok, key="L" + d)
    for d in doms:
        wait_state(tok, d, t=40)
    s, b, _ = svc("GET", "/dossiers", tok=tok)
    names = [x["domain"] for x in b["dossiers"]]
    check(names == sorted(doms) and b["has_more"] is False, "E-88", f"order {names}")
    check(set(b["dossiers"][0]) >= {"dossier_id", "domain", "state", "legal_name", "researched_at", "spent_units"}, "E-88", "list item keys")
    s, b, _ = svc("GET", "/dossiers?limit=2&offset=1", tok=tok)
    check([x["domain"] for x in b["dossiers"]] == sorted(doms)[1:3] and b["has_more"] is True, "E-88", f"paging {b}")
    s, b, _ = svc("GET", "/dossiers?limit=2&offset=2", tok=tok)
    check(len(b["dossiers"]) == 2 and b["has_more"] is False, "E-88", "has_more at end")
    check(len(svc("GET", "/dossiers?q=", tok=tok)[1]["dossiers"]) == 4, "E-88", "empty q")
    check([x["domain"] for x in svc("GET", "/dossiers?q=QUILL", tok=tok)[1]["dossiers"]] == ["quillmate.test"], "E-88", "q case-insens domain")
    ln = {x["domain"]: x["legal_name"] for x in svc("GET", "/dossiers", tok=tok)[1]["dossiers"]}
    for d, n in ln.items():
        if n:
            got = [x["domain"] for x in svc("GET", "/dossiers?q=" + urllib.request.quote(n.lower()), tok=tok)[1]["dossiers"]]
            check(d in got, "E-88", f"q by legal_name {n!r} missing {d}")
            check(svc("GET", "/dossiers/" + d, tok=tok)[1]["fields"]["legal_name"]["value"] == n, "E-88", "list legal_name matches field")
    tok2 = login("bob@example.com")
    check(len(svc("GET", "/dossiers", tok=tok2)[1]["dossiers"]) == 4, "E-65", "users see same dossiers")


def p_all_samples_support():
    """E-01/E-37/E-39/E-96: build every sample company, verify each citation, and unknown-ness via key if present"""
    reset(); tok = login()
    sample = ["halvorsen-robotics", "quillmate", "brightwater-labs", "ostrava-mobility", "pemberton-analytics",
              "ferncliff-foods", "tidemark-energy", "corvid-security", "larkspur-health", "mosaic-freight",
              "windrush-bakery", "ashgrove-solar"]
    for s in sample:
        dom = s + ".test"
        mock("POST", "/_mock/reset", {"epoch": 0})
        svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="s" + s)
        d = wait_state(tok, dom, t=30)
        if not d:
            check(False, "E-81", f"{dom} never finished"); continue
        check(d["state"] == "ready", "E-80", f"{dom} state {d['state']}")
        verify_dossier(d, dom, dom)
        log = calls()
        check(d["spent_units"] == build_cost(log) <= 80, "E-02/E-89", f"{dom} spent {d['spent_units']} log {build_cost(log)}")
        # unknown iff nothing supports: any served text with a supporting sentence for an unknown field => violation
        for f in FIELDS:
            if d["fields"][f]["status"] == "unknown":
                for c in log:
                    for sv in c["served"]:
                        txt = sv["text"].partition("\n\n")[2] if "\n\n" in sv["text"] else sv["text"]
                        for sent in split_sentences(txt):
                            for v in set(map(lambda x: x, values_for(f, sent, dom))):
                                if supports(sent, f, v, dom):
                                    check(False, "E-80", f"{dom}.{f} unknown but served sentence supports {v!r}: {sent[:100]!r}")
        # known: value must be one supported by a served sentence (verify_dossier did) ; multi-value citations consistent (E-39)
        for f in FIELDS:
            fl = d["fields"][f]
            for c in fl["citations"]:
                check(supports(c["excerpt"], f, fl["value"], dom), "E-39", f"{dom}.{f} citation supports a different value")


def p_faults():
    reset(); tok = login(); dom = "quillmate.test"
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search", "extract", "research"], "mode": "error"})
    r = svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="f1")
    check(r[0] == 202, "E-54", f"create under fault {r[0]}")
    d = wait_state(tok, dom, t=30)
    check(d and d["state"] == "failed" and d["spent_units"] == 0 and all(d["fields"][f]["status"] == "unknown" for f in FIELDS), "E-80", f"all-fail build -> {d and (d['state'], d['spent_units'])}")
    check(d and d["researched_at"] is None, "E-86", "researched_at not null after failed first build")
    check(all(c["cost"] == 0 for c in calls()), "E-100", "faulted calls cost")
    check(len([c for c in calls() if c["status"] == 200]) == 0, "E-80", "")
    # recover: refresh with no fault -> ready, then fault again keeps fields
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search", "extract", "research"], "mode": "none"})
    svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="f2")
    good = wait_state(tok, dom)
    check(good["state"] == "ready", "E-80", f"recovered state {good['state']}")
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search", "extract", "research"], "mode": "error"})
    svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="f3")
    bad = wait_state(tok, dom)
    check(bad["state"] == "failed", "E-80", f"state {bad['state']}")
    check(bad["fields"] == good["fields"] and bad["researched_at"] == good["researched_at"], "E-80/E-86", "failed build changed fields/researched_at")
    check(bad["spent_units"] == good["spent_units"], "E-89", "spent grew on free faulted calls")
    # rate limit mode + tavily absent/erroring: nimble alone suffices
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search", "extract", "research"], "mode": "none"})
    mock("POST", "/_mock/faults", {"provider": "tavily", "methods": ["search", "extract"], "mode": "error"})
    svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="f4")
    ok = wait_state(tok, dom)
    check(ok["state"] == "ready", "E-12", "tavily errors blocked research")
    mock("POST", "/_mock/faults", {"provider": "tavily", "methods": ["search", "extract"], "mode": "none"})
    # throttle / weather
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search", "extract", "research"], "mode": "throttle"})
    svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="f5")
    th = wait_state(tok, dom, t=40)
    check(th is not None and th["state"] in ("ready", "failed"), "E-54", "throttled build did not finish")
    check(th["spent_units"] == build_cost(calls()), "E-89", f"spent under throttle {th['spent_units']} vs {build_cost(calls())}")
    check(all(c["status"] < 500 or c["cost"] == 0 for c in calls()), "E-100", "")
    # delay fault: slow nimble search
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search"], "mode": "delay", "seconds": 3})
    svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="f6")
    t0 = time.time(); sl = wait_state(tok, dom, t=60)
    check(sl is not None and sl["state"] in ("ready", "failed"), "E-81", "delayed build did not finish")
    check(svc("GET", "/health")[0] == 200, "E-21", "health during delayed build")
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search"], "mode": "none"})


def p_budget():
    """E-02/E-101: spend never exceeds 80 per build on every sample company, also with tavily-heavy faults"""
    reset(); tok = login()
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["research"], "mode": "error"})
    for s in ["halvorsen-robotics", "mosaic-freight", "windrush-bakery"]:
        dom = s + ".test"
        mock("POST", "/_mock/reset", {"epoch": 0})
        mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["research"], "mode": "error"})
        svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="bg" + s)
        d = wait_state(tok, dom)
        check(d is not None and d["spent_units"] == build_cost(calls()) <= 80, "E-02", f"{dom} {d and d['spent_units']}")
        ex = [c for c in calls() if c["method"] == "search" and c["status"] == 200 and c["query"] == dom]
        check(len(ex) == 1, "E-42", f"{dom}: {len(ex)} exact-domain successful searches with research failing")
        verify_dossier(d, dom, dom + "/noresearch")
    # when the exact-domain search is the failing one, a later success counts: errored search does not count
    mock("POST", "/_mock/reset", {"epoch": 0})
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search"], "mode": "error"})
    dom = "ostrava-mobility.test"
    svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="bgx")
    d = wait_state(tok, dom)
    log = calls()
    okex = [c for c in log if c["method"] == "search" and c["status"] == 200 and c["query"] == dom]
    check(len(okex) <= 1, "E-42", f"{len(okex)} successful exact searches")
    check(d["spent_units"] == build_cost(log) <= 80, "E-02", f"nimble-search-down spend {d['spent_units']}")
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search"], "mode": "none"})


def p_reset_midbuild():
    reset(); tok = login(); dom = "quillmate.test"
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search", "research"], "mode": "delay", "seconds": 3})
    svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="m1")
    time.sleep(0.5)
    reset(); tok = login()
    time.sleep(6)
    check(svc("GET", "/dossiers", tok=tok)[1]["dossiers"] == [], "E-22", "build resurrected a dossier after reset")
    check(svc("GET", "/dossiers/" + dom, tok=tok)[0] == 404, "E-22", "dossier visible after reset")
    r = svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="m1")
    check(r[0] == 202, "E-22", f"idempotency record survived reset: {r[0]}")
    wait_state(tok, dom, t=30)


def p_export_import():
    reset(); tok = login(); dom = "halvorsen-robotics.test"
    s, e0, _ = svc("GET", "/_test/export")
    check(s == 200 and e0["track"] == "dossier" and e0["format_version"] == 1 and "state" in e0, "E-110", f"export {s}")
    svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="e1")
    d1 = wait_state(tok, dom)
    sg = svc("POST", "/auth/signup", {"email": "zed@example.com", "password": "secretpass1", "display_name": "Z"})[1]
    err(svc("POST", "/dossiers", {"domain": "bad domain"}, tok=tok, key="fail1"), 422, "validation_failed", "E-112", "setup failed key")
    s, e, _ = svc("GET", "/_test/export")
    check(s == 200, "E-110", "export")
    check("secretpass1" not in json.dumps(e) and "correct horse" not in json.dumps(e), "E-115", "plaintext password in export")
    snap = json.dumps(e, sort_keys=True)
    log_n = len(calls())
    svc("POST", "/_test/reset", {"now": "2026-04-01T00:00:00+00:00", "users": []})
    check(svc("GET", "/dossiers", tok=tok)[0] == 401, "E-22", "token valid after reset")
    clk = "2026-04-02T00:00:00+00:00"
    svc("POST", "/_test/clock", {"now": clk})
    r = svc("POST", "/_test/import", e)
    check(r[0] == 204, "E-111", f"import {r[0]} {r[1]}")
    check(len(calls()) == log_n, "E-113", "import made provider calls")
    d2 = svc("GET", "/dossiers/" + dom, tok=tok)
    check(d2[0] == 200 and d2[1] == d1, "E-112", f"dossier after import differs: {d2[0]}")
    check(svc("POST", "/auth/login", {"email": "zed@example.com", "password": "secretpass1"})[1]["user_id"] == sg["user_id"], "E-112", "login/user_id after import")
    check(svc("GET", "/dossiers", tok=sg["token"])[0] == 200, "E-112", "signup token after import")
    rp = svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="e1")
    check(rp[0] == 200 and rp[1]["dossier_id"] == d1["dossier_id"], "E-112", f"idempotent replay after import {rp}")
    rp = svc("POST", "/dossiers", {"domain": "quillmate.test"}, tok=tok, key="fail1")
    check(rp[0] == 202, "E-112", f"failed key reusable after import {rp[0]}")
    check(len(calls()) > log_n, "E-112", "") if False else None
    # clock unchanged by import
    err(svc("POST", "/_test/clock", {"now": "2026-04-01T12:00:00+00:00"}), 422, "validation_failed", "E-113", "import changed clock (clock went back)")
    wait_state(tok, "quillmate.test")
    # re-import export taken earlier is replacement and idempotent
    r1 = svc("POST", "/_test/import", e); r2 = svc("POST", "/_test/import", e)
    check(r1[0] == 204 and r2[0] == 204, "E-111", "repeat import")
    s, e2, _ = svc("GET", "/_test/export")
    check(json.dumps(e2, sort_keys=True) == snap, "E-111", "export after import differs from imported state")
    check(svc("GET", "/dossiers/quillmate.test", tok=tok)[0] == 404, "E-111", "import merged instead of replaced")
    # invalid imports leave state unchanged
    for bad, why in [({"track": "other", "format_version": 1, "state": e["state"]}, "track"),
                     ({"track": "dossier", "format_version": 2, "state": e["state"]}, "version"),
                     ({"track": "dossier", "format_version": 1}, "missing state"),
                     ({"track": "dossier", "format_version": 1, "state": "nonsense"}, "invalid state"),
                     ({"track": "dossier", "format_version": 1, "state": {"garbage": True}}, "invalid state obj")]:
        err(svc("POST", "/_test/import", bad), 422, "validation_failed", "E-111", why)
    err(svc("POST", "/_test/import", raw=b"{nope", headers={"Content-Type": "application/json"}), 400, "malformed_request", "E-111", "bad json import")
    check(svc("GET", "/dossiers/" + dom, tok=tok)[1] == d1, "E-111", "invalid import changed state")
    # reset clears imported
    reset()
    check(svc("GET", "/dossiers", tok=tok)[0] == 401, "E-113", "imported token survived reset")
    # export during build: pre-build dossier
    reset(); tok = login()
    svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="x1"); wait_state(tok, dom)
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search", "research"], "mode": "delay", "seconds": 3})
    svc("POST", f"/dossiers/{dom}/refresh", tok=tok, key="x2")
    s, em, _ = svc("GET", "/_test/export")
    wait_state(tok, dom, t=30)
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search", "research"], "mode": "none"})
    reset(); svc("POST", "/_test/import", em)
    tok = login()
    d = svc("GET", "/dossiers/" + dom, tok=tok)[1]
    check(d["state"] == "ready" and d["fields"]["legal_name"]["status"] == "known", "E-114", f"export mid-build -> {d['state']}")
    # first build mid-flight export
    reset(); tok = login()
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search", "research"], "mode": "delay", "seconds": 3})
    svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="y1")
    s, em, _ = svc("GET", "/_test/export")
    wait_state(tok, dom, t=30)
    mock("POST", "/_mock/faults", {"provider": "nimble", "methods": ["search", "research"], "mode": "none"})
    reset(); svc("POST", "/_test/import", em)
    tok = login()
    d = svc("GET", "/dossiers/" + dom, tok=tok)[1]
    check(d["state"] == "failed" and all(d["fields"][f]["status"] == "unknown" for f in FIELDS), "E-114", f"first-build export -> {d['state']}")
    time.sleep(0.5)


def p_concurrency_reads():
    reset(); tok = login(); dom = "pemberton-analytics.test"
    svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="c1")
    seen = []; stop = [False]

    def reader():
        while not stop[0]:
            s, b, _ = svc("GET", "/dossiers/" + dom, tok=tok)
            if s == 200:
                seen.append(b)
            elif s >= 500:
                seen.append(("5xx", s))
    ts = [threading.Thread(target=reader) for _ in range(8)]
    [t.start() for t in ts]
    wait_state(tok, dom)
    time.sleep(0.3); stop[0] = True; [t.join() for t in ts]
    check(not any(isinstance(x, tuple) for x in seen), "E-54", "5xx during build")
    last = 0
    for b in seen:
        if isinstance(b, tuple):
            continue
        if b["state"] == "building" and b["researched_at"] is None:
            check(all(b["fields"][f]["status"] == "unknown" for f in FIELDS), "E-120", "partial fields visible before ready")
    final = seen[-1]
    check(final["state"] == "ready", "E-120", "final state")
    # 50 concurrent mixed requests
    with ThreadPoolExecutor(50) as ex:
        res = list(ex.map(lambda i: svc("GET", "/dossiers/" + dom, tok=tok)[0], range(50)))
    check(all(c == 200 for c in res), "E-13", f"50 concurrent GETs {set(res)}")


def p_clock():
    reset(); tok = login(); dom = "quillmate.test"
    svc("POST", "/_test/clock", {"now": "2026-03-03T12:00:00-05:00"})
    svc("POST", "/dossiers", {"domain": dom}, tok=tok, key="t1")
    time.sleep(1.5)
    d = wait_state(tok, dom)
    ra = d["researched_at"]
    check(ra and re.search(r"(Z|[+-]\d\d:\d\d)$", ra), "E-27", f"researched_at offset {ra}")
    if ra:
        from datetime import datetime
        check(datetime.fromisoformat(ra.replace("Z", "+00:00")) == datetime.fromisoformat("2026-03-03T12:00:00-05:00"), "E-26", f"researched_at {ra} != request clock time")
    time.sleep(1)
    check(svc("GET", "/dossiers/" + dom, tok=tok)[1]["researched_at"] == ra, "E-26", "clock moved by itself")
    check(svc("POST", "/_test/clock", {"now": "2026-03-03T12:00:00-05:00"})[0] == 204, "E-25", "equal now allowed (not earlier)")


def p_misc():
    reset(); tok = login()
    s, b, h = svc("GET", "/dossiers", tok=tok)
    check("application/json" in (h.get("Content-Type") or ""), "E-28", f"content-type {h.get('Content-Type')}")
    err(svc("GET", "/nope", tok=tok), 404, "not_found", "E-50", "unknown route")
    s, b, _ = svc("GET", "/dossiers?limit=5&zzz=1", tok=tok)
    check(s == 200, "E-28", "unknown query ignored")
    err(svc("POST", "/auth/login", {"email": "ada@example.com"}), 422, "validation_failed", "E-52", "login missing password")


ALL = [p_health_auth, p_reset_clock, p_validation, p_build_core, p_refresh_cost, p_idempotency, p_concurrent_create,
       p_list, p_all_samples_support, p_faults, p_budget, p_reset_midbuild, p_export_import, p_concurrency_reads,
       p_clock, p_misc]

if __name__ == "__main__":
    args = sys.argv[1:] or ["all"]
    if not selftest():
        print("probe reference implementation is wrong; fix before use")
        sys.exit(2)
    if args == ["selftest"]:
        sys.exit(0)
    sel = ALL if args == ["all"] else [f for f in ALL if f.__name__[2:] in args or f.__name__ in args]
    for f in sel:
        print("==", f.__name__)
        try:
            f()
        except Exception as ex:  # a probe crash is a probe/infra problem; show it
            import traceback; traceback.print_exc()
            FAILS.append(("PROBE-CRASH", f.__name__ + ": " + repr(ex)))
    print(f"\n{PASSES[0]} checks passed, {len(FAILS)} failed")
    for e, m in FAILS:
        print(" -", e, m)
    sys.exit(1 if FAILS else 0)
