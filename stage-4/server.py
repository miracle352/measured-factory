"""HTTP layer for the dossier service."""
import json
import os
import re
import datetime
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlsplit

import ui
from store import ApiError, Store, invalid, malformed, normalise_domain, parse_ts

STORE = Store()
MAX_BODY = 256 * 1024 * 1024


def _no_const(_):
    raise ValueError("bad constant")


def parse_json(raw):
    try:
        text = raw.decode("utf-8")
        return json.loads(text, parse_constant=_no_const)
    except Exception:
        raise malformed("body is not valid JSON")


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


_DIGITS = re.compile(r"[0-9]+")


def int_param(qs, name, default, lo, hi=None):
    if name not in qs:
        return default
    v = qs[name]
    if not _DIGITS.fullmatch(v):
        raise invalid("%s must be an integer" % name)
    n = int(v) if len(v) < 1000 else 10 ** 1000
    if n < lo or (hi is not None and n > hi):
        raise invalid("%s out of range" % name)
    return n


_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _ts_param(qs, name):
    """RFC 3339 timestamp query parameter; an unescaped '+' offset arrives as a space."""
    if name not in qs:
        return None
    v = qs[name]
    v = re.sub(r" ([0-9]{2}:[0-9]{2})$", lambda m: "+" + m.group(1), v)
    parse_ts(v)
    return v


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 120

    def log_message(self, *a):
        pass

    # ------------------------------------------------------------ plumbing
    def _send(self, status, obj=None):
        body = b"" if obj is None else dumps(obj)
        try:
            self.send_response(status)
            if obj is not None:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionError, socket.timeout):
            self.close_connection = True

    def _send_html(self, text):
        body = text.encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionError, socket.timeout):
            self.close_connection = True

    def _wants_html(self):
        q_html, q_json = 0.0, 0.0
        for part in (self.headers.get("Accept") or "").split(","):
            bits = [b.strip() for b in part.split(";")]
            mt = bits[0].lower()
            q = 1.0
            for b in bits[1:]:
                if b.lower().startswith("q="):
                    try:
                        q = float(b[2:])
                    except ValueError:
                        q = 0.0
            if mt == "text/html":
                q_html = max(q_html, q)
            elif mt == "application/json":
                q_json = max(q_json, q)
        return q_html > 0 and q_html >= q_json

    def _browser_page(self, method, path):
        """HTML for browser routes, or None when the request is an API request."""
        if method != "GET":
            return None
        if path == "/":
            return ui.list_page()
        if path == "/signup":
            return ui.signup_page()
        if path == "/login":
            return ui.login_page()
        if path == "/contested":
            return ui.contested_page()
        segs = path.split("/")
        if len(segs) in (3, 4) and segs[1] == "dossiers" and segs[2] != "":
            if len(segs) == 4 and segs[3] != "evidence":
                return None
            raw = unquote(segs[2])
            try:
                dom = normalise_domain(raw)
            except ApiError:
                dom = raw.strip().lower()
            if len(segs) == 4:
                return ui.evidence_page(dom)
            if self._wants_html():
                return ui.dossier_page(dom)
        return None

    def _read_body(self):
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in te:
            chunks, total = [], 0
            while True:
                line = self.rfile.readline(65537)
                try:
                    size = int(line.split(b";")[0].strip() or b"0", 16)
                except ValueError:
                    raise malformed("bad chunk")
                if size == 0:
                    while True:
                        l = self.rfile.readline(65537)
                        if l in (b"\r\n", b"\n", b""):
                            break
                    break
                total += size
                if total > MAX_BODY:
                    raise malformed("body too large")
                chunks.append(self.rfile.read(size))
                self.rfile.readline(65537)
            return b"".join(chunks)
        cl = self.headers.get("Content-Length")
        if not cl:
            return b""
        try:
            n = int(cl)
        except ValueError:
            raise malformed("bad content-length")
        if n < 0 or n > MAX_BODY:
            raise malformed("bad content-length")
        return self.rfile.read(n) if n else b""

    def _dispatch(self, method):
        try:
            try:
                raw = self._read_body()
            except ApiError:
                self.close_connection = True
                raise
            parts = urlsplit(self.path)
            path = parts.path
            qs = {}
            for k, v in parse_qsl(parts.query, keep_blank_values=True):
                qs.setdefault(k, v)
            page = self._browser_page(method, path)
            if page is not None:
                self._send_html(page)
                return
            status, obj = self._route(method, path, qs, raw)
            self._send(status, obj)
        except ApiError as e:
            self._send(e.status, {"error": {"code": e.code, "message": e.message}})
        except Exception as e:  # last resort; should not happen
            print("internal error:", repr(e), file=sys.stderr)
            self._send(500, {"error": {"code": "internal_error", "message": "internal error"}})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_PATCH(self):
        self._dispatch("PATCH")

    # ------------------------------------------------------------ routing
    def _idem_key(self):
        key = self.headers.get("Idempotency-Key")
        if key is None or key == "":
            raise ApiError(400, "missing_idempotency_key", "Idempotency-Key required")
        if len(key) > 255:
            raise invalid("Idempotency-Key too long")
        return key

    def _route(self, method, path, qs, raw):
        S = STORE
        notfound = ApiError(404, "not_found", "no such route")
        if path == "/health":
            if method != "GET":
                raise notfound
            return 200, {"status": "ok"}
        if path.startswith("/_test/"):
            op = path[len("/_test/"):]
            if op == "reset" and method == "POST":
                S.reset(parse_json(raw))
                return 204, None
            if op == "clock" and method == "POST":
                S.set_clock(parse_json(raw))
                return 204, None
            if op == "export" and method == "GET":
                return 200, S.export()
            if op == "import" and method == "POST":
                S.import_state(parse_json(raw))
                return 204, None
            raise notfound
        if path == "/auth/signup" and method == "POST":
            return 201, S.signup(parse_json(raw))
        if path == "/auth/login" and method == "POST":
            return 200, S.login(parse_json(raw))

        if path == "/changes" and method == "GET":
            S.authenticate(self.headers.get("Authorization"))
            since = int_param(qs, "since", 0, 0)
            limit = int_param(qs, "limit", 50, 1, 200)
            return 200, S.changes(since, limit)

        segs = path.split("/")  # ['', 'dossiers', ...]
        if len(segs) < 2 or segs[0] != "" or segs[1] != "dossiers":
            raise notfound
        n = len(segs)
        if n == 2 and method in ("GET", "POST"):
            uid = S.authenticate(self.headers.get("Authorization"))
            if method == "GET":
                q = qs.get("q", "")
                limit = int_param(qs, "limit", 50, 1, 200)
                offset = int_param(qs, "offset", 0, 0)
                return 200, S.list_dossiers(q, limit, offset)
            key = self._idem_key()
            body = parse_json(raw)
            if not isinstance(body, dict):
                raise malformed("body must be an object")
            return S.post_dossier(uid, key, path, body)
        if n == 3 and method == "GET":
            S.authenticate(self.headers.get("Authorization"))
            as_of = _ts_param(qs, "as_of")
            return 200, S.get_dossier(unquote(segs[2]), as_of)
        if n == 4 and segs[3] == "history" and method == "GET":
            S.authenticate(self.headers.get("Authorization"))
            return 200, S.history(unquote(segs[2]))
        if n == 4 and segs[3] == "values" and method == "GET":
            S.authenticate(self.headers.get("Authorization"))
            ta = qs.get("true_at")
            if ta is None or not _DATE.fullmatch(ta):
                raise invalid("true_at must be YYYY-MM-DD")
            try:
                datetime.date(int(ta[:4]), int(ta[5:7]), int(ta[8:]))
            except ValueError:
                raise invalid("true_at must be a valid date")
            as_of = _ts_param(qs, "as_of")
            return 200, S.values(unquote(segs[2]), ta, as_of)
        if n == 4 and segs[3] == "refresh" and method == "POST":
            uid = S.authenticate(self.headers.get("Authorization"))
            key = self._idem_key()
            return S.refresh(uid, key, path, unquote(segs[2]))
        raise notfound


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 512
    allow_reuse_address = True


def main():
    port = int(os.environ.get("PORT") or 8080)
    srv = Server(("0.0.0.0", port), Handler)
    srv.serve_forever()


if __name__ == "__main__":
    main()
