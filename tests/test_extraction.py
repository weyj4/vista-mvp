from __future__ import annotations

from app.extraction import ExtractionResult, FieldExtraction, to_quote_spec
from app.state import FieldStatus


def _fe(value, status=FieldStatus.extracted, confidence=0.9, evidence=None):
    return FieldExtraction(
        value=value,
        status=status,
        confidence=confidence,
        evidence=evidence if evidence is not None else value,
    )


def _well_formed() -> ExtractionResult:
    return ExtractionResult(
        dimensions=_fe("12x10x8", evidence="12x10x8 (inches)"),
        box_style=_fe("RSC", evidence="RSC boxes"),
        board_grade=_fe("32 ECT B-flute", evidence="32 ECT B-flute"),
        print_spec=_fe("1 color", evidence="1-color print"),
        quantity=_fe("5000", evidence="5,000"),
        logistics=_fe("FOB origin, Dallas DC", evidence="FOB origin to our Dallas DC"),
    )


def test_well_formed_maps_cleanly():
    spec = to_quote_spec(_well_formed())

    assert spec.dimensions.status == FieldStatus.extracted
    assert spec.dimensions.value.length == 12
    assert spec.dimensions.value.width == 10
    assert spec.dimensions.value.depth == 8
    assert spec.dimensions.source == "12x10x8 (inches)"

    assert spec.quantity.value == 5000
    assert spec.quantity.source == "5,000"

    assert spec.box_style.value == "RSC"
    assert spec.board_grade.value == "32 ECT B-flute"
    assert spec.print_spec.value == "1 color"
    assert spec.logistics.value == "FOB origin, Dallas DC"


def test_bad_dimensions_degrades_to_ambiguous():
    result = _well_formed().model_copy(
        update={"dimensions": _fe("12 by 10", evidence="12 by 10")}
    )
    spec = to_quote_spec(result)

    assert spec.dimensions.value is None
    assert spec.dimensions.status == FieldStatus.ambiguous
    assert spec.dimensions.source == "12 by 10"
    # Other fields are untouched.
    assert spec.quantity.value == 5000
    assert spec.box_style.value == "RSC"


def test_missing_field_passes_through():
    result = _well_formed().model_copy(
        update={
            "board_grade": FieldExtraction(
                value=None,
                status=FieldStatus.missing,
                confidence=0.0,
                evidence=None,
            )
        }
    )
    spec = to_quote_spec(result)

    assert spec.board_grade.value is None
    assert spec.board_grade.status == FieldStatus.missing
    assert spec.board_grade.source is None
    assert spec.board_grade.confidence == 0.0


def test_unparseable_quantity_degrades_to_ambiguous():
    result = _well_formed().model_copy(
        update={
            "quantity": _fe(
                "a couple truckloads",
                status=FieldStatus.ambiguous,
                confidence=0.2,
            )
        }
    )
    spec = to_quote_spec(result)

    assert spec.quantity.value is None
    assert spec.quantity.status == FieldStatus.ambiguous


def test_dimensions_accepts_various_separators():
    for raw in ("12 x 10 x 8", "12X10X8", "12×10×8"):
        result = _well_formed().model_copy(
            update={"dimensions": _fe(raw)}
        )
        spec = to_quote_spec(result)
        assert spec.dimensions.value.length == 12
        assert spec.dimensions.value.width == 10
        assert spec.dimensions.value.depth == 8
        assert spec.dimensions.status == FieldStatus.extracted


def test_quantity_strips_commas_and_units():
    for raw, expected in (("5,000", 5000), ("7500 pcs", 7500), ("10,000 units", 10000)):
        result = _well_formed().model_copy(update={"quantity": _fe(raw)})
        spec = to_quote_spec(result)
        assert spec.quantity.value == expected, f"{raw!r} -> {spec.quantity.value}"
