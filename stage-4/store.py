"""State, clock, auth, idempotency, builds bookkeeping, export/import."""
import base64
import copy
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time

FIELD_NAMES = ["legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total"]
ALL_FIELDS = FIELD_NAMES + ["executives", "investors"]
BUILD_CAP = 80
RESUME_DEADLINE = 9.0
from urllib.parse import urlsplit

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
    return {n: {"value": None, "status": "unknown", "true_from": None, "learned_at": None,
                "citations": [], "candidates": [], "origins": [], "corroborated": False,
                "corroborated_since": None} for n in ALL_FIELDS}


# ---------------------------------------------------------------- origins

def host_origin(url):
    """Normalised host of a URL (the origin of an imported candidate that records none)."""
    try:
        h = urlsplit(url).hostname if isinstance(url, str) else None
    except ValueError:
        h = None
    if not h:
        return ""
    try:
        return normalise_domain(h)
    except ApiError:
        return h.lower()


def _member_cands(name, f):
    """For executives/investors: list of (member key, [candidates of that member]); else None."""
    if name not in ("executives", "investors"):
        return None
    out = []
    val = f.get("value")
    if not isinstance(val, list):
        return out
    cands = f.get("candidates") or []
    for m in val:
        if name == "executives":
            if not isinstance(m, dict):
                continue
            key = ("e", m.get("title"), _vk(m.get("name")))
            mine = [c for c in cands if c.get("title") == m.get("title")
                    and _vk(c.get("value")) == _vk(m.get("name"))]
        else:
            key = ("i", _vk(m))
            mine = [c for c in cands if _vk(c.get("value")) == _vk(m)]
        out.append((key, mine))
    return out


def _origins_of(cs):
    return {c.get("origin") for c in cs if c.get("origin")}


def field_keys(name, f):
    """(origins, corroborated) of a field."""
    if f.get("value") is None:
        return [], False
    mem = _member_cands(name, f)
    if mem is None:
        cs = [c for c in f.get("candidates") or [] if _vk(c.get("value")) == _vk(f["value"])]
        o = sorted(_origins_of(cs))
        return o, len(o) >= 2
    allo = set()
    ok = bool(mem)
    for _, cs in mem:
        o = _origins_of(cs)
        allo |= o
        if len(o) < 2:
            ok = False
    return sorted(allo), ok


def _standing_ok(name, seq):
    """seq: field dicts of ready builds, oldest first; is the last one corroborated by standing origins."""
    last = seq[-1]
    if last.get("value") is None:
        return False
    mem = _member_cands(name, last)
    if mem is None:
        o = set()
        for f in reversed(seq):
            if f.get("value") is None or _vk(f["value"]) != _vk(last["value"]):
                break
            o |= _origins_of([c for c in f.get("candidates") or []
                              if _vk(c.get("value")) == _vk(last["value"])])
        return len(o) >= 2
    if not mem:
        return False
    for key, _ in mem:
        o = set()
        for f in reversed(seq):
            m = dict(_member_cands(name, f) or [])
            if key not in m:
                break
            o |= _origins_of(m[key])
        if len(o) < 2:
            return False
    return True


def corroborated_since(name, timed):
    """timed: [(time_iso, fields dict)] of ready builds, oldest first (failed builds excluded)."""
    fl = [f[name] for _, f in timed]
    if not fl or not _standing_ok(name, fl):
        return None
    k = len(fl) - 1
    while k > 0 and _standing_ok(name, fl[:k]):
        k -= 1
    return timed[k][0]


