"""Appendix A engine: when does an excerpt support a value for a field of a company.

Public API
    split_header(text)                      -> (header_lines, prose)
    sentences(prose)                        -> list[str]
    is_single_sentence(excerpt)             -> bool
    extract_values(field, excerpt, domain)  -> list of normalised values
    supports(field, value, excerpt, domain) -> bool
    company_name(domain)                    -> str
    collapse_ws(text)                       -> str
    in_prose(excerpt, prose)                -> bool

Everything here is pure and dependency free.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

FIELDS = ("legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total")
EXEC_TITLES = ("cfo", "coo", "cto")

# --------------------------------------------------------------------------- tables

STATEMENT_PHRASES = {
    "legal_name": ["legal name", "registered name", "registered as", "registered company", "legal entity",
                   "name of record"],
    "hq_city": ["headquartered in", "headquarters in", "head office in", "based in", "registered office in",
                "registered seat in"],
    "ceo": ["chief executive officer", "chief executive", "CEO"],
    "founded_year": ["founded", "founding", "established", "incorporated"],
    "headcount_range": ["employs", "employees", "staff", "people", "headcount", "workforce"],
    "funding_total": ["raised", "funding", "invested", "investment"],
    "cfo": ["chief financial officer", "CFO"],
    "coo": ["chief operating officer", "COO"],
    "cto": ["chief technology officer", "CTO"],
}

NEGATING_PHRASES = ["in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to", "aims to",
                    "seeking", "could", "would", "might", "reportedly", "rumoured", "former", "formerly",
                    "will become", "not"]

LEGAL_SUFFIXES = ["Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC", "GmbH", "AG",
                  "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.", "S.A.", "S.A.S.", "S.L.",
                  "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K."]
_DOTTED_SUFFIXES = [s for s in LEGAL_SUFFIXES if s.endswith(".")]

HEADCOUNT_RANGES = [(1, 10, "1-10"), (11, 50, "11-50"), (51, 200, "51-200"), (201, 500, "201-500"),
                    (501, 1000, "501-1000"), (1001, 5000, "1001-5000"), (5001, 10000, "5001-10000"),
                    (10001, None, "10001+")]

# --------------------------------------------------------------------------- basics

_WS_RE = re.compile(r"\s+")
_LINE_BREAK_RE = re.compile(r"\r\n|\n|\r")
_NOT_ALNUM_BEFORE = r"(?<![^\W_])"
_NOT_ALNUM_AFTER = r"(?![^\W_])"
_WORD_TOKEN_RE = re.compile(r"(?:[^\W_]|[̀-ͯ])+")


def collapse_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _is_alnum(ch: str) -> bool:
    return ch.isalpha() or ch.isdigit() or unicodedata.category(ch).startswith("M")


def company_name(domain: str) -> str:
    return domain.split(".")[0].replace("-", " ")


def _phrase_pattern(phrase: str) -> str:
    return _NOT_ALNUM_BEFORE + re.escape(phrase).replace("\\ ", " ") + _NOT_ALNUM_AFTER


def _alt_regex(phrases: list[str]) -> re.Pattern:
    ordered = sorted(phrases, key=len, reverse=True)
    return re.compile("|".join(_phrase_pattern(p) for p in ordered), re.IGNORECASE)


_PHRASE_RE = {f: _alt_regex(p) for f, p in STATEMENT_PHRASES.items()}
_NEGATING_RE = _alt_regex(NEGATING_PHRASES)


def _name_regex(domain: str) -> re.Pattern:
    return re.compile(_phrase_pattern(company_name(domain)), re.IGNORECASE)


def _domain_regex(domain: str) -> re.Pattern:
    return re.compile(_phrase_pattern(domain), re.IGNORECASE)


# --------------------------------------------------------------------------- A.1 / header

_HEADER_RE = re.compile(r"^[A-Z][a-z]+(?:-[A-Z][a-z]+)*:.*$")


def _is_header_line(line: str) -> bool:
    return bool(_HEADER_RE.match(line.rstrip("\r")))


def split_header(text: str) -> tuple[list[str], str]:
    """Header lines (if the first line is one) up to the first empty line; the rest is prose."""
    lines = _LINE_BREAK_RE.split(text)
    if not lines or not _is_header_line(lines[0]):
        return [], text
    header: list[str] = []
    i = 0
    while i < len(lines) and lines[i].strip() != "":
        header.append(lines[i])
        i += 1
    prose_lines = lines[i + 1:] if i < len(lines) else []
    return header, "\n".join(prose_lines)


def _ends_dotted_suffix(text: str, dot_index: int) -> bool:
    upto = text[:dot_index + 1]
    for suffix in _DOTTED_SUFFIXES:
        if upto.endswith(suffix):
            before = len(upto) - len(suffix) - 1
            if before < 0 or not _is_alnum(upto[before]):
                return True
    return False


_CLOSERS = '"”’)'


def _split_line(line: str) -> list[str]:
    out: list[str] = []
    start = 0
    n = len(line)
    i = 0
    while i < n:
        ch = line[i]
        if ch in ".!?":
            j = i + 1
            while j < n and line[j] in _CLOSERS:
                j += 1
            if j < n and line[j].isspace() and not (ch == "." and _ends_dotted_suffix(line, i)):
                out.append(line[start:j])
                start = j
                i = j
                continue
        i += 1
    out.append(line[start:])
    return [s.strip() for s in out if s.strip()]


def sentences(prose: str) -> list[str]:
    result: list[str] = []
    for line in _LINE_BREAK_RE.split(prose):
        result.extend(_split_line(line))
    return result


def is_single_sentence(excerpt: str) -> bool:
    return len(sentences(collapse_ws(excerpt))) == 1


def in_prose(excerpt: str, prose: str) -> bool:
    """Excerpt is copied from the prose (whitespace runs may be collapsed)."""
    e = collapse_ws(excerpt)
    return bool(e) and e in collapse_ws(prose)


# --------------------------------------------------------------------------- word helpers

def _tokens(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _WORD_TOKEN_RE.finditer(text)]


def _is_cap_word(tok: str) -> bool:
    if len(tok) < 2 or not tok[0].isupper():
        return False
    return all(c.islower() or unicodedata.category(c).startswith("M") for c in tok[1:])


def _is_upper_word(tok: str) -> bool:
    return len(tok) >= 2 and all(c.isupper() for c in tok)


# --------------------------------------------------------------------------- numbers / amounts

_NUM_RUN_RE = re.compile(r"[0-9][0-9,.]*[0-9]|[0-9]")
_NUM_VALID_RE = re.compile(r"^(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?$")
_PREFIX_RE = re.compile(_NOT_ALNUM_BEFORE + r"(?:US\$|USD|\$) ?$", re.IGNORECASE)
_SCALES = {"k": 10**3, "thousand": 10**3, "m": 10**6, "mn": 10**6, "million": 10**6, "bn": 10**9,
           "billion": 10**9}
_SUFFIX_DIRECT_RE = re.compile(r"(mn|bn|k|m)" + _NOT_ALNUM_AFTER, re.IGNORECASE)
_SUFFIX_WORD_RE = re.compile(r" (thousand|million|billion)" + _NOT_ALNUM_AFTER, re.IGNORECASE)
_DOLLARS_RE = re.compile(r"(?: (thousand|million|billion))? (?:US )?dollars" + _NOT_ALNUM_AFTER, re.IGNORECASE)


class _Num:
    __slots__ = ("start", "end", "text", "valid", "letter_adjacent")

    def __init__(self, text: str, m: re.Match):
        self.start, self.end = m.start(), m.end()
        self.text = m.group()
        self.valid = bool(_NUM_VALID_RE.match(self.text))
        before = text[self.start - 1] if self.start > 0 else ""
        after = text[self.end] if self.end < len(text) else ""
        self.letter_adjacent = (bool(before) and before.isalpha()) or (bool(after) and after.isalpha())

    @property
    def decimal(self) -> Decimal:
        return Decimal(self.text.replace(",", ""))

    @property
    def is_int(self) -> bool:
        return "." not in self.text


def _numbers(text: str) -> list[_Num]:
    return [_Num(text, m) for m in _NUM_RUN_RE.finditer(text)]


def _amounts(text: str, nums: list[_Num]) -> list[tuple[int, int, int | None]]:
    """Amount occurrences as (start, end, value-or-None). None: not a whole number of dollars."""
    found: list[tuple[int, int, int | None]] = []
    for n in nums:
        if not n.valid:
            continue
        # form 1: currency marker, optional space, number, optional scale
        pm = _PREFIX_RE.search(text[:n.start])
        if pm:
            scale = 1
            end = None
            m = _SUFFIX_DIRECT_RE.match(text, n.end)
            if m:
                scale, end = _SCALES[m.group(1).lower()], m.end()
            else:
                m = _SUFFIX_WORD_RE.match(text, n.end)
                if m:
                    scale, end = _SCALES[m.group(1).lower()], m.end()
                elif not (n.end < len(text) and _is_alnum(text[n.end])):
                    end = n.end
            if end is not None:
                found.append((pm.start(), end, _whole(n.decimal * scale)))
                continue
        # form 2: number [scale word] dollars
        before = text[n.start - 1] if n.start > 0 else ""
        if not (before and _is_alnum(before)):
            m = _DOLLARS_RE.match(text, n.end)
            if m:
                scale = _SCALES[m.group(1).lower()] if m.group(1) else 1
                found.append((n.start, m.end(), _whole(n.decimal * scale)))
    return found


def _whole(d: Decimal) -> int | None:
    try:
        if d != d.to_integral_value():
            return None
        return int(d)
    except (InvalidOperation, ValueError):
        return None


def _in_spans(n: _Num, spans: list[tuple[int, int, int | None]]) -> bool:
    return any(s <= n.start and n.end <= e for s, e, _ in spans)


def headcount_range(n: int) -> str | None:
    if n < 1:
        return None
    for lo, hi, label in HEADCOUNT_RANGES:
        if n >= lo and (hi is None or n <= hi):
            return label
    return None


# --------------------------------------------------------------------------- field extractors

def _x_funding(text: str, domain: str) -> list:
    amounts = _amounts(text, _numbers(text))
    if any(v is None for _, _, v in amounts):
        return []  # an amount that is not a whole number of dollars is not a value
    return [v for _, _, v in amounts]


def _plain_numbers(text: str) -> list[_Num]:
    nums = _numbers(text)
    spans = _amounts(text, nums)
    return [n for n in nums if n.valid and not n.letter_adjacent and not _in_spans(n, spans)]


def _x_founded(text: str, domain: str) -> list:
    out = []
    for n in _plain_numbers(text):
        if len(n.text) == 4 and n.text.isdigit() and 1800 <= int(n.text) <= 2099:
            out.append(int(n.text))
    return out


def _x_headcount(text: str, domain: str) -> list:
    out = []
    for n in _plain_numbers(text):
        if not n.is_int:
            continue
        r = headcount_range(int(n.decimal))
        if r:
            out.append(r)
    return out


def _x_hq_city(text: str, domain: str) -> list:
    toks = _tokens(text)
    by_start = {t[0]: i for i, t in enumerate(toks)}
    out = []
    for m in _PHRASE_RE["hq_city"].finditer(text):
        e = m.end()
        if e >= len(text) or text[e] != " ":
            continue
        i = by_start.get(e + 1)
        if i is None or not _is_cap_word(toks[i][2]):
            continue
        # not part of a longer run: the word before (the phrase's last word) must not be a capitalised word
        # joined by a space or '-'
        j = i - 1
        if j >= 0 and toks[j][1] <= e and text[toks[j][1]:toks[i][0]] in (" ", "-") and _is_cap_word(toks[j][2]):
            continue
        k = i
        while (k + 1 < len(toks) and text[toks[k][1]:toks[k + 1][0]] in (" ", "-")
               and _is_cap_word(toks[k + 1][2])):
            k += 1
        out.append(text[toks[i][0]:toks[k][1]])
    return out


def _x_person(text: str, domain: str, field: str = "ceo") -> list:
    spans = [(m.start(), m.end()) for m in _name_regex(domain).finditer(text)]
    spans += [(m.start(), m.end()) for m in _PHRASE_RE[field].finditer(text)]
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    cleaned = []
    pos = 0
    for s, e in merged:
        cleaned.append(text[pos:s])
        cleaned.append("\x00")
        pos = e
    cleaned.append(text[pos:])
    t = "".join(cleaned)
    toks = _tokens(t)
    out = []
    i = 0
    while i < len(toks):
        if not _is_cap_word(toks[i][2]):
            i += 1
            continue
        k = i
        while k + 1 < len(toks) and t[toks[k][1]:toks[k + 1][0]] == " " and _is_cap_word(toks[k + 1][2]):
            k += 1
        if 2 <= k - i + 1 <= 3:
            out.append(t[toks[i][0]:toks[k][1]])
        i = k + 1
    return out


def _suffix_at(text: str, p: int) -> int | None:
    best = None
    for sfx in LEGAL_SUFFIXES:
        if text.startswith(sfx, p):
            e = p + len(sfx)
            if e < len(text) and _is_alnum(text[e]):
                continue
            if best is None or e < best:
                best = e
    return best


def _x_legal_name(text: str, domain: str) -> list:
    toks = _tokens(text)
    by_start = {t[0]: i for i, t in enumerate(toks)}
    out = []
    starts = [m for m in _name_regex(domain).finditer(text)] + [m for m in _domain_regex(domain).finditer(text)]
    for m in starts:
        pos = m.end()
        while True:
            for sep in (", ", " "):
                if text.startswith(sep, pos):
                    e = _suffix_at(text, pos + len(sep))
                    if e is not None:
                        out.append(text[m.start():e])
                        pos = None
                        break
            if pos is None:
                break
            if text.startswith(" ", pos) and (pos + 1) in by_start:
                tok = toks[by_start[pos + 1]]
                if _is_cap_word(tok[2]) or _is_upper_word(tok[2]):
                    pos = tok[1]
                    continue
            break
    return out


_EXTRACTORS = {
    "legal_name": _x_legal_name,
    "hq_city": _x_hq_city,
    "ceo": lambda t, d: _x_person(t, d, "ceo"),
    "founded_year": _x_founded,
    "headcount_range": _x_headcount,
    "funding_total": _x_funding,
    "cfo": lambda t, d: _x_person(t, d, "cfo"),
    "coo": lambda t, d: _x_person(t, d, "coo"),
    "cto": lambda t, d: _x_person(t, d, "cto"),
}


# --------------------------------------------------------------------------- A.2

def extract_values(field: str, excerpt: str, domain: str) -> list:
    """Distinct normalised values the excerpt states for the field; [] when it supports nothing."""
    if field not in _EXTRACTORS:
        return []
    text = collapse_ws(excerpt)
    if not text or len(sentences(text)) != 1:
        return []
    if not (_name_regex(domain).search(text) or _domain_regex(domain).search(text)):
        return []
    if not _PHRASE_RE[field].search(text):
        return []
    if _NEGATING_RE.search(text):
        return []
    values: list = []
    for v in _EXTRACTORS[field](text, domain):
        if v not in values:
            values.append(v)
    return values


def supports(field: str, value, excerpt: str, domain: str) -> bool:
    if value is None or isinstance(value, bool):
        return False
    values = extract_values(field, excerpt, domain)
    return bool(values) and all(v == value for v in values)
