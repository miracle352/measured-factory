# Dossier service — run

Build and start (from this folder):

```sh
docker build -t dossier-service . && docker run --rm -p 8080:8080 -e PORT=8080 \
  -e NIMBLE_API_KEY=... -e NIMBLE_BASE_URL=... \
  -e TAVILY_API_KEY=... -e TAVILY_BASE_URL=... dossier-service
```

`PORT` defaults to 8080. Tavily variables are optional; Nimble alone suffices.
Health check: `GET /health`. All provider traffic goes through the `webrouter` Python package
(installed at image build with `pip install "webrouter[search,extract,research]>=0.12.0"`).
State is persisted to `$DOSSIER_STATE_DIR/state.json` (default `/var/lib/dossier`, on the container's own
filesystem, so it survives a container stop/start but not removal of the container). It is rewritten atomically after
every mutation (temp file, fsync, rename), so an abrupt kill leaves either the old or the new state; a missing file
means an empty service. The clock, accounts, tokens, dossiers, builds, history, change feed and idempotent responses are
all kept. Do not run with `--rm` if state must outlive the container.

## Browser screens

`/`, `/signup`, `/login`, `/contested`, `/dossiers/{domain}` (with `Accept: text/html`; otherwise JSON) and
`/dossiers/{domain}/evidence` are served as self-contained HTML (inline CSS/JS, no external assets) and read the
JSON API with the bearer token kept in `localStorage`. The dossier screen polls every second while `building`
(latest read wins), keeps one Idempotency-Key per pending research/refresh so a lost response can be retried
(`research-uncertain` / `refresh-uncertain`). Export/import keeps tokens, so signed-in browsers stay signed in.
