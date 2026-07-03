from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.graph import app as graph_app
from app.state import QuoteRequestInput, QuoteState

log = logging.getLogger(__name__)

app = FastAPI(title="Quick Quotes (v0)")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/quote")
def quote(body: QuoteRequestInput) -> JSONResponse:
    try:
        initial = QuoteState(
            request_id=body.request_id,
            raw_request=body,
            status="running",
        )
        result = graph_app.invoke(initial)
        final = QuoteState.model_validate(result) if isinstance(result, dict) else result
        return JSONResponse(final.model_dump(by_alias=True))
    except Exception as exc:
        log.exception("quote pipeline failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
