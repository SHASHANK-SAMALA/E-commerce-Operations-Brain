import asyncio
import sys
import uvicorn

from ecommerce_brain.config.settings import get_settings


if __name__ == "__main__":
    settings = get_settings()

    # On Windows, uvicorn's default ProactorEventLoop breaks psycopg3 async.
    # Explicitly create and install a SelectorEventLoop before handing control to uvicorn.
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
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

