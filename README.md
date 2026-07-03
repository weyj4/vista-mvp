# Quick Quotes — v0 walking skeleton

Thin end-to-end LangGraph pipeline for the BoxTech "Quick Quotes" agent, deployed to Google Cloud Run. Every node is a stub — no LLM calls, no CoreERP, no retrieval, no auth. The goal is a deployable spine to hang real nodes on next. See `spec-v0.md` for the full design.

Stack: Python 3.12 · `langgraph` · `pydantic` v2 · `FastAPI` · `uvicorn` · `uv` for package management.

## Local

```bash
uv sync
uv run python -m app.main
```

Smoke tests:

```bash
curl -s localhost:8080/healthz
# → {"ok":true}

curl -s -X POST localhost:8080/quote \
  -H 'content-type: application/json' \
  -d '{"request_id":"req_1","from":"buyer@acme.com","body":"Need a quote for 5000 RSC boxes, 12x10x8, 32 ECT."}'
# → 200; status="delivered", spec populated, quote.total=4200
```

## Container

```bash
docker build -t quick-quotes .
docker run --rm -p 8080:8080 -e PORT=8080 quick-quotes
```

## Deploy to Cloud Run

Source deploy uses the `Dockerfile` in this repo (Cloud Build handles the image):

```bash
gcloud run deploy quick-quotes \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080
```

Then hit the printed service URL:

```bash
curl -s https://<SERVICE_URL>/healthz
curl -s -X POST https://<SERVICE_URL>/quote \
  -H 'content-type: application/json' \
  -d '{"request_id":"req_1","from":"buyer@acme.com","body":"5000 RSC 12x10x8 32ECT"}'
```

`--allow-unauthenticated` is fine for a demo. Lock it down before anything real.

## Layout

```
app/
├── state.py     # Pydantic models: QuoteState, QuoteSpec, ExtractedField[T], ...
├── nodes.py     # six stub nodes: ingest → extract → enrich → validate → cost → deliver
├── graph.py     # StateGraph wiring; exports compiled graph as `app`
├── server.py    # FastAPI: GET /healthz, POST /quote
└── main.py      # uvicorn entrypoint (reads $PORT, binds 0.0.0.0)
```
