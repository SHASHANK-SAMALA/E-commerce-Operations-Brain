import subprocess
import sys
import time

SERVERS = [
    "ecommerce_brain/mcp_servers/sales_mcp_server.py",
    "ecommerce_brain/mcp_servers/inventory_mcp_server.py",
    "ecommerce_brain/mcp_servers/marketing_mcp_server.py",
    "ecommerce_brain/mcp_servers/support_mcp_server.py",
    "ecommerce_brain/mcp_servers/action_mcp_server.py",
]

def main():
    print("Starting all MCP servers...")
    processes = []
    try:
        for server in SERVERS:
            print(f"Starting {server}...")
            p = subprocess.Popen(
                [sys.executable, server],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT
            )
            processes.append(p)
            time.sleep(1) # stagger startups slightly

        print(f"All {len(processes)} MCP servers started. Press Ctrl+C to stop.")

        # Keep main thread alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down MCP servers...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.wait()
        print("Done.")

if __name__ == "__main__":
    main()
