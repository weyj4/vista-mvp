from __future__ import annotations

import os

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TEMPERATURE = float(os.environ.get("GEMINI_TEMPERATURE", "0.0"))
GOOGLE_API_KEY_ENV = "GOOGLE_API_KEY"
