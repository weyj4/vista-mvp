from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.nodes import cost, deliver, enrich, extract, ingest, validate
from app.state import QuoteState

_builder = StateGraph(QuoteState)

_builder.add_node("ingest", ingest)
_builder.add_node("extract", extract)
_builder.add_node("enrich", enrich)
_builder.add_node("validate", validate)
_builder.add_node("cost", cost)
_builder.add_node("deliver", deliver)

_builder.add_edge(START, "ingest")
_builder.add_edge("ingest", "extract")
_builder.add_edge("extract", "enrich")
_builder.add_edge("enrich", "validate")
_builder.add_edge("validate", "cost")
_builder.add_edge("cost", "deliver")
_builder.add_edge("deliver", END)

app = _builder.compile()
