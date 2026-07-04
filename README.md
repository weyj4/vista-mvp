# Quick Quotes

LangGraph "Quick Quotes" agent deployed to Google Cloud Run. `extract` is a real Gemini structured-output call (see `spec-v1.md`); the remaining nodes (`ingest`, `enrich`, `validate`, `cost`, `deliver`) are stubs from the v0 skeleton (`spec-v0.md`) — a deployable spine to hang the rest on.

Stack: Python 3.12 · `langgraph` · `pydantic` v2 · `FastAPI` · `uvicorn` · `langchain-google-genai` (Gemini) · `uv` for package management.

## Local

```bash
uv sync
uv run python -m app.main
```

The server boots on `:8080`. Without `GOOGLE_API_KEY` set, `extract` degrades gracefully (see below) — you'll still get a `200`, but `spec` fields come back as `missing` and one entry lands in `errors`.

To enable LangSmith tracing locally, copy `.env.example` to `.env`, fill in your `LANGSMITH_API_KEY` (and `GOOGLE_API_KEY` while you're there), and start with:

```bash
uv run --env-file .env python -m app.main
```

The startup log confirms with `langsmith tracing enabled project=...`.

Smoke tests:

```bash
curl -s localhost:8080/healthz
# → {"ok":true}

curl -s -X POST localhost:8080/quote \
  -H 'content-type: application/json' \
  -d @fixtures/clean_email.json | python -m json.tool
# → 200; status="delivered", spec populated from Gemini, quote.total=4200
```

## Extraction (Gemini)

`app/extraction.py` defines a flat `ExtractionResult` schema; `app/llm.py` binds it to a `ChatGoogleGenerativeAI` (`gemini-2.5-flash` by default, temperature 0). A pure `to_quote_spec` mapper turns the flat result into the typed `QuoteSpec[ExtractedField[T]]`.

Config (all env-driven, with sane defaults):

- `GOOGLE_API_KEY` — required for real extraction. If unset, `extract` returns an all-`missing` spec and appends `"extract: GOOGLE_API_KEY not set"` to `errors`; the pipeline still returns 200.
- `GEMINI_MODEL` — defaults to `gemini-2.5-flash`.
- `GEMINI_TEMPERATURE` — defaults to `0.0`.

Try the fixtures:

```bash
# clean — expect mostly `extracted` with evidence phrases
curl -s -X POST localhost:8080/quote -H 'content-type: application/json' \
  -d @fixtures/clean_email.json | python -m json.tool

# messy — expect board_grade `missing`, quantity `ambiguous`, print `ambiguous`
curl -s -X POST localhost:8080/quote -H 'content-type: application/json' \
  -d @fixtures/messy_email.json | python -m json.tool

# prior_ref — expect most fields `missing` with evidence pointing at the PO reference
curl -s -X POST localhost:8080/quote -H 'content-type: application/json' \
  -d @fixtures/prior_ref_email.json | python -m json.tool
```

**Production upgrade to Vertex AI**: no code change — set `GOOGLE_GENAI_USE_VERTEXAI=true` plus `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` and use Application Default Credentials instead of `GOOGLE_API_KEY`. `langchain-google-genai` picks the backend automatically.

## Tests

```bash
uv run pytest
```

Unit tests cover the `to_quote_spec` mapper (well-formed extraction, per-field parse-degradation, separator variants for dimensions, comma/unit stripping for quantity). Extraction against real Gemini is not unit-tested — the fixtures above are the manual acceptance smoke.

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

To enable LangSmith tracing on Cloud Run, first put the API key in Secret Manager:

```bash
gcloud secrets create langsmith-api-key --replication-policy=automatic
printf 'lsv2_pt_...' | gcloud secrets versions add langsmith-api-key --data-file=-
gcloud secrets add-iam-policy-binding langsmith-api-key \
  --member="serviceAccount:$(gcloud run services describe quick-quotes --region us-central1 --format='value(spec.template.spec.serviceAccountName)')" \
  --role=roles/secretmanager.secretAccessor
```

Then redeploy with the tracing flags:

```bash
gcloud run deploy quick-quotes \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars=LANGSMITH_TRACING=true,LANGSMITH_PROJECT=quick-quotes-v0 \
  --set-secrets=LANGSMITH_API_KEY=langsmith-api-key:latest
```

> Note: state (all node inputs/outputs) is shipped to LangSmith. Fine for stub v0; revisit before real customer data flows through — either scrub sensitive fields or move to self-hosted LangSmith.

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
├── state.py       # Pydantic models: QuoteState, QuoteSpec, ExtractedField[T], ...
├── nodes.py       # six nodes: ingest → extract (Gemini) → enrich → validate → cost → deliver
├── graph.py       # StateGraph wiring; exports compiled graph as `app`
├── server.py      # FastAPI: GET /healthz, POST /quote
├── main.py        # uvicorn entrypoint (reads $PORT, binds 0.0.0.0)
├── config.py      # GEMINI_MODEL / GEMINI_TEMPERATURE / GOOGLE_API_KEY_ENV
├── llm.py         # lazy lru_cached get_extractor() bound to ExtractionResult
└── extraction.py  # flat FieldExtraction/ExtractionResult schema + to_quote_spec mapper + prompt
fixtures/          # clean / messy / prior_ref demo emails
tests/             # pytest unit tests for the mapper
```
