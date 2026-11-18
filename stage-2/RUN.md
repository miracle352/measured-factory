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
State is in memory only.

## Browser screens

`/`, `/signup`, `/login`, `/contested`, `/dossiers/{domain}` (with `Accept: text/html`; otherwise JSON) and
`/dossiers/{domain}/evidence` are served as self-contained HTML (inline CSS/JS, no external assets) and read the
JSON API with the bearer token kept in `localStorage`. The dossier screen polls every second while `building`
(latest read wins), keeps one Idempotency-Key per pending research/refresh so a lost response can be retried
(`research-uncertain` / `refresh-uncertain`). Export/import keeps tokens, so signed-in browsers stay signed in.
