from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from app.state import (
    Dimensions,
    ExtractedField,
    FieldStatus,
    QuoteSpec,
)


class FieldExtraction(BaseModel):
    """One extracted field: the value plus the model's self-assessment."""

    value: Optional[str] = Field(
        default=None,
        description=(
            "The extracted value as a string, or null if not present. "
            "For dimensions use 'LxWxD' (e.g. '12x10x8'). For quantity, digits only."
        ),
    )
    status: FieldStatus = Field(
        description=(
            "extracted=stated outright; inferred=filled from context/convention; "
            "missing=not present; ambiguous=multiple plausible readings."
        ),
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
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


EXTRACTION_SYSTEM_PROMPT = """\
You extract corrugated-box quote specifications from customer emails for a sales
estimator. Return a structured record with six fields; each carries a value plus a
status, confidence, and short evidence phrase quoted from the email.

Fields:
- dimensions: length × width × depth in INCHES, formatted as "LxWxD" (e.g. "12x10x8").
- box_style: e.g. "RSC", "die-cut", "HSC", "FOL". Report what the customer names.
- board_grade: e.g. "32 ECT", "B-flute", "BC double-wall", "44# kraft". Report as written.
- print_spec: e.g. "1 color", "2 color flexo", "unprinted", "custom logo". Report as written.
- quantity: integer number of units. Digits only (strip commas and units).
- logistics: delivery/freight/location terms. e.g. "FOB origin", "delivered to Dallas DC".

Status rules — apply strictly to every field:
- extracted: the value is stated outright in the email.
- inferred: not stated outright, but a standard industry convention clearly fills it (rare).
- missing: not present at all.
- ambiguous: multiple plausible readings (e.g. "a couple truckloads" for quantity).

Hard rules:
- Never invent a dimension, grade, or quantity that the text does not support.
- Do NOT mark a field "extracted" unless the value appears explicitly in the email.
- `evidence` must be a verbatim snippet from the email; use null when status is "missing".
- If torn between "inferred" and "ambiguous", prefer "ambiguous".
- `confidence` is a rough 0..1 hint; use lower values for inferred/ambiguous fields.
"""


_DIM_SPLIT = re.compile(r"\s*[xX×]\s*")
_DIGITS = re.compile(r"[^\d]")


def _parse_dimensions(raw: str) -> Dimensions:
    parts = _DIM_SPLIT.split(raw.strip())
    if len(parts) != 3:
        raise ValueError(f"expected LxWxD, got {raw!r}")
    length, width, depth = (float(p) for p in parts)
    return Dimensions(length=length, width=width, depth=depth)


def _parse_quantity(raw: str) -> int:
    digits = _DIGITS.sub("", raw)
    if not digits:
        raise ValueError(f"no digits in {raw!r}")
    return int(digits)


def _wrap(fe: FieldExtraction, value, *, status: FieldStatus | None = None) -> ExtractedField:
    return ExtractedField(
        value=value,
        confidence=fe.confidence,
        source=fe.evidence,
        status=status if status is not None else fe.status,
    )


def _map_string(fe: FieldExtraction) -> ExtractedField[str]:
    return _wrap(fe, fe.value)


def _map_dimensions(fe: FieldExtraction) -> ExtractedField[Dimensions]:
    if fe.status == FieldStatus.missing or not fe.value:
        return _wrap(fe, None)
    try:
        return _wrap(fe, _parse_dimensions(fe.value))
    except (ValueError, TypeError):
        return _wrap(fe, None, status=FieldStatus.ambiguous)


def _map_quantity(fe: FieldExtraction) -> ExtractedField[int]:
    if fe.status == FieldStatus.missing or not fe.value:
        return _wrap(fe, None)
    try:
        return _wrap(fe, _parse_quantity(fe.value))
    except (ValueError, TypeError):
        return _wrap(fe, None, status=FieldStatus.ambiguous)


def to_quote_spec(result: ExtractionResult) -> QuoteSpec:
    """Map the flat LLM output into the typed QuoteSpec with ExtractedField wrappers.

    Typed parsing (quantity->int, dimensions->Dimensions) happens here with per-field
    try/except: a parse failure degrades THAT field to status=ambiguous, not the whole spec.
    """
    return QuoteSpec(
        dimensions=_map_dimensions(result.dimensions),
        box_style=_map_string(result.box_style),
        board_grade=_map_string(result.board_grade),
        print_spec=_map_string(result.print_spec),
        quantity=_map_quantity(result.quantity),
        logistics=_map_string(result.logistics),
    )
