# Quick Quotes — Walking Skeleton Spec (v0, Python)

## Purpose

Build the **thinnest possible end-to-end LangGraph pipeline** for the BoxTech "Quick Quotes" agent, deploy it to **Google Cloud Run**, and prove the whole path works: an HTTP request carrying a quote-request payload goes in, runs through a LangGraph `StateGraph`, and a structured JSON response comes out with `200 OK`.

**This is a skeleton, not the product.** Every node is a stub. No LLM calls, no CoreERP, no retrieval, no auth, no human-in-the-loop. The goal is a deployable spine we can hang real nodes on next. Optimize for *works, deployed, and easy to read* over *complete*.

**Stack:** Python 3.12 + `langgraph` + `pydantic` v2 + `FastAPI` + `uvicorn`, containerized, on Cloud Run.

---

## Explicitly OUT of scope for v0

Do **not** build any of these. They come later.

- Real LLM / Gemini calls (the `extract` node returns hardcoded stub data)
- CoreERP API integration (the `cost` node returns a fake price)
- Retrieval / vector search / win-rate scoring (the `enrich` node is a pass-through)
- Human-in-the-loop interrupts / checkpointing (v0 runs straight through, no pauses)
- Email ingestion / webhooks / queues (input arrives directly as JSON on an HTTP POST)
- Attachment parsing (PDF/image/audio) — input is a JSON body only
- Persistence / database / Cloud SQL
- Authentication / authorization
- Multi-tenancy / customer resolution beyond echoing an ID
- Tests beyond one smoke test (see Acceptance Criteria)
- Retries, error taxonomy, observability beyond basic `logging`

If you're unsure whether something is in scope: it's not. Keep it minimal.

---

## Architecture (v0)

```
POST /quote  ──▶  FastAPI handler  ──▶  graph.invoke(state)  ──▶  200 JSON
                                             │
                                             ▼
             START ▶ ingest ▶ extract ▶ enrich ▶ validate ▶ cost ▶ deliver ▶ END
```

All six nodes are synchronous stubs that return a partial `QuoteState` update. No branching, no interrupts in v0 — a straight line. (The real graph has conditional edges and two human gates; we add those later. Keep the node names and order identical to the target design so we can evolve in place.)

---

## Project structure

```
quick_quotes/
├── app/
│   ├── __init__.py
│   ├── state.py          # Pydantic models: ExtractedField, QuoteSpec, QuoteState, QuoteRequestInput
│   ├── nodes.py          # the six stub node functions
│   ├── graph.py          # builds & compiles the StateGraph
│   ├── server.py         # FastAPI app: POST /quote + GET /healthz
│   └── main.py           # entrypoint: uvicorn on $PORT
├── pyproject.toml        # (or requirements.txt — see Dependencies)
├── Dockerfile
└── .dockerignore
```

---

## Data model (`app/state.py`)

Define the shared graph state with Pydantic v2. Keep field-level confidence/provenance in the shape now (even though stubs fill it with constants) so the real `extract` node drops in without reshaping state.

`ExtractedField` is generic over the field's value type — use `typing.Generic[T]` + `TypeVar` so confidence + provenance travel with every field.

```python
from __future__ import annotations
from enum import Enum
from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, Field

T = TypeVar("T")


class FieldStatus(str, Enum):
    extracted = "extracted"
    inferred = "inferred"
    missing = "missing"
    ambiguous = "ambiguous"


class ExtractedField(BaseModel, Generic[T]):
    """A single extracted field carrying its value plus provenance metadata."""
    value: Optional[T] = None
    confidence: float = 1.0                 # 0..1 (stub: 1.0)
    source: Optional[str] = None            # provenance pointer (stub: "stub")
    status: FieldStatus = FieldStatus.extracted


class Dimensions(BaseModel):
    length: float
    width: float
    depth: float


class QuoteSpec(BaseModel):
    dimensions: ExtractedField[Dimensions]
    box_style: ExtractedField[str]          # e.g. "RSC"
    board_grade: ExtractedField[str]        # e.g. "32 ECT"
    print_spec: ExtractedField[str]
    quantity: ExtractedField[int]
    logistics: ExtractedField[str]


class QuoteRequestInput(BaseModel):
    request_id: str
    from_: str = Field(alias="from")        # 'from' is a Python keyword
    body: str

    model_config = {"populate_by_name": True}


class ValidationResult(BaseModel):
    status: str = "clean"                   # clean | needs_review | blocked
    flagged_fields: list[str] = Field(default_factory=list)


class Enrichment(BaseModel):
    retrieved: list[Any] = Field(default_factory=list)
    win_score: Optional[float] = None


class Quote(BaseModel):
    currency: str = "USD"
    total: float = 0.0
    line_items: list[Any] = Field(default_factory=list)


class QuoteState(BaseModel):
    # intake
    request_id: str
    customer_id: Optional[str] = None
    raw_request: Optional[QuoteRequestInput] = None
    # extraction
    spec: Optional[QuoteSpec] = None
    # enrichment
    enrichment: Optional[Enrichment] = None
    # validation
    validation: Optional[ValidationResult] = None
    # system of record
    quote: Optional[Quote] = None
    # cross-cutting
    status: str = "running"                 # running | delivered | failed
    errors: list[str] = Field(default_factory=list)
```