def stamp_keys(fields):
    for n in ALL_FIELDS:
        f = fields[n]
        for c in f.get("candidates") or []:
            if not c.get("origin"):
                c["origin"] = host_origin(c.get("url"))
        f["origins"], f["corroborated"] = field_keys(n, f)
        f.setdefault("corroborated_since", None)
        if f["value"] is None:
            f["corroborated_since"] = None


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
    """Fields in stage-3 shape. A field carrying `candidates` is kept as given (build result or
    stage-2/3 export). A stage-1 field (citations only) gets candidates derived from its citations."""
    out = {}
    raw = raw if isinstance(raw, dict) else {}
    for n in ALL_FIELDS:
        f = raw.get(n)
        if not isinstance(f, dict):
            out[n] = unknown_fields()[n]
        elif isinstance(f.get("candidates"), list):
            cs = [dict(c) for c in f["candidates"] if isinstance(c, dict)]
            if not cs:
                out[n] = unknown_fields()[n]
            else:
                out[n] = {"value": f.get("value"), "status": f.get("status") or "known",
                          "true_from": f.get("true_from"), "learned_at": f.get("learned_at"),
                          "citations": [_clean_cite(c) for c in (f.get("citations") or [])
                                        if isinstance(c, dict)],
                          "candidates": cs,
                          "corroborated_since": f.get("corroborated_since")}
        elif n != "executives" and f.get("value") is not None and isinstance(f.get("citations"), list):
            cites = [_clean_cite(c) for c in f["citations"] if isinstance(c, dict)]
            fobj = {"value": f["value"], "status": "known", "citations": cites}
            cands = _derive(n, fobj, researched_at) if cites else []
            if cands:
                af = _assemble(cands)
                out[n] = {"value": af["value"], "status": af["status"], "true_from": af.get("true_from"),
                          "learned_at": None, "citations": af["citations"], "candidates": af["candidates"]}
            else:
                out[n] = unknown_fields()[n]
        else:
            out[n] = unknown_fields()[n]
    stamp_keys(out)
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

    def _run_build(domain, now_iso, should_abort, budget=None):
        _time.sleep(0.2)
        return _Result("ready", unknown_fields(), 0)


try:
    import inspect as _inspect
    _TAKES_BUDGET = "budget" in _inspect.signature(_run_build).parameters
except Exception:
    _TAKES_BUDGET = False


def _dbg(*a):
    try:
        with open("/tmp/dbg-b.log", "a") as fh:
            fh.write("%.2f %s
" % (time.time() % 1000, " ".join(map(str, a))))
    except Exception:
        pass


class BuildBudget:
    """One build's view of its budget: the per-build cap (kept across restarts) and, for a batch's
    build, the batch's shared budget. reserve() before a call, settle() after it."""

    def __init__(self, store, d, batch, epoch):
        self.store, self.d, self.batch, self.epoch = store, d, batch, epoch
        self.spent = int(d.get("cur_spent") or 0)
        self.reserved = 0
        self.refused = False

    def reserve(self, n):
        n = int(n)
        with self.store.lock:
            if n <= 0:
                return True
            if self.store.epoch != self.epoch:
                return False
            b = self.batch
            if self.spent + self.reserved + n > BUILD_CAP or (
                    b is not None and b["spent"] + b["reserved"] + n > b["limit"]):
                self.refused = True
                _dbg("refuse", self.d["domain"], n, self.spent, self.reserved, b and (b["spent"], b["reserved"]))
                return False
            self.reserved += n
            if b is not None:
                b["reserved"] += n
            _dbg("reserve", self.d["domain"], n, "spent", self.spent, "res", self.reserved, "batch", b and (b["spent"], b["reserved"]))
            # persisted before the call: a call in flight at a kill is charged after the restart
            self.d["cur_reserved"] = self.reserved
            self.store._persist()
            return True

    def settle(self, reserved, actual):
        reserved, actual = max(int(reserved), 0), max(int(actual), 0)
        with self.store.lock:
            if self.store.epoch != self.epoch:
                return
            self.reserved = max(self.reserved - reserved, 0)
            actual = min(actual, reserved, BUILD_CAP - self.spent)
            self.spent += actual
            self.d["cur_spent"] = self.spent
            b = self.batch
            if b is not None:
                b["reserved"] = max(b["reserved"] - reserved, 0)
                b["spent"] += actual
            self.d["cur_reserved"] = self.reserved
            _dbg("settle", self.d["domain"], reserved, actual, "spent", self.spent)
            self.store._persist()


def _res_get(res, name, default=None):
    if isinstance(res, dict):
        return res.get(name, default)
    return getattr(res, name, default)


# ---------------------------------------------------------------- timeline helpers

def _vk(v):
    if isinstance(v, str):
        v = v.strip()
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def _cand_key(field, c):
    try:
        import candidates as C
        return tuple(C.cand_key(field, c))
    except Exception:
        return (field, c.get("title"), _vk(c.get("value")), c.get("url"), c.get("provider"))


def _seen_key(field, c):
    return json.dumps(_cand_key(field, c), ensure_ascii=False, default=str)


def _date_of(published_at):
    """UTC date part of an RFC 3339 timestamp, else None."""
    if not isinstance(published_at, str):
        return None
    try:
        return parse_ts(published_at).astimezone(dt.timezone.utc).date().isoformat()
    except Exception:
        return None


def _import_pages(cands_by_field):
    try:
        import timeline
        return timeline.import_pages(cands_by_field)
    except Exception:
        pass
    pages = {}
    for f, cs in cands_by_field.items():
        for c in cs:
            u = c.get("url")
            p = pages.setdefault(u, {"url": u, "true_from": _date_of(c.get("published_at")),
                                     "candidates": {n: [] for n in ALL_FIELDS}})
            p["candidates"][f].append(c)
    return list(pages.values())


def _classify(field, prev, new):
    try:
        import timeline
        return timeline.classify(field, prev, new)
    except ImportError:
        pass
    if _vk(prev.get("value")) == _vk(new.get("value")):
        return None
    pt, nt = prev.get("true_from"), new.get("true_from")
    if prev.get("value") is not None and new.get("value") is not None \
            and pt is not None and nt is not None and nt <= pt:
        return "correction"
    return "change"


def _field_view(f):
    return {"value": f.get("value"), "true_from": f.get("true_from")}


def _sel_true_from(f):
    if "true_from" in f and f["true_from"] is not None:
        return f["true_from"]
    for c in f.get("candidates", []):
        if c.get("selected"):
            return c.get("true_from")
    return None


def _state_dir():
    d = os.environ.get("DOSSIER_STATE_DIR") or "/var/lib/dossier"
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".probe")
        with open(probe, "w") as fh:
            fh.write("x")
        os.remove(probe)
        return d
    except OSError:
        d = os.path.join(os.path.expanduser("~"), ".dossier-state")
        os.makedirs(d, exist_ok=True)
        return d


