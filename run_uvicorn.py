"""Local uvicorn launcher.

Docker deployments should use ``uvicorn ecommerce_brain.api.main:app``
directly via CMD/ENTRYPOINT — this script is for local development only.

Windows note: uvicorn's default ProactorEventLoop is incompatible with
psycopg3's async connection pool (uses SelectorEventLoop internally).
We explicitly install SelectorEventLoop before starting uvicorn so that
``asyncio.get_event_loop()`` returns the correct loop type everywhere.
On Linux/macOS the default event loop is already SelectorEventLoop-based.
"""

from __future__ import annotations

import asyncio
import sys

import uvicorn

from ecommerce_brain.config.settings import get_settings


if __name__ == "__main__":
    settings = get_settings()

    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    config = uvicorn.Config(
        "ecommerce_brain.api.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=False,
    )
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())

