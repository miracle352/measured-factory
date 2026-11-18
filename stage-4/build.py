"""Dossier build: gather evidence through WebRouter, decide the six fields, track spend.

    run_build(domain, now_iso, should_abort) -> BuildResult

Blocking; run it in a worker thread.  Never raises.  A build makes exactly one non-error search whose
query is the normalised domain, researches through nimble asking for all six fields, extracts the pages the
search returned, validates every research claim and every cited excerpt with support.py against text that
was actually served, and never lets its spend exceed MAX_UNITS (80).

Stage 2: page text is what a browser shows once the page has loaded (Nimble extract with render=True, 3 units per
URL).  Search results only name pages; every candidate is read from rendered text.  Fields come back assembled
(candidates.assemble_field) with candidates, kind and publication time.
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

import candidates as cand_mod
import support
from support import FIELDS, EXEC_TITLES

MAX_UNITS = 80

# Cost table (§9)
SEARCH_COST = {"nimble": {"lite": 1, "fast": 5, "deep": 15}, "tavily": {"lite": 8, "fast": 16, "deep": 16}}
EXTRACT_COST = {"nimble": 1, "tavily": 2}
RENDER_COST = 3  # nimble extract with provider_options={"render": True}
RESEARCH_COST = 25

# Timing.  Real providers are far slower than a local stand-in (a Nimble search can take 10+ s, a research run
# about a minute), so waits are generous; nothing here is tuned to a mock.
CALL_TIMEOUT = 45.0           # one search / extract request
RESEARCH_TIMEOUT = 170.0      # wait for a research run after it was accepted
RESEARCH_CREATE_TIMEOUT = 45.0
STOP_NEW_CALLS_AFTER = 190.0  # seconds since the build started; calls in flight still finish by ~240 s
RETRY_PAUSE = 1.1             # a provider may refuse the same call again for a second after a 429
MAX_REFUSAL_RETRIES = 3       # 429, 429, 429 then a normal answer
FAST_RETRY_UNTIL = 7.0        # while every provider answers within a second, retries stop after this much working time (waits after a 429 excluded)
MAX_BACKOFF_TOTAL = 40.0      # summed pause allowed once any provider has been seen answering slowly

TRUNCATED_CAP = {"lite": 300, "fast": 1500}


@dataclass
class Options:
    search_depth: str = "lite"       # depth of the domain search ("lite" | "fast" | "deep")
    research: bool = True
    extract_results: bool = True     # extract the URLs the searches returned (full text)
    followups: bool = True           # targeted searches for fields still unknown
    max_followups: int = 6
    followup_depth: str = "lite"
    render: bool = True              # extract through a browser (3 units/URL); False = plain extract (1 unit/URL)


@dataclass
class BuildResult:
    outcome: str                                 # 'ready' | 'failed'
    fields: dict | None                          # None when the build failed (keep the previous fields)
    spent_units: int
    log: list = dc_field(default_factory=list)   # (kind, detail, cost) per provider call, for measurement
    pages: list = dc_field(default_factory=list)  # [{"url", "true_from"}] for every URL whose page text was read
    all_failed: bool = False                     # every provider call that was made failed (a failed build)


# --------------------------------------------------------------------------- router

_router_lock = threading.Lock()
_router = None


def _get_router():
    global _router
    with _router_lock:
        if _router is None:
            from web_router import WebRouter

            if os.environ.get("NIMBLE_BASE_URL", None) == "":
                os.environ.pop("NIMBLE_BASE_URL")
            config: dict[str, dict[str, Any]] = {"nimble": {"max_retries": 0, "timeout": CALL_TIMEOUT}}
            if os.environ.get("NIMBLE_BASE_URL"):
                config["nimble"]["base_url"] = os.environ["NIMBLE_BASE_URL"]
            tavily_base = os.environ.get("TAVILY_BASE_URL")
            if tavily_base:
                config["tavily"] = {"api_base_url": tavily_base}
            for name, var in (("kernel", "KERNEL_BASE_URL"), ("browserbase", "BROWSERBASE_BASE_URL")):
                if os.environ.get(var):
                    config[name] = {"base_url": os.environ[var]}
            _router = WebRouter("nimble", provider_config=config, router=None)
        return _router


# --------------------------------------------------------------------------- evidence

@dataclass
class Evidence:
    field: str
    value: Any
    url: str
    excerpt: str
    provider: str
    kind: str
    published_at: str | None
    true_from: str | None = None


def _header_info(header: list[str]) -> dict[str, str]:
    info = {}
    for line in header:
        name, _, value = line.partition(":")
        info[name.strip().lower()] = value.strip()
    return info


class Gathered:
    """Browser texts the providers served, per page, and the evidence derived from them."""

    def __init__(self, domain: str):
        self.domain = domain
        self.lock = threading.Lock()
        self.full: dict[str, str] = {}            # url -> rendered text (what a browser shows after load)
        self.provider: dict[str, str] = {}
        self.evidence: list[Evidence] = []
        self._seen: set[tuple] = set()
        self.pages: dict[str, str | None] = {}    # url -> true_from, for every page read
        self.meta: dict[str, dict] = {}           # url -> {"lineage", "lookalike"}

    def add_text(self, url: str, text: str, provider: str) -> None:
        if not url or not isinstance(text, str):
            return
        header, prose = support.split_header(text)
        info = _header_info(header)
        lin = cand_mod.lineage(info, url)
        kind = cand_mod.page_kind(info.get("kind"), url, self.domain)
        if kind == "own" and lin["registrant"] != self.domain:
            kind = "aggregator"                   # only the company's registrant publishes an own page
        lookalike = info.get("kind", "").strip() == "own" and lin["registrant"] != lin["own_host"]
        published = cand_mod.parse_published(info.get("published"))
        true_from = cand_mod.page_true_from(info.get("effective"), published)
        with self.lock:
            if url in self.full:
                return
            self.full[url] = text
            self.provider[url] = provider
            self.pages[url] = true_from
            self.meta[url] = {"lineage": lin, "lookalike": lookalike}
        if not text:
            return
        for sent in support.sentences(prose):
            self._scan_sentence(url, sent, provider, kind, published, true_from)

    def _scan_sentence(self, url: str, sent: str, provider: str, kind: str, published: str | None,
                       true_from: str | None = None) -> None:
        sent = support.collapse_ws(sent)
        if not sent or len(sent) > 500:
            return
        for f in FIELDS + EXEC_TITLES + ("investors",):
            vals = support.extract_values(f, sent, self.domain)
            if f == "investors":
                for v in vals:
                    key = (f, url, sent, provider, v)
                    with self.lock:
                        if key in self._seen:
                            continue
                        self._seen.add(key)
                        self.evidence.append(Evidence(f, v, url, sent, provider, kind, published, true_from))
                continue
            if len(vals) == 1:
                key = (f, url, sent, provider)
                with self.lock:
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    self.evidence.append(Evidence(f, vals[0], url, sent, provider, kind, published, true_from))

    def origin_of(self, url: str) -> str:
        """Origin of a page (stage 4): First-Published-By, else the origin of its original, else the company's
        domain for a lookalike, else its registrant.  Rule 2 follows at most three Canonical URLs."""
        cur, hops = url, 0
        while True:
            m = self.meta.get(cur)
            if m is None:
                return cand_mod.normalise_host(cur)
            lin = m["lineage"]
            if lin["first_published_by"]:
                return lin["first_published_by"]
            canon = lin["canonical"]
            if canon is None:
                return self.domain if m["lookalike"] else lin["registrant"]
            if hops >= 3 or canon not in self.meta:
                return cand_mod.normalise_host(canon)
            cur, hops = canon, hops + 1

    def missing_originals(self) -> list[str]:
        """Canonical URLs whose pages rule 2 needs and that were not gathered."""
        need: list[str] = []
        with self.lock:
            metas = dict(self.meta)
        for url in metas:
            cur, hops = url, 0
            while True:
                m = metas.get(cur)
                if m is None:
                    break
                lin = m["lineage"]
                if lin["first_published_by"] or lin["canonical"] is None or hops >= 3:
                    break
                c = lin["canonical"]
                if c not in metas:
                    need.append(c)
                    break
                cur, hops = c, hops + 1
        return list(dict.fromkeys(need))

    def decide(self, now_iso: str | None) -> dict:
        """Assemble every field from its candidates (candidates.assemble_field)."""
        out = {}
        origins: dict[str, str] = {}
        for f in FIELDS + ("executives", "investors"):
            with self.lock:
                cands = []
                for e in self.evidence:
                    if f == "executives":
                        if e.field not in EXEC_TITLES:
                            continue
                    elif e.field != f:
                        continue
                    if e.url not in origins:
                        origins[e.url] = self.origin_of(e.url)
                    c = {"value": e.value, "url": e.url, "excerpt": e.excerpt, "provider": e.provider,
                         "kind": e.kind, "published_at": e.published_at, "retrieved_at": now_iso,
                         "true_from": e.true_from, "origin": origins[e.url]}
                    if f == "executives":
                        c["title"] = e.field
                    cands.append(c)
            out[f] = cand_mod.assemble_field(cands, f)
        return out

    def page_list(self) -> list[dict]:
        with self.lock:
            return [{"url": u, "true_from": tf} for u, tf in self.pages.items()]

    def unknown_fields(self) -> list[str]:
        with self.lock:
            have = {e.field for e in self.evidence}
        return [f for f in FIELDS if f not in have]


def _claim_matches(f: str, claimed: Any, value: Any) -> bool:
    try:
        if f in ("founded_year", "funding_total"):
            if isinstance(claimed, bool):
                return False
            if isinstance(claimed, str):
                claimed = claimed.replace(",", "").strip()
            return int(float(claimed)) == value and float(claimed) == int(float(claimed))
        if f == "headcount_range":
            if isinstance(claimed, (int, float)) and not isinstance(claimed, bool):
                return support.headcount_range(int(claimed)) == value
            return str(claimed).strip() == value
        return support.collapse_ws(str(claimed)).casefold() == support.collapse_ws(str(value)).casefold()
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------- the build

class _Stop(Exception):
    pass


def _original(exc: BaseException):
    seen = 0
    cur: Any = exc
    while cur is not None and seen < 6:
        status = getattr(cur, "status_code", None)
        if isinstance(status, int) and status >= 400:
            return cur
        nxt = getattr(cur, "original", None) or cur.__cause__
        if nxt is None:
            return cur
        cur = nxt
        seen += 1
    return cur


def _is_refusal(exc: BaseException) -> bool:
    """True when the provider answered with an error status (such a call costs nothing)."""
    cur: Any = exc
    for _ in range(6):
        status = getattr(cur, "status_code", None)
        if isinstance(status, int) and status >= 400 and type(cur).__name__ not in ("ExtractFailure",):
            name = type(cur).__name__.lower()
            if "timeout" not in name and "connection" not in name:
                return True
        cur = getattr(cur, "original", None) or getattr(cur, "__cause__", None)
        if cur is None:
            break
    return False


class _Build:
    def __init__(self, domain: str, should_abort: Callable[[], bool], options: Options, now_iso: str | None = None,
                 budget=None):
        self.budget = budget
        self.budget_refused = False
        self.attempted = 0
        self.domain = domain
        self.now_iso = now_iso
        self.name = support.company_name(domain)
        self.display = " ".join(w.capitalize() for w in self.name.split())
        self.should_abort = should_abort or (lambda: False)
        self.opt = options
        self.start = time.monotonic()
        self.lock = threading.Lock()
        self.spent = 0
        self.reserved = 0
        self.backoff_used = 0.0
        self.waiters = 0              # threads currently waiting to repeat a call after a 429
        self.wait_mark = 0.0
        self.waited = 0.0             # wall time during which at least one thread was waiting after a 429
        self.slow = False
        self.successes = 0
        self.domain_search_done = False
        self.domain_search_lock = threading.Lock()
        self.g = Gathered(domain)
        self.log: list = []
        self.fetched: set[str] = set()
        self.router = _get_router()

    # ---- accounting
    def elapsed(self) -> float:
        """Seconds since the start, not counting time spent waiting to repeat a call after a 429."""
        return self._raw_elapsed() - self._waited_now()

    def _raw_elapsed(self) -> float:
        return time.monotonic() - self.start

    def _waited_now(self) -> float:
        extra = (time.monotonic() - self.wait_mark) if self.waiters else 0.0
        return self.waited + extra

    def _wait_begin(self) -> None:
        with self.lock:
            if self.waiters == 0:
                self.wait_mark = time.monotonic()
            self.waiters += 1

    def _wait_end(self) -> None:
        with self.lock:
            self.waiters -= 1
            if self.waiters == 0:
                self.waited += time.monotonic() - self.wait_mark

    def _stopped(self) -> bool:
        try:
            if self.should_abort():
                return True
        except Exception:
            pass
        return self._raw_elapsed() - self.waited > STOP_NEW_CALLS_AFTER

    def _reserve(self, cost: int) -> bool:
        with self.lock:
            if self.spent + self.reserved + cost > MAX_UNITS:
                return False
            if self.budget is not None:
                try:
                    ok = bool(self.budget.reserve(cost))
                except Exception:  # noqa: BLE001
                    ok = False
                if not ok:
                    self.budget_refused = True
                    return False
            self.reserved += cost
            self.attempted += 1
            return True

    def _settle(self, reserved: int, charged: int) -> None:
        with self.lock:
            self.reserved -= reserved
            self.spent += charged
            if self.budget is not None:
                try:
                    self.budget.settle(reserved, charged)
                except Exception:  # noqa: BLE001
                    pass

    def _note_latency(self, began: float) -> None:
        if time.monotonic() - began > 1.0:
            self.slow = True

    def _pause(self) -> bool:
        with self.lock:
            if self.backoff_used + RETRY_PAUSE > MAX_BACKOFF_TOTAL:
                return False
            if not self.slow and self.elapsed() > FAST_RETRY_UNTIL:
                return False  # waiting does not count, but working time against fast providers is bounded
            self.backoff_used += RETRY_PAUSE
        self._wait_begin()
        try:
            time.sleep(RETRY_PAUSE)
        finally:
            self._wait_end()
        return True

    def call(self, kind: str, detail: str, cost: int, fn: Callable[[], Any], retry_unanswered: bool = True):
        """One provider call with pessimistic reservation, exact spend, bounded retries. Returns result or None."""
        refusals = 0
        unanswered = 0
        while True:
            if self._stopped() or not self._reserve(cost):
                return None
            began = time.monotonic()
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001 - a provider failure never escapes the build
                self._note_latency(began)
                if _is_refusal(exc):
                    self._settle(cost, 0)
                    self.log.append((kind, detail + " [refused]", 0))
                    if refusals < MAX_REFUSAL_RETRIES and self._pause():
                        refusals += 1
                        continue
                    return None
                answered_empty = type(exc).__name__ == "ProviderError" and getattr(exc, "original", None) is None
                self._settle(cost, cost)  # timed out, connection failed, or answered with nothing: costs its units
                self.log.append((kind, detail + (" [no page]" if answered_empty else " [unanswered]"), cost))
                if not answered_empty and retry_unanswered and unanswered < 1:
                    unanswered += 1
                    continue
                return None
            self._note_latency(began)
            self._settle(cost, cost)
            self.log.append((kind, detail, cost))
            with self.lock:
                self.successes += 1
            return result

    # ---- provider operations
    def _names_company(self, item) -> bool:
        blob = f"{item.url} {item.title} {item.description}".lower()
        return self.domain in blob or self.name in blob or self.name.replace(" ", "-") in blob

    def search(self, query: str, depth: str, only_relevant: bool = False) -> list | None:
        cost = SEARCH_COST["nimble"][depth]
        r = self.call("search", f"{depth}:{query}", cost,
                      lambda: self.router.search(query, provider="nimble", search_depth=depth, max_results=10,
                                                 timeout=CALL_TIMEOUT, data_apis=False))
        if r is None:
            return None
        results = []
        for item in r.results:
            url = item.url
            if not url:
                continue
            if only_relevant and not self._names_company(item):
                continue
            results.append(url)  # a search only names pages; their text is read from a rendered extract
        return results

    def domain_search(self) -> list | None:
        with self.domain_search_lock:
            if self.domain_search_done:
                return None
            res = self.search(self.domain, self.opt.search_depth, only_relevant=True)
            if res is not None:
                self.domain_search_done = True
            return res

    def extract(self, url: str) -> bool:
        with self.lock:
            if url in self.fetched:
                return False
            self.fetched.add(url)
        opts = {"render": True} if self.opt.render else None
        r = self.call("extract", url, RENDER_COST if self.opt.render else EXTRACT_COST["nimble"],
                      lambda: self.router.extract([url], provider="nimble", timeout=CALL_TIMEOUT,
                                                  **({"provider_options": opts} if opts else {})))
        if r is None:
            return False
        for doc in r.documents:
            self.g.add_text(url, doc.content, "nimble")
        return True

    def research(self) -> None:
        schema = {"type": "object", "properties": {
            "legal_name": {"type": ["string", "null"]}, "hq_city": {"type": ["string", "null"]},
            "ceo": {"type": ["string", "null"]}, "founded_year": {"type": ["integer", "null"]},
            "headcount_range": {"type": ["string", "null"]}, "funding_total": {"type": ["integer", "null"]}}}
        query = (f"Research the company with the web domain {self.domain}: its legal_name, hq_city, ceo, "
                 f"founded_year, headcount_range and funding_total.")
        job = self.call("research", "create", RESEARCH_COST,
                        lambda: self.router.submit_research(query, provider="nimble", output_schema=schema),
                        retry_unanswered=False)
        if job is None:
            return
        # the run has started: its 25 units are spent whatever happens next
        response = None
        refusals = 0
        while response is None:
            try:
                response = job.result(timeout=RESEARCH_TIMEOUT)
            except Exception as exc:  # noqa: BLE001
                # polling a run may itself be answered 429 (costs nothing): wait and ask again
                if _is_refusal(exc) and refusals < 2 * MAX_REFUSAL_RETRIES and not self._stopped() and self._pause():
                    refusals += 1
                    continue
                return
        structured = response.structured if isinstance(response.structured, dict) else {}
        cited_urls = []
        for c in response.citations or []:
            f = (c.field or "").replace("$.", "", 1)
            if f not in FIELDS:
                continue
            # the cited page joins the evidence whether or not the citation supports the claim; the claim itself
            # is only ever a candidate through the page's rendered text (an excerpt must appear there)
            if c.url:
                cited_urls.append(c.url)
        self.research_urls = cited_urls

    # ---- orchestration
    def run(self) -> BuildResult:
        self.research_urls: list[str] = []
        pool = ThreadPoolExecutor(max_workers=6)
        try:
            futs = []
            if self.opt.research:
                futs.append(pool.submit(self.research))
            search_f = pool.submit(self.domain_search)
            urls = search_f.result() or []
            if self.opt.extract_results:
                self._extract_all(pool, urls)
            for f in futs:
                f.result()
            # pages cited by research that no search returned: fetch them so excerpts are checked against text
            if self.opt.extract_results and self.research_urls:
                self._extract_all(pool, list(self.research_urls), limit=10)
            if not self.domain_search_done and not self._stopped():
                urls = self.domain_search() or []
                if self.opt.extract_results:
                    self._extract_all(pool, urls)
            self._fetch_originals(pool)
            if self.opt.followups and self.successes > 0:
                self._followups(pool)
                self._fetch_originals(pool)
        except Exception:  # noqa: BLE001
            pass
        finally:
            pool.shutdown(wait=True)
        spent = self.spent
        aborted = self.should_abort()
        if aborted or (self.successes == 0 and not self.budget_refused):
            return BuildResult("failed", None, spent, self.log, [], self.successes == 0 and self.attempted > 0)
        return BuildResult("ready", self.g.decide(self.now_iso), spent, self.log, self.g.page_list())

    def _fetch_originals(self, pool) -> None:
        """Obtain from a provider every original that origin rule 2 needs (at most three Canonical hops)."""
        while not self._stopped():
            need = [u for u in self.g.missing_originals() if u not in self.fetched]
            if not need:
                return
            list(pool.map(self.extract, need[:10]))

    def _extract_all(self, pool, urls: list[str], limit: int = 10) -> int:
        new = [u for u in dict.fromkeys(urls) if u not in self.g.full and u not in self.fetched][:limit]
        list(pool.map(self.extract, new))
        return len(new)

    _KEYWORDS = {
        "legal_name": "registered name legal entity",
        "hq_city": "headquartered based in headquarters",
        "ceo": "chief executive CEO",
        "founded_year": "founded established",
        "headcount_range": "employees staff headcount",
        "funding_total": "raised funding investment",
    }

    def _followups(self, pool) -> None:
        done = 0
        asked: set[str] = set()
        for f in list(self.g.unknown_fields()):
            if done >= self.opt.max_followups or self._stopped():
                return
            if f not in self.g.unknown_fields():
                continue
            query = f"{self.display} {self._KEYWORDS[f]}"
            if query in asked or query.strip().lower() == self.domain:
                continue
            asked.add(query)
            done += 1
            urls = self.search(query, self.opt.followup_depth, only_relevant=True)
            if urls and self.opt.extract_results:
                self._extract_all(pool, urls, limit=5)


def run_build(domain: str, now_iso: str | None = None, should_abort: Callable[[], bool] | None = None,
              budget=None, options: Options | None = None) -> BuildResult:
    b = None
    try:
        b = _Build(domain, should_abort or (lambda: False), options or Options(), now_iso, budget)
        return b.run()
    except Exception:  # noqa: BLE001 - never raises
        spent = b.spent if b is not None else 0
        return BuildResult("failed", None, spent, b.log if b is not None else [])
