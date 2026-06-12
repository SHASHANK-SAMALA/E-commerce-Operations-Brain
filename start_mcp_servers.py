"""Launch all 5 MCP servers as subprocesses.

Each server's stdout+stderr is streamed to logs/mcp_<name>.log so we can
debug tool errors without attaching to the parent process.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

SERVERS = [
    "ecommerce_brain/mcp_servers/sales_mcp_server.py",
    "ecommerce_brain/mcp_servers/inventory_mcp_server.py",
    "ecommerce_brain/mcp_servers/marketing_mcp_server.py",
    "ecommerce_brain/mcp_servers/support_mcp_server.py",
    "ecommerce_brain/mcp_servers/action_mcp_server.py",
]

LOG_DIR = Path("logs")


def _log_path_for(server_path: str) -> Path:
    name = Path(server_path).stem  # e.g. "sales_mcp_server"
    return LOG_DIR / f"{name}.log"


def main() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    print("Starting all MCP servers...")
    processes: list[tuple[subprocess.Popen, object]] = []
    try:
        for server in SERVERS:
            log_path = _log_path_for(server)
            print(f"Starting {server} (logs → {log_path})")
            log_handle = log_path.open("a", buffering=1)  # line-buffered
            p = subprocess.Popen(
                [sys.executable, server],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
            processes.append((p, log_handle))
            time.sleep(1)  # stagger startups slightly

        print(f"All {len(processes)} MCP servers started. Press Ctrl+C to stop.")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down MCP servers...")
        for p, _ in processes:
            p.terminate()
        for p, fh in processes:
            p.wait()
            fh.close()
        print("Done.")


if __name__ == "__main__":
    main()
