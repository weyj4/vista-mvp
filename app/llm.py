from __future__ import annotations

import functools
import os

from app.config import GEMINI_MODEL, GEMINI_TEMPERATURE, GOOGLE_API_KEY_ENV


@functools.lru_cache(maxsize=1)
def get_extractor():
    """Lazily build a structured-output LLM bound to ExtractionResult.

    Raises RuntimeError if the API key is missing (caught by the extract node so the
    pipeline degrades gracefully rather than crashing).
    """
    if not os.environ.get(GOOGLE_API_KEY_ENV):
        raise RuntimeError(f"{GOOGLE_API_KEY_ENV} not set")

    from langchain_google_genai import ChatGoogleGenerativeAI

    from app.extraction import ExtractionResult

    llm = ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        temperature=GEMINI_TEMPERATURE,
    )
    return llm.with_structured_output(ExtractionResult)
