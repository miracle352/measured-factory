"""Dossier build: gather evidence through WebRouter, decide the six fields, track spend.

    run_build(domain, now_iso, should_abort) -> BuildResult

Blocking; run it in a worker thread.  Never raises.  A build makes exactly one non-error search whose
query is the normalised domain, researches through nimble asking for all six fields, extracts the pages the
search returned, validates every research claim and every cited excerpt with support.py against text that
was actually served, and never lets its spend exceed MAX_UNITS (80).
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

import support
from support import FIELDS

MAX_UNITS = 80

# Cost table (§9)
SEARCH_COST = {"nimble": {"lite": 1, "fast": 5, "deep": 15}, "tavily": {"lite": 8, "fast": 16, "deep": 16}}
EXTRACT_COST = {"nimble": 1, "tavily": 2}
RESEARCH_COST = 25

# Timing.  Real providers are far slower than a local stand-in (a Nimble search can take 10+ s, a research run
# about a minute), so waits are generous; nothing here is tuned to a mock.
CALL_TIMEOUT = 45.0           # one search / extract request
RESEARCH_TIMEOUT = 170.0      # wait for a research run after it was accepted
RESEARCH_CREATE_TIMEOUT = 45.0
STOP_NEW_CALLS_AFTER = 190.0  # seconds since the build started; calls in flight still finish by ~240 s
RETRY_PAUSE = 1.1             # a provider may refuse the same call again for a second after a 429
MAX_REFUSAL_RETRIES = 3       # 429, 429, 429 then a normal answer
FAST_RETRY_UNTIL = 7.5        # while every provider answers within a second, retries stop this long after the start
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


@dataclass
class BuildResult:
    outcome: str                                 # 'ready' | 'failed'
    fields: dict | None                          # None when the build failed (keep the previous fields)
    spent_units: int
    log: list = dc_field(default_factory=list)   # (kind, detail, cost) per provider call, for measurement


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
            _router = WebRouter("nimble", provider_config=config, router=None)
        return _router


# --------------------------------------------------------------------------- evidence

_TRUST = {"own": 4, "filing": 3, "news": 2, "aggregator": 1}


@dataclass
class Evidence:
    field: str
    value: Any
    url: str
    excerpt: str
    provider: str
    trust: int
    date: str


def _host(url: str) -> str:
    rest = url.split("://", 1)[-1]
    return rest.split("/", 1)[0].split(":", 1)[0].lower()


def _header_info(header: list[str]) -> dict[str, str]:
    info = {}
    for line in header:
        name, _, value = line.partition(":")
        info[name.strip().lower()] = value.strip()
    return info


def _trust(domain: str, url: str, kind: str | None) -> int:
    host = _host(url)
    if host == domain or host.endswith("." + domain) or host == "www." + domain:
        return 4
    return _TRUST.get((kind or "").lower(), 2)


class Gathered:
    """Texts the providers served, per page, and the evidence derived from them."""

    def __init__(self, domain: str):
        self.domain = domain
        self.lock = threading.Lock()
        self.full: dict[str, str] = {}            # url -> full served text (extract / deep search)
        self.partial: dict[str, str] = {}         # url -> truncated served text (snippet / truncated body)
        self.evidence: list[Evidence] = []
        self._seen: set[tuple] = set()
        self.meta: dict[str, tuple[str | None, str]] = {}   # url -> (kind, date)

    def add_text(self, url: str, text: str, provider: str, truncated: bool) -> None:
        if not url or not text:
            return
        with self.lock:
            if truncated:
                if url in self.full or len(text) <= len(self.partial.get(url, "")):
                    return
                self.partial[url] = text
            else:
                self.full[url] = text
            header, prose = support.split_header(text)
        info = _header_info(header)
        kind = info.get("kind")
        date = info.get("effective") or info.get("published") or ""
        with self.lock:
            self.meta[url] = (kind, date)
        sents = support.sentences(prose)
        if truncated and sents and prose.rstrip()[-1:] not in ".!?\"”’)":
            sents = sents[:-1]  # the last sentence was cut off by the provider
        for sent in sents:
            self._scan_sentence(url, sent, provider, kind, date)

    def _scan_sentence(self, url: str, sent: str, provider: str, kind: str | None, date: str) -> None:
        sent = support.collapse_ws(sent)
        if not sent or len(sent) > 500:
            return
        for f in FIELDS:
            vals = support.extract_values(f, sent, self.domain)
            if len(vals) == 1:
                self._add(Evidence(f, vals[0], url, sent, provider, _trust(self.domain, url, kind), date))

    def _add(self, ev: Evidence) -> None:
        key = (ev.field, ev.url, ev.excerpt, ev.provider)
        with self.lock:
            if key in self._seen:
                return
            self._seen.add(key)
            self.evidence.append(ev)

    def add_claim(self, f: str, claimed: Any, url: str, excerpts: list[str], provider: str) -> bool:
        """A research claim counts only when its citation supports it, against served text."""
        ok = False
        for ex in excerpts:
            ex = support.collapse_ws(ex or "")
            if not ex or len(ex) > 500:
                continue
            vals = support.extract_values(f, ex, self.domain)
            if len(vals) != 1 or not _claim_matches(f, claimed, vals[0]):
                continue
            known = self.full.get(url)
            if known is not None:
                _, prose = support.split_header(known)
                if not support.in_prose(ex, prose):
                    continue
            with self.lock:
                kind, date = self.meta.get(url, (None, ""))
            self._add(Evidence(f, vals[0], url, ex, provider, _trust(self.domain, url, kind), date))
            ok = True
        return ok

    def revalidate(self) -> None:
        """Drop evidence whose excerpt turns out not to be in the prose of the full text we now hold."""
        with self.lock:
            keep = []
            for ev in self.evidence:
                known = self.full.get(ev.url)
                if known is not None:
                    _, prose = support.split_header(known)
                    if not support.in_prose(ev.excerpt, prose):
                        continue
                keep.append(ev)
            self.evidence = keep

    def decide(self) -> dict:
        self.revalidate()
        out = {}
        for f in FIELDS:
            groups: dict[Any, list[Evidence]] = {}
            with self.lock:
                for ev in self.evidence:
                    if ev.field == f:
                        groups.setdefault(ev.value, []).append(ev)
            if not groups:
                out[f] = {"value": None, "status": "unknown", "citations": []}
                continue

            def score(item):
                _, evs = item
                return (max(e.trust for e in evs), max(e.date for e in evs), len({e.url for e in evs}))

            value, evs = max(groups.items(), key=score)
            evs = sorted(evs, key=lambda e: (-e.trust, e.date, e.url), reverse=False)
            cites, seen = [], set()
            for e in evs:
                if (e.url, e.excerpt) in seen:
                    continue
                seen.add((e.url, e.excerpt))
                cites.append({"url": e.url, "excerpt": e.excerpt, "provider": e.provider})
                if len(cites) >= 3:
                    break
            out[f] = {"value": value, "status": "known", "citations": cites}
        return out

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
    def __init__(self, domain: str, should_abort: Callable[[], bool], options: Options):
        self.domain = domain
        self.name = support.company_name(domain)
        self.display = " ".join(w.capitalize() for w in self.name.split())
        self.should_abort = should_abort or (lambda: False)
        self.opt = options
        self.start = time.monotonic()
        self.lock = threading.Lock()
        self.spent = 0
        self.reserved = 0
        self.backoff_used = 0.0
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
        return time.monotonic() - self.start

    def _stopped(self) -> bool:
        try:
            if self.should_abort():
                return True
        except Exception:
            pass
        return self.elapsed() > STOP_NEW_CALLS_AFTER

    def _reserve(self, cost: int) -> bool:
        with self.lock:
            if self.spent + self.reserved + cost > MAX_UNITS:
                return False
            self.reserved += cost
            return True

    def _settle(self, reserved: int, charged: int) -> None:
        with self.lock:
            self.reserved -= reserved
            self.spent += charged

    def _note_latency(self, began: float) -> None:
        if time.monotonic() - began > 1.0:
            self.slow = True

    def _pause(self) -> bool:
        with self.lock:
            if self.slow:
                if self.backoff_used + RETRY_PAUSE > MAX_BACKOFF_TOTAL:
                    return False
            elif self.elapsed() + RETRY_PAUSE > FAST_RETRY_UNTIL:
                return False
            self.backoff_used += RETRY_PAUSE
        time.sleep(RETRY_PAUSE)
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
            results.append(url)
            if depth == "deep":
                self.g.add_text(url, item.content or item.description, "nimble", truncated=False)
            else:
                text = item.content or item.description
                self.g.add_text(url, text, "nimble", truncated=True)
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
        r = self.call("extract", url, EXTRACT_COST["nimble"],
                      lambda: self.router.extract([url], provider="nimble", timeout=CALL_TIMEOUT))
        if r is None:
            return False
        for doc in r.documents:
            self.g.add_text(url, doc.content, "nimble", truncated=False)
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
        try:
            response = job.result(timeout=RESEARCH_TIMEOUT)
        except Exception:  # noqa: BLE001
            return
        structured = response.structured if isinstance(response.structured, dict) else {}
        cited_urls = []
        for c in response.citations or []:
            f = (c.field or "").replace("$.", "", 1)
            if f not in FIELDS:
                continue
            claimed = structured.get(f)
            if claimed is None:
                continue
            excerpts = [c.snippet or ""] + list((getattr(c, "extra", None) or {}).get("excerpts") or [])
            self.g.add_claim(f, claimed, c.url, excerpts, "nimble")
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
                self._extract_all(pool, [u for u in self.research_urls if u not in self.g.full], limit=4)
            if not self.domain_search_done and not self._stopped():
                urls = self.domain_search() or []
                if self.opt.extract_results:
                    self._extract_all(pool, urls)
            if self.opt.followups and self.successes > 0:
                self._followups(pool)
        except Exception:  # noqa: BLE001
            pass
        finally:
            pool.shutdown(wait=True)
        spent = self.spent
        if self.successes == 0 or self.should_abort():
            return BuildResult("failed", None, spent, self.log)
        return BuildResult("ready", self.g.decide(), spent, self.log)

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
            urls = self.search(query, self.opt.followup_depth)
            if urls and self.opt.extract_results:
                self._extract_all(pool, urls, limit=5)


def run_build(domain: str, now_iso: str | None = None, should_abort: Callable[[], bool] | None = None,
              options: Options | None = None) -> BuildResult:
    b = None
    try:
        b = _Build(domain, should_abort or (lambda: False), options or Options())
        return b.run()
    except Exception:  # noqa: BLE001 - never raises
        spent = b.spent if b is not None else 0
        return BuildResult("failed", None, spent, b.log if b is not None else [])
