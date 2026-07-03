from __future__ import annotations

import hashlib
import logging

from app.state import (
    Dimensions,
    Enrichment,
    ExtractedField,
    FieldStatus,
    Quote,
    QuoteSpec,
    QuoteState,
    ValidationResult,
)

log = logging.getLogger(__name__)


def _stub_field(value):
    return ExtractedField(
        value=value,
        confidence=1.0,
        source="stub",
        status=FieldStatus.extracted,
    )


def ingest(state: QuoteState) -> dict:
    sender = state.raw_request.from_ if state.raw_request else ""
    customer_id = "cust_" + hashlib.sha1(sender.encode()).hexdigest()[:8]
    log.info("[ingest] request_id=%s", state.request_id)
    return {"customer_id": customer_id, "status": "running"}


def extract(state: QuoteState) -> dict:
    spec = QuoteSpec(
        dimensions=_stub_field(Dimensions(length=12, width=10, depth=8)),
        box_style=_stub_field("RSC"),
        board_grade=_stub_field("32 ECT"),
        print_spec=_stub_field("1 color"),
        quantity=_stub_field(5000),
        logistics=_stub_field("FOB origin"),
    )
    log.info("[extract] stub spec produced")
    return {"spec": spec}


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
