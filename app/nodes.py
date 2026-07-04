from __future__ import annotations

import hashlib
import logging

from app.state import (
    Enrichment,
    ExtractedField,
    FieldStatus,
    Quote,
    QuoteSpec,
    QuoteState,
    ValidationResult,
)

log = logging.getLogger(__name__)


def _missing_field() -> ExtractedField:
    return ExtractedField(
        value=None,
        confidence=0.0,
        source=None,
        status=FieldStatus.missing,
    )


def _all_missing_spec() -> QuoteSpec:
    return QuoteSpec(
        dimensions=_missing_field(),
        box_style=_missing_field(),
        board_grade=_missing_field(),
        print_spec=_missing_field(),
        quantity=_missing_field(),
        logistics=_missing_field(),
    )


def ingest(state: QuoteState) -> dict:
    sender = state.raw_request.from_ if state.raw_request else ""
    customer_id = "cust_" + hashlib.sha1(sender.encode()).hexdigest()[:8]
    log.info("[ingest] request_id=%s", state.request_id)
    return {"customer_id": customer_id, "status": "running"}


def extract(state: QuoteState) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.extraction import EXTRACTION_SYSTEM_PROMPT, to_quote_spec
    from app.llm import get_extractor

    email = state.raw_request.body if state.raw_request else ""
    try:
        extractor = get_extractor()
        result = extractor.invoke(
            [
                SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
                HumanMessage(content=email),
            ]
        )
        spec = to_quote_spec(result)
        extracted_count = sum(
            1
            for f in (
                spec.dimensions,
                spec.box_style,
                spec.board_grade,
                spec.print_spec,
                spec.quantity,
                spec.logistics,
            )
            if f.status == FieldStatus.extracted
        )
        log.info("[extract] extracted=%d/6", extracted_count)
        return {"spec": spec}
    except Exception as exc:
        log.exception("[extract] failed, degrading to all-missing")
        return {"spec": _all_missing_spec(), "errors": [f"extract: {exc}"]}


def enrich(state: QuoteState) -> dict:
    log.info("[enrich] stub win_score=0.5")
    return {"enrichment": Enrichment(retrieved=[], win_score=0.5)}


def validate(state: QuoteState) -> dict:
    log.info("[validate] clean")
    return {"validation": ValidationResult(status="clean", flagged_fields=[])}


def cost(state: QuoteState) -> dict:
    log.info("[cost] stub total=4200")
    return {"quote": Quote(currency="USD", total=4200.00, line_items=[])}


def deliver(state: QuoteState) -> dict:
    log.info("[deliver] done")
    return {"status": "delivered"}
