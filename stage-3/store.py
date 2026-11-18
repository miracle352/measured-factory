"""State, clock, auth, idempotency, builds bookkeeping, export/import."""
import base64
import copy
import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
import threading

FIELD_NAMES = ["legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total"]

_RFC3339 = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)
_DOMAIN_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")


class ApiError(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


def invalid(msg="invalid request"):
    return ApiError(422, "validation_failed", msg)


def malformed(msg="malformed request"):
    return ApiError(400, "malformed_request", msg)


# ---------------------------------------------------------------- helpers

def parse_ts(value):
    if not isinstance(value, str):
        raise malformed("timestamp must be a string")
    m = _RFC3339.match(value)
    if not m:
        raise invalid("timestamp must be RFC 3339 with an offset")
    s = value
    if s[-1] in "Zz":
        s = s[:-1] + "+00:00"
    s = s.replace("t", "T", 1) if "T" not in s else s
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        raise invalid("invalid timestamp")
    if d.tzinfo is None or d.utcoffset() is None:
        raise invalid("timestamp needs an offset")
    return d


def normalise_domain(raw):
    """raw must be str. Returns normalised domain or raises 422."""
    d = raw.strip().lower()
    if d.endswith("."):
        d = d[:-1]
    if d.startswith("www."):
        d = d[4:]
    if not d or len(d) > 253:
        raise invalid("invalid domain")
    labels = d.split(".")
    if len(labels) < 2:
        raise invalid("invalid domain")
    for lab in labels:
        if not _DOMAIN_LABEL.fullmatch(lab):
            raise invalid("invalid domain")
    return d


def hash_password(password):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 13, r=8, p=1, dklen=32)
    return "scrypt$13$8$1$%s$%s" % (
        base64.b64encode(salt).decode(), base64.b64encode(h).decode())


def verify_password(password, stored):
    try:
        _, n, r, p, salt, h = stored.split("$")
        salt = base64.b64decode(salt)
        h = base64.b64decode(h)
        calc = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** int(n), r=int(r),
                              p=int(p), dklen=len(h))
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


def unknown_fields():
    return {n: {"value": None, "status": "unknown", "citations": [], "candidates": []}
            for n in FIELD_NAMES}


_AUTH = {"own": 0, "filing": 0, "news": 1, "aggregator": 2, None: 2}
_PROV = {"nimble": 0, "tavily": 1, "kernel": 2, "browserbase": 3}