> Implementer notes:
> - LangGraph's Python `StateGraph` accepts a Pydantic `BaseModel` as the state schema directly — pass `QuoteState` to `StateGraph(QuoteState)`. Nodes return a `dict` (or partial `QuoteState`) of channels to update; LangGraph merges them.
> - Default reducers are last-write-wins, which is correct for every channel here **except** `errors`. Make `errors` an append channel: annotate it with `Annotated[list[str], operator.add]` in the state schema (LangGraph will concat instead of overwrite). If mixing Pydantic + `Annotated` reducers is awkward, it's acceptable in v0 to leave `errors` last-write-wins and note the TODO — no node writes errors in the skeleton anyway.

---

## The six stub nodes (`app/nodes.py`)

Each node is a function `def <name>(state: QuoteState) -> dict` returning the channels it updates. All values are hardcoded stubs. Log one line per node (via the `logging` module, `INFO`) so Cloud Run logs show the path executing.

1. **`ingest`** — derive `customer_id = "cust_" + <deterministic hash of raw_request.from_>` (e.g. first 8 hex of `hashlib.sha1`), set `status="running"`. Log `[ingest] request_id=...`.

2. **`extract`** — return a hardcoded `QuoteSpec` with all fields `status="extracted"`, `confidence=1.0`, `source="stub"`. Plausible RSC values: dimensions 12×10×8, board_grade "32 ECT", box_style "RSC", quantity 5000, print_spec "1 color", logistics "FOB origin". Log `[extract] stub spec produced`.

3. **`enrich`** — pass-through: set `enrichment = Enrichment(retrieved=[], win_score=0.5)`. Log `[enrich] stub win_score=0.5`.

4. **`validate`** — set `validation = ValidationResult(status="clean", flagged_fields=[])`. Log `[validate] clean`.

5. **`cost`** — return a fake price: `quote = Quote(currency="USD", total=4200.00, line_items=[])`. Log `[cost] stub total=4200`.

6. **`deliver`** — set `status="delivered"`. Log `[deliver] done`.

Keep nodes as plain functions (sync is fine for v0). No classes.

---

## The graph (`app/graph.py`)

- `graph = StateGraph(QuoteState)`
- Add the six nodes with `graph.add_node("ingest", ingest)` etc.
- Wire a straight chain with `add_edge`: `START → ingest → extract → enrich → validate → cost → deliver → END` (import `START`, `END` from `langgraph.graph`).
- `app = graph.compile()` — **no checkpointer in v0**, no conditional edges.
- Export the compiled `app`.

---

## HTTP server (`app/server.py`, `app/main.py`)

Use **FastAPI** + **uvicorn**.

