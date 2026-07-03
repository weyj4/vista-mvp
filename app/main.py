from __future__ import annotations

import logging
import os

import uvicorn


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(
        "app.server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )


if __name__ == "__main__":
    main()
