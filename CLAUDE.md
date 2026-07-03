# Quick Quotes (Vista MVP) — Claude guide

v0 **walking skeleton** for the BoxTech "Quick Quotes" LangGraph agent, deployed on Google Cloud Run. Every node is a stub — the point is a deployable spine, not the product. Full design is in `spec-v0.md`; consult it before changing shape.

## Stack

Python 3.12 · `langgraph` · `pydantic` v2 · `FastAPI` · `uvicorn` · **`uv`** for all package management (never `pip`).

## Layout

```
app/
├── state.py    Pydantic models: QuoteState, QuoteSpec, ExtractedField[T], ...
├── nodes.py    six stub node fns: ingest, extract, enrich, validate, cost, deliver
├── graph.py    StateGraph wiring; exports compiled graph as `app`
├── server.py   FastAPI: GET /healthz, POST /quote
└── main.py     uvicorn entrypoint; reads $PORT, binds 0.0.0.0
```

## Common commands

```bash
uv sync                          # install / refresh deps
uv run python -m app.main        # run server locally on :8080
uv add <pkg>                     # add a dep (updates pyproject + uv.lock)
docker build -t quick-quotes .   # container build
gcloud run deploy quick-quotes --source . --region us-central1 --allow-unauthenticated --port 8080
```

## Explicitly OUT of scope for v0

Do **not** add these without an explicit ask — the spec lists them as later work:

- Real LLM / Gemini calls (`extract` stays a stub)
- CoreERP integration (`cost` stays a hardcoded price)
- Retrieval / vector search / win-rate scoring
- Human-in-the-loop interrupts / checkpointing
- Email / webhooks / queues / attachment parsing
- Persistence, auth, multi-tenancy
- Tests beyond the acceptance-criteria smoke tests
- Retries, error taxonomy, richer observability

If unsure whether something belongs in v0: it doesn't.

## Gotchas

- **`app` name collision.** `app/graph.py` exports the compiled graph as `app` (spec-mandated). `app/server.py` imports it as `graph_app` to avoid clashing with the FastAPI instance also named `app`. Keep that alias.
- **`from` field alias.** `QuoteRequestInput.from_` is `from` on the wire. Always dump with `.model_dump(by_alias=True)` when returning it, and use `model_validate` on incoming dicts.
- **LangGraph `invoke` returns a `dict`, not the state model.** `server.py` coerces via `QuoteState.model_validate(result)` before serializing.
- **`errors` reducer TODO.** Currently last-write-wins because no node writes it. Before any node appends errors, switch to `Annotated[list[str], operator.add]` per the spec note.
- **Node names + order are final.** Real logic replaces stub bodies **in place** — don't rename or reorder.
- **Cloud Run requirements.** `main.py` binds `0.0.0.0` and reads `$PORT`; do not hardcode a port.

## When touching this repo

- Prefer editing existing files over adding new ones.
- Keep nodes as plain sync functions returning `dict` — no classes, no async in v0.
- Don't add fallback/backwards-compat shims; this is a fresh skeleton.
- The Docker build has not been verified on this machine (no Docker daemon). If you make Dockerfile changes, actually build it or `gcloud run deploy --source .` to test.
