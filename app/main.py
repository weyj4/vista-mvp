from __future__ import annotations

import logging
import os

import uvicorn


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true":
        logging.getLogger(__name__).info(
            "langsmith tracing enabled project=%s",
            os.environ.get("LANGSMITH_PROJECT", "default"),
        )
    uvicorn.run(
        "app.server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )


if __name__ == "__main__":
    main()