- `GET /healthz` → `200` `{"ok": true}`. (Cloud Run health check + quick smoke.)
- `POST /quote`:
  - Request body validated as `QuoteRequestInput` (FastAPI does this via the Pydantic model → automatic `422` on bad input; that's fine, no need for manual `400`).
  - Build the initial `QuoteState(request_id=body.request_id, raw_request=body, status="running")`.
  - `result = app.invoke(initial_state)` — note `invoke` returns the state (as a dict or model depending on version; coerce to `QuoteState` or dump to dict for the response).
  - Return `200` with the full final state as JSON (use `.model_dump(by_alias=True)` so `from` round-trips).
  - Wrap in try/except → `500 {"error": <message>}` on failure.
- `main.py`: `uvicorn.run("app.server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))`. **Must bind `0.0.0.0` and read `PORT` — Cloud Run requires this.**

---

## Containerization

**`Dockerfile`** — small, production-lean:

- Base: `python:3.12-slim`.
- Set `PYTHONUNBUFFERED=1` (so logs flush to Cloud Run).
- Copy dependency manifest, `pip install --no-cache-dir` (use a venv or `--user` if you prefer; not required).
- Copy `app/`.
- `CMD ["python", "-m", "app.main"]` (or `uvicorn app.server:app --host 0.0.0.0 --port ${PORT}` via shell form — but prefer the `main.py` entrypoint so `$PORT` is read in Python).
- Do **not** hardcode the port — read `os.environ["PORT"]`.

**`.dockerignore`**: `__pycache__`, `*.pyc`, `.git`, `*.md`, `.venv`, `venv`.

---

## Dependencies

Prefer a `requirements.txt` for simplicity (Cloud Run source deploy picks it up automatically):

```
langgraph
langchain-core
pydantic>=2
fastapi
uvicorn[standard]
```

(If you'd rather use `pyproject.toml` with the same deps, that's fine — but `requirements.txt` is the least-friction path for `gcloud run deploy --source`.)

Pin versions only if the build breaks on latest; otherwise leave unpinned for v0.

---

## Acceptance criteria (definition of done)

1. `pip install -r requirements.txt` succeeds.
2. `python -m app.main` locally, then `curl localhost:8080/healthz` → `200 {"ok":true}`.
3. This request:
   ```bash
   curl -s -X POST localhost:8080/quote \
     -H 'content-type: application/json' \
     -d '{"request_id":"req_1","from":"buyer@acme.com","body":"Need a quote for 5000 RSC boxes, 12x10x8, 32 ECT."}'
   ```
   returns `200` and JSON where `status == "delivered"`, `spec` is populated, and `quote.total == 4200`.
4. Cloud Run logs show all six `[node]` log lines in order for that request.
5. `docker build` succeeds and the container runs locally the same way (`docker run -p 8080:8080 -e PORT=8080 <image>`).

---

## Deploy to Cloud Run (for me to run, include in README)

Provide a short `README.md` with these commands (source-based deploy — Cloud Build handles the image):

```bash
gcloud run deploy quick-quotes \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080
```

Then smoke-test the deployed URL:

```bash
curl -s https://<SERVICE_URL>/healthz
curl -s -X POST https://<SERVICE_URL>/quote -H 'content-type: application/json' \
  -d '{"request_id":"req_1","from":"buyer@acme.com","body":"5000 RSC 12x10x8 32ECT"}'
```

(`--allow-unauthenticated` is fine for a demo; note in the README it should be locked down for anything real.)

---

## Evolution notes (context for the implementer — do NOT build now)

So the skeleton grows cleanly into the real system, keep these seams intact:

- Node names + order are the **final** ones. Real logic replaces stub bodies in place.
- `extract` becomes a **Gemini structured-output call** — bind `QuoteSpec` as the response schema (Gemini + Pydantic structured output is clean in Python via the `google-genai` SDK or `langchain-google-vertexai`'s `.with_structured_output(QuoteSpec)`). The `ExtractedField` shape already matches.
- `validate` gains a **conditional edge**: `clean → cost` vs. `needs_review → spec_review` (a human-gate interrupt node inserted before `cost`), via `add_conditional_edges`.
- A second **interrupt** (`approval`) gets inserted before `deliver`, conditional on a price threshold. Use LangGraph's `interrupt()` primitive.
- Compiling with a **checkpointer** (`langgraph.checkpoint.postgres` via Cloud SQL) enables those interrupts to suspend/resume.
- `cost` becomes a real (mock-then-real) CoreERP REST call — but stays **deterministic**: no LLM in this node, ever.
- Production upgrade path: this same compiled graph can be wrapped by **Vertex AI Agent Engine** (`LanggraphAgent`), which is Python-first — a reason this MVP is in Python. Managed checkpointing, tracing, and HITL interrupts come with it.
```
