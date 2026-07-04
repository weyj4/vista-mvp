from __future__ import annotations

import operator
from enum import Enum
from typing import Annotated, Any, Generic, Optional, TypeVar

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
    confidence: float = 1.0
    source: Optional[str] = None
    status: FieldStatus = FieldStatus.extracted


class Dimensions(BaseModel):
    length: float
    width: float
    depth: float


class QuoteSpec(BaseModel):
    dimensions: ExtractedField[Dimensions]
    box_style: ExtractedField[str]
    board_grade: ExtractedField[str]
    print_spec: ExtractedField[str]
    quantity: ExtractedField[int]
    logistics: ExtractedField[str]


class QuoteRequestInput(BaseModel):
    request_id: str
    from_: str = Field(alias="from")
    body: str

    model_config = {"populate_by_name": True}


class ValidationResult(BaseModel):
    status: str = "clean"
    flagged_fields: list[str] = Field(default_factory=list)


class Enrichment(BaseModel):
    retrieved: list[Any] = Field(default_factory=list)
    win_score: Optional[float] = None


class Quote(BaseModel):
    currency: str = "USD"
    total: float = 0.0
    line_items: list[Any] = Field(default_factory=list)


class QuoteState(BaseModel):
    request_id: str
    customer_id: Optional[str] = None
    raw_request: Optional[QuoteRequestInput] = None
    spec: Optional[QuoteSpec] = None
    enrichment: Optional[Enrichment] = None
    validation: Optional[ValidationResult] = None
    quote: Optional[Quote] = None
    status: str = "running"
    # Append reducer: each node's `errors` list is concatenated (audit log).
    errors: Annotated[list[str], operator.add] = Field(default_factory=list)
