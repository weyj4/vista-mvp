# Quick Quotes (Vista MVP) — Claude guide

LangGraph "Quick Quotes" agent deployed on Google Cloud Run. `extract` is a real Gemini structured-output call (v1); every other node is still a stub. See `spec-v0.md` for the skeleton design and `spec-v1.md` for the extract node — consult before changing shape.

## Stack

Python 3.12 · `langgraph` · `pydantic` v2 · `FastAPI` · `uvicorn` · `langchain-google-genai` (Gemini) · **`uv`** for all package management (never `pip`).

## Layout

```
app/
├── state.py       Pydantic models: QuoteState, QuoteSpec, ExtractedField[T], ...
├── nodes.py       six node fns: ingest, extract (real), enrich, validate, cost, deliver
├── graph.py       StateGraph wiring; exports compiled graph as `app`
├── server.py      FastAPI: GET /healthz, POST /quote
├── main.py        uvicorn entrypoint; reads $PORT, binds 0.0.0.0
├── config.py      GEMINI_MODEL / GEMINI_TEMPERATURE / GOOGLE_API_KEY_ENV
├── llm.py         lazy lru_cached get_extractor() bound to ExtractionResult
└── extraction.py  flat FieldExtraction/ExtractionResult schema + to_quote_spec mapper + prompt
fixtures/          clean / messy / prior_ref demo emails (QuoteRequestInput JSON)
tests/             pytest unit tests for the mapper
```

## Common commands

```bash
uv sync                          # install / refresh deps (incl. dev)
uv run python -m app.main        # run server locally on :8080
uv run pytest                    # run unit tests
uv add <pkg>                     # add a dep (updates pyproject + uv.lock)
docker build -t quick-quotes .   # container build
gcloud run deploy quick-quotes --source . --region us-central1 --allow-unauthenticated --port 8080
```

## Explicitly OUT of scope

Do **not** add these without an explicit ask — the specs list them as later work:

- CoreERP integration (`cost` stays a hardcoded price)
- Retrieval / vector search / win-rate scoring (`enrich` is a pass-through)
- Human-in-the-loop interrupts / checkpointing
- Email / webhooks / queues / attachment parsing (fixtures are text-body only)
- Persistence, auth, multi-tenancy
- Retries, error taxonomy, richer observability

If unsure whether something belongs now: it doesn't.

## Extraction (Gemini) — invariants

- **Use `langchain-google-genai`, never `ChatVertexAI`.** The latter is deprecated for Gemini as of `langchain-google-genai` 4.0. `spec-v0.md`'s evolution note is out of date on this — trust `spec-v1.md`.
- **Flat schema + mapper, not nested generics.** The model emits `ExtractionResult` (six flat `FieldExtraction`s: `value`/`status`/`confidence`/`evidence`). `to_quote_spec()` maps that into the typed `QuoteSpec[ExtractedField[T]]`. Don't ask Gemini to fill the nested `Generic[T]` wrappers directly.
- **Typed-parse degradation is per-field, not per-call.** `_parse_dimensions`/`_parse_quantity` are wrapped in try/except inside the mapper; a bad value degrades **that field** to `status=ambiguous` with `value=None`, leaving the other five intact.
- **`extract` must never crash the pipeline.** Any failure (missing key, API error, refusal, validation error) is caught, returns `_all_missing_spec()`, and appends one `errors: ["extract: <exc>"]` entry. Server always returns 200 for a well-formed request.
- **Lazy LLM import.** `ChatGoogleGenerativeAI` is imported inside `get_extractor()`, and `get_extractor()` itself is `lru_cache`-d. Do not top-level import from `langchain_google_genai` — it makes module import expensive and breaks test-without-key scenarios.
- **Temperature 0.0.** Extraction is deterministic-ish by contract. Don't add randomness.
- **Auth today = `GOOGLE_API_KEY` env var.** Prod upgrade path is Vertex AI backend via ADC + `GOOGLE_GENAI_USE_VERTEXAI=true` — no code change needed, just env.

## Observability

LangSmith tracing is env-var-driven — no code registers callbacks. Set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` and LangGraph auto-instruments. `server.py` tags each `invoke` with `run_name=quote:<request_id>` + metadata so traces are searchable by request id. `main.py` logs `langsmith tracing enabled project=...` at boot when the flag is on. Local: `uv run --env-file .env python -m app.main`. Cloud Run: `--set-env-vars` + `--set-secrets` (see README). Do **not** add `langsmith` as a direct dep — it's already transitive via `langchain-core`.

## Gotchas

- **`app` name collision.** `app/graph.py` exports the compiled graph as `app` (spec-mandated). `app/server.py` imports it as `graph_app` to avoid clashing with the FastAPI instance also named `app`. Keep that alias.
- **`from` field alias.** `QuoteRequestInput.from_` is `from` on the wire. Always dump with `.model_dump(by_alias=True)` when returning it, and use `model_validate` on incoming dicts.
- **LangGraph `invoke` returns a `dict`, not the state model.** `server.py` coerces via `QuoteState.model_validate(result)` before serializing.
- **`errors` is an append reducer** (`Annotated[list[str], operator.add]`). Nodes returning `{"errors": [msg]}` concat rather than overwrite. Verified working with the Pydantic state schema.
- **Node names + order are final.** Real logic replaces stub bodies **in place** — don't rename or reorder.
- **Cloud Run requirements.** `main.py` binds `0.0.0.0` and reads `$PORT`; do not hardcode a port.

## When touching this repo

- Prefer editing existing files over adding new ones.
- Keep nodes as plain sync functions returning `dict` — no classes, no async in v0.
- Don't add fallback/backwards-compat shims; this is a fresh skeleton.
- The Docker build has not been verified on this machine (no Docker daemon). If you make Dockerfile changes, actually build it or `gcloud run deploy --source .` to test.
