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