def _jsonable_build_state(builds):
    return builds


# ---------------------------------------------------------------- store

class Store:
    def __init__(self, persist=True):
        self.lock = threading.RLock()
        self.clock = None  # None -> follow system time
        self.epoch = 0
        self._fresh()
        self.path = None
        if persist:
            try:
                self.path = os.path.join(_state_dir(), "state.json")
            except OSError:
                self.path = None
            self._load()

    def _fresh(self):
        self.users = {}      # id -> {id,email,display_name,pw}
        self.emails = {}     # lower email -> id
        self.tokens = {}     # token -> user id
        self.dossiers = {}   # domain -> dict
        self.idem = {}       # (uid, "METHOD path", key) -> {"body":..., "response":...}
        self.seq = 0
        self.feed = []       # feed entries
        self.feed_seq = 0
        self.batches = {}    # id -> batch dict
        self.bseq = 0

    # ---- persistence
    def _persist(self):
        if not self.path:
            return
        with self.lock:
            snap = self._dump()
            snap["clock"] = self.clock.isoformat() if self.clock is not None else None
            data = json.dumps(snap, ensure_ascii=False).encode("utf-8")
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.path)
                try:
                    fd = os.open(os.path.dirname(self.path), os.O_RDONLY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                except OSError:
                    pass
            except OSError as e:
                print("persist failed:", repr(e), file=sys.stderr)

    def _load(self):
        try:
            with open(self.path, "rb") as fh:
                snap = json.loads(fh.read().decode("utf-8"))
            new = self._parse_state(snap, restore=True)
        except Exception:
            return
        with self.lock:
            (self.users, self.emails, self.tokens, self.dossiers, self.idem, self.seq,
             self.feed, self.feed_seq, self.batches, self.bseq) = new
            if snap.get("clock"):
                try:
                    self.clock = parse_ts(snap["clock"])
                except Exception:
                    self.clock = None
            for d in self.dossiers.values():
                if d["building"]:
                    _dbg("resume", d["domain"], d.get("cur_spent"), d.get("build_batch"), {k:(v["spent"]) for k,v in self.batches.items()})
                    self._start_build(d, d.get("build_batch"), resumed=True)

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
            self._persist()

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
            self._persist()

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
            self._persist()
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
            self._persist()
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

    def _new_dossier(self, domain):
        self.seq += 1
        return {"id": "d_%d" % self.seq, "domain": domain, "last_outcome": None, "building": False,
                "fields": unknown_fields(), "researched_at": None, "spent_units": 0,
                "base_spent": 0, "builds": [], "history": {n: [] for n in ALL_FIELDS}, "seen": {},
                "cur_spent": 0, "cur_reserved": 0, "build_batch": None}

    def _start_build(self, d, batch_id=None, resumed=False):
        d["building"] = True
        if not resumed:
            d["cur_spent"] = 0
            d["build_batch"] = batch_id
        d["cur_reserved"] = 0
        epoch = self.epoch
        now_iso = self.now_iso()
        batch = self.batches.get(d.get("build_batch"))
        budget = BuildBudget(self, d, batch, epoch)
        threading.Thread(target=self._run, args=(d, epoch, now_iso, budget, resumed),
                         daemon=True).start()

    def _run(self, d, epoch, now_iso, budget, resumed=False):
        t0 = time.monotonic()

        def should_abort():
            if self.epoch != epoch:
                return True
            return resumed and time.monotonic() - t0 > RESUME_DEADLINE
        try:
            if _TAKES_BUDGET:
                res = _run_build(d["domain"], now_iso, should_abort, budget=budget)
            else:
                res = _run_build(d["domain"], now_iso, should_abort)
        except BaseException:
            res = None
        with self.lock:
            if self.epoch != epoch:
                return
            d["building"] = False
            try:
                if resumed and budget.refused and _res_get(res, "outcome") == "ready":
                    res = None  # a build cut short by its budget after a restart leaves fields as they were
                self._complete(d, res, now_iso, budget)
            except Exception as e:
                print("build completion failed:", repr(e), file=sys.stderr)
                d["last_outcome"] = "failed"
            d["cur_spent"] = 0
            self._persist()

    def _complete(self, d, res, now_iso, budget=None):
        failed = {"time": now_iso, "outcome": "failed", "spent": 0, "fields": None,
                  "pages": [], "researched_at": None}
        try:
            spent = max(int(_res_get(res, "spent_units", 0) or 0), 0) if res is not None else 0
        except Exception:
            spent = 0
        if budget is not None:
            extra = spent - budget.spent
            if extra > 0 and budget.batch is not None:  # spend the build reports but did not settle
                b = budget.batch
                b["spent"] += max(min(extra, b["limit"] - b["spent"]), 0)
            spent = max(spent, budget.spent)
        d["spent_units"] += spent
        failed["spent"] = spent
        if res is None:
            d["last_outcome"] = "failed"
            d["builds"].append(failed)
            return
        if _res_get(res, "outcome") != "ready":
            d["last_outcome"] = "failed"
            d["builds"].append(failed)
            return
        fields = norm_fields(_res_get(res, "fields"), now_iso)
        prev = d["fields"]
        first_ready = not any(b["outcome"] == "ready" for b in d["builds"])
        seen = d["seen"]
        for n in ALL_FIELDS:
            f = fields[n]
            for c in f["candidates"]:
                c["learned_at"] = seen.setdefault(_seen_key(n, c), now_iso)
                c.setdefault("true_from", None)
            if f["value"] is None:
                f["true_from"] = None
                f["learned_at"] = None
            else:
                f["true_from"] = f.get("true_from") if n == "investors" else _sel_true_from(f)
                p = prev.get(n) or {}
                keep = p.get("value") is not None and _vk(p.get("value")) == _vk(f["value"])
                f["learned_at"] = (p.get("learned_at") if keep else None) or now_iso
        for n in ALL_FIELDS:
            p, f = prev.get(n) or {"value": None, "true_from": None}, fields[n]
            if _vk(p.get("value")) == _vk(f.get("value")):
                continue
            hist = d["history"][n]
            if not hist and first_ready:
                typ = "initial" if f["value"] is not None else None
            else:
                typ = _classify(n, p, f) or "change"
            if typ is None:
                continue
            hist.append(self._hist_entry(typ, f))
            if typ != "initial":
                self.feed_seq += 1
                self.feed.append({"seq": self.feed_seq, "domain": d["domain"], "field": n,
                                  "type": typ, "from": copy.deepcopy(p.get("value")),
                                  "to": copy.deepcopy(f.get("value")), "true_from": f.get("true_from"),
                                  "learned_at": now_iso})
        timed = [(b["time"], b["fields"]) for b in d["builds"]
                 if b["outcome"] == "ready" and b.get("fields")] + [(now_iso, fields)]
        for n in ALL_FIELDS:
            fields[n]["corroborated_since"] = corroborated_since(n, timed)
        d["fields"] = fields
        d["researched_at"] = now_iso
        d["last_outcome"] = "ready"
        d["builds"].append({"time": now_iso, "outcome": "ready", "spent": spent,
                            "fields": copy.deepcopy(fields), "researched_at": now_iso,
                            "pages": self._pages(fields, _res_get(res, "pages"))})

    @staticmethod
    def _hist_entry(typ, f):
        has = f.get("value") is not None
        return {"type": typ, "value": copy.deepcopy(f.get("value")),
                "true_from": f.get("true_from") if has else None,
                "learned_at": f.get("learned_at") if has else None,
                "citations": copy.deepcopy(f.get("citations") or []) if has else []}

    @staticmethod
    def _pages(fields, result_pages):
        pages = {}

        def page(url, tf):
            if url not in pages:
                pages[url] = {"url": url, "true_from": tf, "candidates": {n: [] for n in ALL_FIELDS}}
            return pages[url]
        for p in (result_pages or []):
            if isinstance(p, dict) and isinstance(p.get("url"), str):
                page(p["url"], p.get("true_from"))
        for n in ALL_FIELDS:
            for c in fields[n]["candidates"]:
                page(c.get("url"), c.get("true_from"))["candidates"][n].append(copy.deepcopy(c))
        return list(pages.values())

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
                self._persist()
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
            d = self._new_dossier(domain)
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

    # ---- batches
    def _batch_view(self, b):
        running = any(self.dossiers.get(dm) is not None and self.dossiers[dm]["building"]
                      and self.dossiers[dm].get("build_batch") == b["id"] for dm in b["started"])
        return {"batch_id": b["id"], "state": "running" if running else "done",
                "budget_units": b["limit"], "spent_units": b["spent"],
                "dossiers": [{"domain": dm, "state": self._public_state(self.dossiers[dm])
                              if dm in self.dossiers else "failed"} for dm in b["domains"]]}

    def post_batch(self, uid, key, path, body):
        def fn():
            doms = body.get("domains")
            if doms is None:
                raise invalid("domains is required")
            if not isinstance(doms, list):
                raise malformed("domains must be a list")
            if len(doms) == 0 or len(doms) > 50:
                raise invalid("domains must hold 1 to 50 entries")
            norm = []
            for x in doms:
                if not isinstance(x, str):
                    raise malformed("domain must be a string")
                norm.append(normalise_domain(x))
            if len(set(norm)) != len(norm):
                raise invalid("duplicate domains")
            bu = body.get("budget_units")
            if isinstance(bu, float) and abs(bu) < 1e15 and bu == int(bu):
                bu = int(bu)
            if bu is None or isinstance(bu, bool) or not isinstance(bu, int) \
                    or bu < 1 or bu > 100000:
                raise invalid("budget_units must be an integer from 1 to 100000")
            self.bseq += 1
            b = {"id": "b_%d" % self.bseq, "uid": uid, "limit": bu, "spent": 0, "reserved": 0,
                 "domains": norm, "started": []}
            self.batches[b["id"]] = b
            for dm in norm:
                if dm in self.dossiers:
                    continue
                d = self._new_dossier(dm)
                self.dossiers[dm] = d
                b["started"].append(dm)
                self._start_build(d, b["id"])
            return 202, self._batch_view(b)

        return self.idem_write(uid, "POST", path, key, body, fn)

    def get_batch(self, uid, bid):
        with self.lock:
            b = self.batches.get(bid)
            if b is None or b["uid"] != uid:
                raise ApiError(404, "not_found", "no such batch")
            return copy.deepcopy(self._batch_view(b))

    def _full(self, d):
        return {"dossier_id": d["id"], "domain": d["domain"], "state": self._public_state(d),
                "researched_at": d["researched_at"], "spent_units": d["spent_units"],
                "fields": d["fields"]}

    def _find(self, raw_domain):
        domain = normalise_domain(raw_domain)
        d = self.dossiers.get(domain)
        if d is None:
            raise ApiError(404, "not_found", "no such dossier")
        return d

    def get_dossier(self, raw_domain, as_of=None):
        asd = parse_ts(as_of) if as_of is not None else None
        domain = normalise_domain(raw_domain)
        with self.lock:
            d = self.dossiers.get(domain)
            if d is None:
                raise ApiError(404, "not_found", "no such dossier")
            if asd is None:
                return copy.deepcopy(self._full(d))
            b = self._build_at(d, asd)
            if b is None:
                raise ApiError(404, "not_found", "no build at that time")
            spent = d["base_spent"] + sum(x["spent"] for x in d["builds"]
                                          if parse_ts(x["time"]) <= asd)
            return copy.deepcopy({"dossier_id": d["id"], "domain": d["domain"], "state": "ready",
                                  "researched_at": b["researched_at"], "spent_units": spent,
                                  "fields": b["fields"]})

    @staticmethod
    def _build_at(d, asd):
        best, best_key = None, None
        for i, b in enumerate(d["builds"]):
            if b["outcome"] != "ready":
                continue
            t = parse_ts(b["time"])
            if t > asd:
                continue
            k = (t, i)
            if best_key is None or k >= best_key:
                best, best_key = b, k
        return best

    def values(self, raw_domain, true_at, as_of):
        with self.lock:
            d = self._find(raw_domain)
            asd = parse_ts(as_of) if as_of is not None else self.now()
            if self._build_at(d, asd) is None:
                raise ApiError(404, "not_found", "no build at that time")
            builds = [{"time": b["time"], "outcome": b["outcome"], "pages": b["pages"]}
                      for b in d["builds"]]
            as_of_iso = as_of if as_of is not None else self.now_iso()
            import timeline
            got = timeline.values_at(copy.deepcopy(builds), true_at, as_of_iso)
            fields = {}
            for n in ALL_FIELDS:
                g = got.get(n) or {}
                fields[n] = {"value": g.get("value"), "true_from": g.get("true_from"),
                             "citations": g.get("citations") or []}
            return {"domain": d["domain"], "true_at": true_at, "as_of": as_of_iso, "fields": fields}

    def history(self, raw_domain):
        with self.lock:
            d = self._find(raw_domain)
            return {"domain": d["domain"],
                    "fields": {n: copy.deepcopy(d["history"].get(n, [])) for n in ALL_FIELDS}}

    def changes(self, since, limit):
        with self.lock:
            items = [e for e in self.feed if e["seq"] > since]
            return {"changes": copy.deepcopy(items[:limit]), "has_more": len(items) > limit}

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
    def _dump(self):
        with self.lock:
            dossiers = []
            for d in self.dossiers.values():
                dossiers.append({"id": d["id"], "domain": d["domain"],
                                 "state": d["last_outcome"] or "failed",
                                 "building": bool(d["building"]),
                                 "fields": d["fields"], "researched_at": d["researched_at"],
                                 "spent_units": d["spent_units"], "base_spent": d["base_spent"],
                                 "builds": d["builds"], "history": d["history"], "seen": d["seen"],
                                 "cur_spent": d.get("cur_spent", 0),
                                 "cur_reserved": d.get("cur_reserved", 0),
                                 "build_batch": d.get("build_batch")})
            state = {
                "users": list(self.users.values()),
                "tokens": dict(self.tokens),
                "dossiers": dossiers,
                "idem": [[k[0], k[1], k[2], v["body"], v["response"]] for k, v in self.idem.items()],
                "seq": self.seq,
                "feed": self.feed,
                "feed_seq": self.feed_seq,
                "batches": [{k: b[k] for k in ("id", "uid", "limit", "spent", "domains", "started")}
                            | {"reserved": b.get("reserved", 0)}
                            for b in self.batches.values()],
                "bseq": self.bseq,
            }
            return copy.deepcopy(state)

    def export(self):
        state = self._dump()
        for d in state["dossiers"]:
            d.pop("building", None)
            d["cur_spent"], d["cur_reserved"], d["build_batch"] = 0, 0, None
        for b in state["batches"]:
            b["spent"] = min(b["spent"] + b.pop("reserved", 0), b["limit"])
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
            keep = self.bseq
            (self.users, self.emails, self.tokens, self.dossiers, self.idem, self.seq,
             self.feed, self.feed_seq, self.batches, self.bseq) = new
            self.bseq = max(self.bseq, keep)
            self._persist()

    def _parse_state(self, st, restore=False):
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
            dossiers[domain] = self._import_dossier(d, domain, spent)
            if not restore:
                self._restamp(dossiers[domain])
            if restore and d.get("building"):
                dossiers[domain]["building"] = True
                dossiers[domain]["cur_spent"] = min(int(d.get("cur_spent") or 0)
                                                    + int(d.get("cur_reserved") or 0), BUILD_CAP)
                dossiers[domain]["build_batch"] = d.get("build_batch")
        idem = {}
        for item in st["idem"]:
            uid, mp, key, body, resp = item
            if not (isinstance(uid, str) and isinstance(mp, str) and isinstance(key, str)):
                raise invalid("bad idempotency record")
            idem[(uid, mp, key)] = {"body": body, "response": resp}
        seq = st["seq"]
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise invalid("bad seq")
        feed, feed_seq = [], 0
        if isinstance(st.get("feed"), list):
            for e in st["feed"]:
                feed.append({k: e[k] for k in ("seq", "domain", "field", "type", "from", "to",
                                               "true_from", "learned_at")})
            feed_seq = max([e["seq"] for e in feed] + [int(st.get("feed_seq") or 0)])
        batches, bseq = {}, 0
        for b in (st.get("batches") or []):
            rec = {"id": b["id"], "uid": b["uid"], "limit": b["limit"], "spent": b["spent"],
                   "reserved": 0, "domains": list(b["domains"]), "started": list(b["started"])}
            if not isinstance(rec["id"], str) or not isinstance(rec["limit"], int) \
                    or not isinstance(rec["spent"], int):
                raise invalid("bad batch")
            if restore:  # units reserved for calls in flight at the stop count as spent
                rec["spent"] = min(rec["spent"] + int(b.get("reserved") or 0), rec["limit"])
            batches[rec["id"]] = rec
            m = re.fullmatch(r"b_(\d+)", rec["id"])
            if m:
                bseq = max(bseq, int(m.group(1)))
        if isinstance(st.get("bseq"), int) and not isinstance(st.get("bseq"), bool):
            bseq = max(bseq, st["bseq"])
        for d in dossiers.values():
            if d.get("building") and d.get("build_batch") not in batches:
                d["build_batch"] = None
        return users, emails, tokens, dossiers, idem, seq, feed, feed_seq, batches, bseq

    @staticmethod
    def _norm_pages(pages):
        out = []
        for p in (pages or []):
            if not isinstance(p, dict):
                continue
            p = dict(p)
            cm = {n: [dict(c) for c in ((p.get("candidates") or {}).get(n) or [])] for n in ALL_FIELDS}
            for cs in cm.values():
                for c in cs:
                    if not c.get("origin"):
                        c["origin"] = host_origin(c.get("url"))
            p["candidates"] = cm
            out.append(p)
        return out

    def _restamp(self, d):
        """After an import: origin keys and corroborated_since for the current fields and each build."""
        timed = []
        for b in d["builds"]:
            if b["outcome"] != "ready" or not b.get("fields"):
                continue
            b["pages"] = self._norm_pages(b.get("pages"))
            stamp_keys(b["fields"])
            timed.append((b["time"], b["fields"]))
            for n in ALL_FIELDS:
                b["fields"][n]["corroborated_since"] = corroborated_since(n, timed)
        stamp_keys(d["fields"])
        for n in ALL_FIELDS:
            d["fields"][n]["corroborated_since"] = timed[-1][1][n]["corroborated_since"] if timed else None

    def _import_dossier(self, d, domain, spent):
        ra = d["researched_at"]
        out = {"id": d["id"], "domain": domain, "last_outcome": d["state"], "building": False,
               "researched_at": ra, "spent_units": spent, "base_spent": 0, "builds": [],
               "history": {n: [] for n in ALL_FIELDS}, "seen": {},
               "cur_spent": 0, "cur_reserved": 0, "build_batch": None}
        if isinstance(d.get("builds"), list) and isinstance(d.get("history"), dict) \
                and isinstance(d.get("seen"), dict):
            # stage-3 state: restore as it was
            out["fields"] = norm_fields(d["fields"], ra)
            out["base_spent"] = int(d.get("base_spent") or 0)
            out["builds"] = []
            for b in d["builds"]:
                b = dict(b)
                if b.get("outcome") == "ready" and isinstance(b.get("fields"), dict):
                    b["fields"] = norm_fields(b["fields"], b.get("time"))
                out["builds"].append(b)
            out["history"] = {n: list(d["history"].get(n) or []) for n in ALL_FIELDS}
            out["seen"] = d["seen"]
            return out
        fields = norm_fields(d["fields"], ra)
        for n in ALL_FIELDS:
            f = fields[n]
            for c in f["candidates"]:
                c["true_from"] = _date_of(c.get("published_at"))
                c["learned_at"] = c.get("retrieved_at") or ra
                out["seen"][_seen_key(n, c)] = c["learned_at"]
            if f["value"] is None:
                f["true_from"], f["learned_at"] = None, None
            else:
                f["true_from"] = _sel_true_from(f)
                f["learned_at"] = ra
                out["history"][n].append(self._hist_entry("initial", f))
        out["fields"] = fields
        foreign = d.get("builds")
        if isinstance(foreign, list) and foreign:
            for b in foreign:
                if not isinstance(b, dict):
                    continue
                t = b.get("time") or b.get("started_at") or b.get("at")
                if not isinstance(t, str):
                    continue
                parse_ts(t)
                oc = "ready" if b.get("outcome") == "ready" else "failed"
                try:
                    sp = max(int(b.get("spent_units", b.get("spent", 0)) or 0), 0)
                except Exception:
                    sp = 0
                rec = {"time": t, "outcome": oc, "spent": sp, "fields": None, "pages": [],
                       "researched_at": None}
                if oc == "ready":
                    bf = norm_fields(b.get("fields") if b.get("fields") is not None else d["fields"], t)
                    cbf = {}
                    for n in ALL_FIELDS:
                        f = bf[n]
                        for c in f["candidates"]:
                            c["true_from"] = _date_of(c.get("published_at"))
                            c.setdefault("learned_at", c.get("retrieved_at") or t)
                            out["seen"].setdefault(_seen_key(n, c), c["learned_at"])
                        cbf[n] = f["candidates"]
                        if f["value"] is None:
                            f["true_from"], f["learned_at"] = None, None
                        else:
                            f["true_from"] = _sel_true_from(f)
                            f["learned_at"] = t
                            for h in out["history"][n]:
                                if _vk(h["value"]) == _vk(f["value"]):
                                    f["true_from"], f["learned_at"] = h["true_from"], h["learned_at"]
                                    break
                    rec["fields"] = bf
                    rec["researched_at"] = t
                    rec["pages"] = _import_pages(cbf)
                out["builds"].append(rec)
            if out["builds"]:
                return out
        if ra is not None:
            cbf = {n: fields[n]["candidates"] for n in ALL_FIELDS}
            out["builds"].append({"time": ra, "outcome": "ready", "spent": spent,
                                  "fields": copy.deepcopy(fields), "researched_at": ra,
                                  "pages": _import_pages(copy.deepcopy(cbf))})
        else:
            out["base_spent"] = spent
        return out
