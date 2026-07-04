# Quick Quotes — Layer 2 Spec: the real `extract` node

## Purpose

Replace the stub `extract` node with a real LLM call that turns a raw quote-request email
into a populated `QuoteSpec` — with per-field **value**, **status**, **confidence**, and
**evidence/provenance** — using **Gemini structured output**. This is the node the whole
demo hinges on: everything downstream (validation, the review UI, costing) consumes what
this produces.

Keep everything else (state model, graph wiring, server, other stub nodes) unchanged. Only
`extract` becomes real, plus supporting files (`llm.py`, prompt, fixtures, config).

---

## IMPORTANT: use the current Google SDK, not the deprecated one

Use **`langchain-google-genai`** with **`ChatGoogleGenerativeAI`**.

Do **NOT** use `ChatVertexAI` from `langchain-google-vertexai` — as of `langchain-google-genai`
4.0.0, `ChatVertexAI` is **deprecated** for Gemini models. The consolidated `google-genai`
SDK behind `langchain-google-genai` targets either the Gemini Developer API (API key) or
Vertex AI (GCP project) via config, selected automatically. We want that one.

- Package: `langchain-google-genai>=4.0.0`
- Class: `from langchain_google_genai import ChatGoogleGenerativeAI`
- Structured output: `llm.with_structured_output(ExtractionResult)` (Pydantic model)
- Model: `gemini-2.5-flash` (fast + cheap + strong structured output; good default for extraction).
  Make the model name a config constant so it's swappable.

### Auth / backend (keep it simple for the MVP)
- For local dev + the demo, use the **Gemini Developer API with an API key**:
  read `GOOGLE_API_KEY` from env. This avoids GCP ADC friction for a demo.
- Document in the README that in production on Cloud Run you'd switch to the **Vertex AI
  backend** via Application Default Credentials + `GOOGLE_GENAI_USE_VERTEXAI=true` and a
  project/region — no code change beyond env. Note this but don't build it now.
- Never hardcode the key. If `GOOGLE_API_KEY` is unset, the node must fail gracefully
  (see Failure Handling) — not crash the server at import time.

---

## Design decisions (build to these — they're also the talking points)

1. **The LLM fills a FLAT schema; our code maps it into `QuoteSpec`.**
   Do not ask Gemini to emit the nested `ExtractedField[T]` wrappers directly. Give it a
   flat `ExtractionResult` (values + per-field status + confidence + evidence). Then a pure
   function `to_quote_spec(result)` maps that into the typed `QuoteSpec` with its
   `ExtractedField` wrappers. Rationale: simpler schema = lower model error rate; keeps our
   typed state model as the code-side contract; lets us control provenance mapping.

2. **`status` is the reliable signal; `confidence` is a soft display aid.**
   The model classifies each field as `extracted | inferred | missing | ambiguous` — this is
   what downstream routing/UI keys on. It also returns a 0..1 `confidence`, but we treat that
   as a coarse hint, NOT a calibrated probability (LLM self-confidence is poorly calibrated).
   The prompt must instruct: use `missing` when the field isn't present, `ambiguous` when
   there are multiple plausible readings, `inferred` when you're filling from context/normal
   conventions rather than an explicit statement, `extracted` when it's stated outright.

3. **Provenance = evidence snippet, not character offsets.**
   For each field the model returns a short `evidence` string: the exact phrase from the email
   it used (empty for `missing`). We store that in `ExtractedField.source`. Cheap, demo-able,
   no offset machinery.

