"""Smoke check: authenticate to Zepto MCP and save the current tool schemas."""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.zepto_mcp import MCP_URL, ZeptoMCPClient  # noqa: E402


async def main() -> None:
    client = ZeptoMCPClient()
    try:
        print("Connecting to Zepto MCP...")
        tools = await client.list_tools()
        output = {
            "server": MCP_URL,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "tools": tools,
        }
        path = Path(__file__).with_name("zepto_mcp_tools.json")
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Found {len(tools)} tools. Schemas saved to {path}")
        for item in tools:
            print(f"- {item['name']}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