def _jkey(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def _norm_val(v):
    return v.strip() if isinstance(v, str) else v


def _fallback_assemble(cands):
    """Used only when candidates.assemble_field is unavailable."""
    cands = [dict(c) for c in cands]
    for c in cands:
        c["value"] = _norm_val(c["value"])

    def pub(c):
        p = c.get("published_at")
        if not p:
            return (1, 0.0)
        try:
            return (0, -parse_ts(p).timestamp())
        except Exception:
            return (1, 0.0)

    def vkey(c):
        v = c["value"]
        return (0, v, "") if isinstance(v, int) and not isinstance(v, bool) else (1, 0, str(v))

    cands.sort(key=lambda c: (_AUTH.get(c.get("kind"), 2), pub(c), c["url"],
                              _PROV.get(c.get("provider"), 9), vkey(c)))
    if not cands:
        return {"value": None, "status": "unknown", "citations": [], "candidates": []}
    sel = cands[0]["value"]
    for i, c in enumerate(cands):
        c["selected"] = i == 0
    cites = [{"url": c["url"], "excerpt": c["excerpt"], "provider": c["provider"]}
             for c in cands if _jkey(c["value"]) == _jkey(sel)]
    status = "known" if all(_jkey(c["value"]) == _jkey(sel) for c in cands) else "contested"
    return {"value": sel, "status": status, "citations": cites, "candidates": cands}


def _assemble(cands):
    try:
        import candidates as C
        return C.assemble_field(cands)
    except ImportError:
        return _fallback_assemble(cands)


def _derive(name, fobj, researched_at):
    try:
        import candidates as C
        return C.derive_import_candidates(name, fobj, researched_at)
    except ImportError:
        return [{"value": fobj["value"], "url": c["url"], "excerpt": c["excerpt"],
                 "provider": c["provider"], "kind": None, "published_at": None,
                 "retrieved_at": researched_at} for c in fobj["citations"]]


def _clean_cite(c):
    return {"url": str(c.get("url", "")), "excerpt": str(c.get("excerpt", "")),
            "provider": str(c.get("provider", ""))}


def norm_fields(raw, researched_at=None):
    """Fields in stage-2 shape. A field carrying `candidates` is kept as given (build result or
    stage-2 export). A stage-1 field (citations only) gets candidates derived from its citations."""
    out = {}
    raw = raw if isinstance(raw, dict) else {}
    for n in FIELD_NAMES:
        f = raw.get(n)
        if not isinstance(f, dict):
            out[n] = {"value": None, "status": "unknown", "citations": [], "candidates": []}
        elif isinstance(f.get("candidates"), list):
            cs = [dict(c) for c in f["candidates"] if isinstance(c, dict)]
            if not cs:
                out[n] = {"value": None, "status": "unknown", "citations": [], "candidates": []}
            else:
                out[n] = {"value": f.get("value"), "status": f.get("status") or "known",
                          "citations": [_clean_cite(c) for c in (f.get("citations") or [])
                                        if isinstance(c, dict)],
                          "candidates": cs}
        elif f.get("value") is not None and isinstance(f.get("citations"), list):
            cites = [_clean_cite(c) for c in f["citations"] if isinstance(c, dict)]
            fobj = {"value": f["value"], "status": "known", "citations": cites}
            cands = _derive(n, fobj, researched_at) if cites else []
            out[n] = _assemble(cands) if cands else dict(unknown_fields()[n])
        else:
            out[n] = {"value": None, "status": "unknown", "citations": [], "candidates": []}
    return out


# ---------------------------------------------------------------- build module

try:  # builder-a's module
    import build as _build_mod
    _run_build = _build_mod.run_build
except Exception:  # stub until build.py lands
    import time as _time

    class _Result:
        def __init__(self, outcome, fields, spent_units):
            self.outcome = outcome
            self.fields = fields
            self.spent_units = spent_units

    def _run_build(domain, now_iso, should_abort):
        _time.sleep(0.2)
        return _Result("ready", unknown_fields(), 0)


def _res_get(res, name, default=None):
    if isinstance(res, dict):
        return res.get(name, default)
    return getattr(res, name, default)


# ---------------------------------------------------------------- store

class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.clock = None  # None -> follow system time
        self.epoch = 0
        self._fresh()

    def _fresh(self):
        self.users = {}      # id -> {id,email,display_name,pw}
        self.emails = {}     # lower email -> id
        self.tokens = {}     # token -> user id
        self.dossiers = {}   # domain -> dict
        self.idem = {}       # (uid, "METHOD path", key) -> {"body":..., "response":...}
        self.seq = 0

    # ---- clock
    def now(self):
        if self.clock is not None:
            return self.clock
        return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    def now_iso(self):
        return self.now().isoformat()

    def set_clock(self, body):
        if not isinstance(body, dict):
            raise malformed("body must be an object")
        if "now" not in body or body["now"] is None:
            raise invalid("now is required")
        d = parse_ts(body["now"])
        with self.lock:
            if d < self.now():
                raise invalid("now is earlier than the current clock")
            self.clock = d

    # ---- reset
    def reset(self, body):
        if not isinstance(body, dict):
            raise malformed("body must be an object")
        if "now" not in body or body["now"] is None:
            raise invalid("now is required")
        now = parse_ts(body["now"])
        users_in = body.get("users", [])
        if users_in is None:
            users_in = []
        if not isinstance(users_in, list):
            raise malformed("users must be a list")
        prepared = []
        emails, ids = set(), set()
        for u in users_in:
            if not isinstance(u, dict):
                raise malformed("user must be an object")
            for k in ("id", "email", "password", "display_name"):
                if k not in u or u[k] is None:
                    raise invalid("user %s is required" % k)
                if not isinstance(u[k], str):
                    raise malformed("user %s must be a string" % k)
            e = u["email"].strip().lower()
            if e in emails or u["id"] in ids:
                raise invalid("duplicate user")
            emails.add(e)
            ids.add(u["id"])
            prepared.append((u, e))
        users = {}
        email_map = {}
        for u, e in prepared:
            users[u["id"]] = {"id": u["id"], "email": u["email"], "display_name": u["display_name"],
                              "pw": hash_password(u["password"])}
            email_map[e] = u["id"]
        with self.lock:
            self.epoch += 1
            self._fresh()
            self.users = users
            self.emails = email_map
            self.clock = now

    # ---- auth
    def signup(self, body):
        if not isinstance(body, dict):
            raise malformed("body must be an object")
        vals = {}
        for k in ("email", "password", "display_name"):
            v = body.get(k)
            if v is not None and not isinstance(v, str):
                raise malformed("%s must be a string" % k)
            vals[k] = v
        for k, v in vals.items():
            if v is None:
                raise invalid("%s is required" % k)
        email, pw, name = vals["email"], vals["password"], vals["display_name"]
        if not _EMAIL.fullmatch(email):
            raise invalid("invalid email")
        if len(pw) < 8:
            raise invalid("password too short")
        if len(name) == 0 or len(name) > 100:
            raise invalid("invalid display_name")
        key = email.strip().lower()
        with self.lock:
            if key in self.emails:
                raise ApiError(409, "email_taken", "email already registered")
        pwh = hash_password(pw)
        with self.lock:
            if key in self.emails:
                raise ApiError(409, "email_taken", "email already registered")
            uid = "u_" + secrets.token_hex(8)
            self.users[uid] = {"id": uid, "email": email, "display_name": name, "pw": pwh}
            self.emails[key] = uid
            token = secrets.token_urlsafe(32)
            self.tokens[token] = uid
        return {"user_id": uid, "display_name": name, "token": token}

    def login(self, body):
        if not isinstance(body, dict):
            raise malformed("body must be an object")
        for k in ("email", "password"):
            v = body.get(k)
            if v is not None and not isinstance(v, str):
                raise malformed("%s must be a string" % k)
        for k in ("email", "password"):
            if body.get(k) is None:
                raise invalid("%s is required" % k)
        with self.lock:
            uid = self.emails.get(body["email"].strip().lower())
            user = self.users.get(uid) if uid else None
        if user is None:
            verify_password(body["password"], "scrypt$13$8$1$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
            raise ApiError(401, "unauthenticated", "invalid credentials")
        if not verify_password(body["password"], user["pw"]):
            raise ApiError(401, "unauthenticated", "invalid credentials")
        with self.lock:
            if self.users.get(uid) is not user:
                raise ApiError(401, "unauthenticated", "invalid credentials")
            token = secrets.token_urlsafe(32)
            self.tokens[token] = uid
        return {"user_id": uid, "display_name": user["display_name"], "token": token}

    def authenticate(self, header):
        if not header:
            raise ApiError(401, "unauthenticated", "missing token")
        parts = header.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise ApiError(401, "unauthenticated", "malformed token")
        with self.lock:
            uid = self.tokens.get(parts[1].strip())
        if uid is None:
            raise ApiError(401, "unauthenticated", "unknown token")
        return uid

    # ---- dossiers
    def _public_state(self, d):
        if d["building"]:
            return "building"
        return d["last_outcome"] or "failed"

    def _brief(self, d):
        return {"dossier_id": d["id"], "domain": d["domain"], "state": self._public_state(d)}

    def _start_build(self, d):
        d["building"] = True
        epoch = self.epoch
        now_iso = self.now_iso()
        threading.Thread(target=self._run, args=(d, epoch, now_iso), daemon=True).start()

    def _run(self, d, epoch, now_iso):
        def should_abort():
            return self.epoch != epoch
        try:
            res = _run_build(d["domain"], now_iso, should_abort)
        except BaseException:
            res = None
        with self.lock:
            if self.epoch != epoch:
                return
            d["building"] = False
            if res is None:
                d["last_outcome"] = "failed"
                return
            try:
                spent = int(_res_get(res, "spent_units", 0) or 0)
            except Exception:
                spent = 0
            d["spent_units"] += max(spent, 0)
            if _res_get(res, "outcome") == "ready":
                d["fields"] = norm_fields(_res_get(res, "fields"), now_iso)
                d["researched_at"] = now_iso
                d["last_outcome"] = "ready"
            else:
                d["last_outcome"] = "failed"

    def idem_write(self, uid, method, path, key, body_cmp, fn):
        """Run fn() -> (status, response) once per (user, method+path, key)."""
        k = (uid, method + " " + path, key)
        with self.lock:
            rec = self.idem.get(k)
            if rec is not None:
                if rec["body"] != body_cmp:
                    raise ApiError(409, "idempotency_key_reuse", "key used with a different body")
                return 200, copy.deepcopy(rec["response"])
            status, response = fn()
            if 200 <= status < 300:
                self.idem[k] = {"body": body_cmp, "response": copy.deepcopy(response)}
            return status, response

    def post_dossier(self, uid, key, path, body):
        cmp = body.get("domain")

        def fn():
            dom = body.get("domain")
            if dom is None:
                raise invalid("domain is required")
            if not isinstance(dom, str):
                raise malformed("domain must be a string")
            domain = normalise_domain(dom)
            d = self.dossiers.get(domain)
            if d is not None:
                return 200, self._brief(d)
            self.seq += 1
            d = {"id": "d_%d" % self.seq, "domain": domain, "last_outcome": None, "building": False,
                 "fields": unknown_fields(), "researched_at": None, "spent_units": 0}
            self.dossiers[domain] = d
            self._start_build(d)
            return 202, self._brief(d)

        return self.idem_write(uid, "POST", path, key, cmp, fn)

    def refresh(self, uid, key, path, raw_domain):
        def fn():
            domain = normalise_domain(raw_domain)
            d = self.dossiers.get(domain)
            if d is None:
                raise ApiError(404, "not_found", "no such dossier")
            if not d["building"]:
                self._start_build(d)
            return 202, self._brief(d)

        return self.idem_write(uid, "POST", path, key, None, fn)

    def _full(self, d):
        return {"dossier_id": d["id"], "domain": d["domain"], "state": self._public_state(d),
                "researched_at": d["researched_at"], "spent_units": d["spent_units"],
                "fields": d["fields"]}

    def get_dossier(self, raw_domain):
        domain = normalise_domain(raw_domain)
        with self.lock:
            d = self.dossiers.get(domain)
            if d is None:
                raise ApiError(404, "not_found", "no such dossier")
            return copy.deepcopy(self._full(d))

    def list_dossiers(self, q, limit, offset):
        ql = q.lower()
        with self.lock:
            items = []
            for dom in sorted(self.dossiers):
                d = self.dossiers[dom]
                ln = d["fields"]["legal_name"]["value"]
                ln = ln if isinstance(ln, str) else None
                if ql and ql not in dom and not (ln is not None and ql in ln.lower()):
                    continue
                items.append({"dossier_id": d["id"], "domain": dom, "state": self._public_state(d),
                              "legal_name": ln, "researched_at": d["researched_at"],
                              "spent_units": d["spent_units"]})
        page = items[offset:offset + limit]
        return {"dossiers": page, "has_more": offset + limit < len(items)}

    # ---- export / import
    def export(self):
        with self.lock:
            dossiers = []
            for d in self.dossiers.values():
                dossiers.append({"id": d["id"], "domain": d["domain"],
                                 "state": d["last_outcome"] or "failed",
                                 "fields": d["fields"], "researched_at": d["researched_at"],
                                 "spent_units": d["spent_units"]})
            state = {
                "users": list(self.users.values()),
                "tokens": dict(self.tokens),
                "dossiers": dossiers,
                "idem": [[k[0], k[1], k[2], v["body"], v["response"]] for k, v in self.idem.items()],
                "seq": self.seq,
            }
            state = copy.deepcopy(state)
        return {"track": "dossier", "format_version": 1, "state": state}

    def import_state(self, obj):
        if not isinstance(obj, dict):
            raise malformed("body must be an object")
        if obj.get("track") != "dossier" or obj.get("format_version") != 1 \
                or not isinstance(obj.get("state"), dict):
            raise invalid("bad track, version or state")
        try:
            new = self._parse_state(copy.deepcopy(obj["state"]))
        except ApiError:
            raise
        except Exception:
            raise invalid("invalid state")
        with self.lock:
            self.epoch += 1
            self.users, self.emails, self.tokens, self.dossiers, self.idem, self.seq = new

    def _parse_state(self, st):
        users, emails = {}, {}
        for u in st["users"]:
            rec = {k: u[k] for k in ("id", "email", "display_name", "pw")}
            if not all(isinstance(v, str) for v in rec.values()):
                raise invalid("bad user")
            users[rec["id"]] = rec
            emails[rec["email"].strip().lower()] = rec["id"]
        tokens = st["tokens"]
        if not isinstance(tokens, dict):
            raise invalid("bad tokens")
        for t, uid in tokens.items():
            if not isinstance(uid, str) or uid not in users:
                raise invalid("bad token")
        dossiers = {}
        for d in st["dossiers"]:
            domain = d["domain"]
            if not isinstance(domain, str) or normalise_domain(domain) != domain:
                raise invalid("bad domain")
            if d["state"] not in ("ready", "failed"):
                raise invalid("bad dossier state")
            if not isinstance(d["id"], str) or len(d["id"]) > 64:
                raise invalid("bad id")
            if d["researched_at"] is not None:
                parse_ts(d["researched_at"])
            spent = d["spent_units"]
            if not isinstance(spent, int) or isinstance(spent, bool) or spent < 0:
                raise invalid("bad spent")
            if not isinstance(d["fields"], dict):
                raise invalid("bad fields")
            dossiers[domain] = {"id": d["id"], "domain": domain, "last_outcome": d["state"],
                                "building": False, "fields": norm_fields(d["fields"], d["researched_at"]),
                                "researched_at": d["researched_at"], "spent_units": spent}
        idem = {}
        for item in st["idem"]:
            uid, mp, key, body, resp = item
            if not (isinstance(uid, str) and isinstance(mp, str) and isinstance(key, str)):
                raise invalid("bad idempotency record")
            idem[(uid, mp, key)] = {"body": body, "response": resp}
        seq = st["seq"]
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise invalid("bad seq")
        return users, emails, tokens, dossiers, idem, seq