4. **Graceful degradation on failure.**
   Any failure (missing API key, API error, malformed/refused output, validation error) must
   NOT crash the pipeline. On failure, return a `QuoteSpec` with all six fields
   `value=None, status=missing, confidence=0.0, source=None`, and append a message to
   `errors`. The pipeline then flows to human review with everything flagged — which is the
   correct real-world behavior (degrade to manual, don't drop the request).

---

## New / changed files

```
app/
├── llm.py            # NEW: builds the ChatGoogleGenerativeAI client (lazy, cached)
├── extraction.py     # NEW: ExtractionResult flat schema + to_quote_spec() mapper + prompt
├── nodes.py          # CHANGED: extract() now calls the LLM; other nodes untouched
└── config.py         # NEW (small): model name, temperature, env var names
fixtures/
├── clean_email.json      # NEW: a well-specified request (all fields present)
├── messy_email.json      # NEW: incomplete/ambiguous (missing board grade, vague qty)
└── prior_ref_email.json  # NEW: references a prior order ("same as PO#... but 500 more")
```

---

## `app/config.py` (small)

```python
from __future__ import annotations
import os

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TEMPERATURE = float(os.environ.get("GEMINI_TEMPERATURE", "0.0"))  # deterministic extraction
GOOGLE_API_KEY_ENV = "GOOGLE_API_KEY"
```

Temperature 0.0: extraction should be as deterministic as possible.

---

## `app/extraction.py`

### The flat schema the LLM fills

Each field gets value + status + confidence + evidence. Values are all optional (a field may
be missing). Keep names aligned with `QuoteSpec` for a clean mapping.

```python
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from app.state import FieldStatus

class FieldExtraction(BaseModel):
    """One extracted field: the value plus the model's self-assessment."""
    value: Optional[str] = Field(
        default=None,
        description="The extracted value as a string, or null if not present. "
                    "For dimensions use 'LxWxD' (e.g. '12x10x8'). For quantity, digits only.",
    )
    status: FieldStatus = Field(
        description="extracted=stated outright; inferred=filled from context/convention; "
                    "missing=not present; ambiguous=multiple plausible readings.",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Rough 0..1 confidence. Coarse hint only.",
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Short exact phrase from the email supporting this value; null if missing.",
    )

class ExtractionResult(BaseModel):
    """Flat structured output the model returns for a quote-request email."""
    dimensions: FieldExtraction
    box_style: FieldExtraction
    board_grade: FieldExtraction
    print_spec: FieldExtraction
    quantity: FieldExtraction
    logistics: FieldExtraction
```

> Note: every `value` is a string here even for quantity/dimensions, to keep the model's job
> uniform and structured-output-friendly. The mapper does typed parsing (str -> int, str ->
> Dimensions) with try/except so a malformed value degrades that ONE field to `ambiguous`
> rather than failing the whole extraction.

### The prompt

A module-level constant `EXTRACTION_SYSTEM_PROMPT`. Content requirements:
- Role: you extract corrugated-box quote specs from customer emails for an estimator.
- The six fields and what each means (dimensions L×W×D in inches; box_style e.g. RSC/die-cut;
  board_grade e.g. "32 ECT", "B-flute", "BC double-wall"; print_spec e.g. number of colors;
  quantity in units; logistics = delivery/location terms).
- Status rules (the four values, exactly as in decision #2).
- Do NOT guess a value and mark it `extracted`. If not clearly stated, use `missing` or
  `inferred` (and only `inferred` when a normal industry convention clearly applies).
- Return the evidence phrase verbatim from the email.
- Never invent dimensions, grades, or quantities that aren't supported by the text.

Keep it tight and rule-based. Put the email (body + any noted attachment text) in the human
message.

### The mapper (pure function, unit-testable)

```python
def to_quote_spec(result: ExtractionResult) -> QuoteSpec:
    """Map the flat LLM output into the typed QuoteSpec with ExtractedField wrappers.
    Typed parsing (quantity->int, dimensions->Dimensions) is done here with per-field
    try/except: a parse failure degrades THAT field to status=ambiguous, not the whole spec."""
```

- `dimensions`: parse "LxWxD" -> `Dimensions(length,width,depth)`; on failure -> value None,
  status `ambiguous`.
- `quantity`: parse int (strip commas/units); on failure -> None, `ambiguous`.
- string fields: pass through.
- Every field: carry `confidence` and set `source = evidence`.
- Preserve the model's `status` unless typed parsing forces `ambiguous`.

---

## `app/llm.py`

```python
from __future__ import annotations
import functools, os
from app.config import GEMINI_MODEL, GEMINI_TEMPERATURE, GOOGLE_API_KEY_ENV

@functools.lru_cache(maxsize=1)
def get_extractor():
    """Lazily build a structured-output LLM bound to ExtractionResult.
    Raises a clear RuntimeError if the API key is missing (caught by the node)."""
    if not os.environ.get(GOOGLE_API_KEY_ENV):
        raise RuntimeError(f"{GOOGLE_API_KEY_ENV} not set")
    from langchain_google_genai import ChatGoogleGenerativeAI
    from app.extraction import ExtractionResult
    llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=GEMINI_TEMPERATURE)
    return llm.with_structured_output(ExtractionResult)
```

- Lazy + `lru_cache` so import never triggers network/auth and the client is built once.
- Import `ChatGoogleGenerativeAI` *inside* the function so module import stays cheap and
  test-friendly.

---

## `app/nodes.py` — the new `extract`

Replace the stub body. Signature and return type unchanged (`(state) -> dict` with `{"spec": ...}`;
may also return `{"errors": [...]}` on failure).

```python
def extract(state: QuoteState) -> dict:
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.extraction import EXTRACTION_SYSTEM_PROMPT, to_quote_spec
    from app.llm import get_extractor

    email = state.raw_request.body if state.raw_request else ""
    try:
        extractor = get_extractor()
        result = extractor.invoke([
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=email),
        ])
        spec = to_quote_spec(result)
        log.info("[extract] extracted %d fields", 6)
        return {"spec": spec}
    except Exception as exc:
        log.exception("[extract] failed, degrading to all-missing")
        return {"spec": _all_missing_spec(), "errors": [f"extract: {exc}"]}
```

Add a helper `_all_missing_spec()` returning a `QuoteSpec` with all six fields
`value=None, confidence=0.0, source=None, status=FieldStatus.missing`.

> `errors` reducer: this is the first node that writes `errors`. If you haven't yet made it an
> append channel, do it now — annotate in `state.py`:
> `errors: Annotated[list[str], operator.add] = Field(default_factory=list)`
> (import `operator`, `from typing import Annotated`). Confirm LangGraph concatenates rather
> than overwrites. If Pydantic + Annotated reducer causes friction, the fallback is fine for
> the demo (only extract writes errors), but prefer fixing it — it's the audit-log seam.

---

## Fixtures (`fixtures/*.json`)

Each is a `QuoteRequestInput` JSON (`request_id`, `from`, `body`). Write realistic emails.

1. **`clean_email.json`** — all six fields clearly stated. e.g. "Please quote 5,000 RSC boxes,
   12x10x8, 32 ECT B-flute, 1-color print, delivered to our Dallas DC." Expect all
   `extracted`, high confidence.

2. **`messy_email.json`** — incomplete + ambiguous. e.g. a hurried email with dimensions and
   quantity but NO board grade, vague print ("needs our logo"), and fuzzy quantity ("a couple
   truckloads"). Expect: board_grade `missing`, quantity `ambiguous`, print_spec maybe
   `ambiguous`. THIS is the demo hero — it's where confidence indicators and flagged fields
   visibly do work.

3. **`prior_ref_email.json`** — references history: "Same spec as our last order (PO 4471) but
   bump to 7,500." Expect most fields `missing`/`inferred` with evidence pointing at the PO
   reference — motivates the enrichment layer (retrieval) in the narrative.

---

## Dependencies (add to `pyproject.toml`)

```
langchain-google-genai>=4.0.0
```

(Already have `langchain-core`, `langgraph`, `pydantic`, `fastapi`, `uvicorn`.)

Run `uv lock` / `uv sync` after adding so `uv.lock` updates (the Dockerfile builds `--frozen`).

---

## Acceptance criteria

1. With `GOOGLE_API_KEY` set locally:
   ```bash
   curl -s -X POST localhost:8080/quote -H 'content-type: application/json' \
     -d @fixtures/clean_email.json | python -m json.tool
   ```
   returns `200`, `status: delivered`, and `spec` fields populated with real values, mostly
   `status: "extracted"`, non-null `source` evidence snippets.

2. The messy fixture yields at least one `missing` and one `ambiguous` field, with lower
   confidence on the weak fields. (This is the key behavior to eyeball.)

3. With `GOOGLE_API_KEY` UNSET: the endpoint still returns `200` (not 500), `spec` is
   all-`missing`, and `errors` contains one `extract: ...` entry. (Graceful degradation.)

4. `to_quote_spec` has a couple of unit tests: a well-formed `ExtractionResult` maps correctly;
   a bad dimensions string ("12 by 10") degrades that field to `ambiguous` without raising.

5. Existing skeleton acceptance still passes for the other nodes; graph topology unchanged.

---

## Explicitly OUT of scope (still)

- Attachment/PDF/image parsing (fixtures are text-body only; note multimodal as future work).
- Retrieval / actually resolving the prior-order reference (enrichment layer, next).
- Human-in-the-loop interrupts / conditional edges (still straight-through).
- Real CoreERP costing (cost node still stub).
- Confidence calibration beyond the model's self-report (call it out as a known limitation).

---

## Talking points this unlocks (for interview prep, not to build)

- Why status-enum > raw confidence float (calibration honesty).
- Why flat-schema-then-map beats making the model emit nested wrappers (error rate, control).
- Why extraction runs at temperature 0 and is a single structured call, NOT an agent.
- Graceful degradation to all-missing = "the system never drops a request; worst case it
  falls back to today's manual process, but faster."
- Swap to Vertex backend = one env change (`GOOGLE_GENAI_USE_VERTEXAI=true`) — the Agent
  Engine production story stays intact.
