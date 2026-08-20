#!/usr/bin/env python3
"""
policy_scaffold.py — WORK IN PROGRESS. See README.md.

Standalone helper: connect to one MCP server, list its tools, and print
a ready-to-paste policy scaffold for persona.json's "policy" block -
because a user cannot write a sensible {server}__never_confirm list
without first seeing what tool names the server actually exposes.

Deliberately a plain script, not tied to any OVOS skill/settings
machinery - works the same regardless of whether MCPToolBox ends up
running inside ovos-core or a standalone ovos-persona-server, on the
same host as anything else or not. It only needs network access to the
MCP server itself.

Usage:
    python -m ovos_mcp_toolbox.policy_scaffold \\
        --name ha --url http://192.168.65.186/api/mcp --token <token>

Prints:
    1. The full list of tool names the server currently exposes
       (so you can actually see what you're writing a policy for)
    2. A ready-to-paste "policy" JSON block, defaulting every tool to
       default_confirm=true (safe-by-default) with empty override lists
       for you to fill in
"""
import argparse
import json
import sys

from ovos_mcp_toolbox import MCPHTTPClient, MCPServerConfig


def scaffold(name: str, url: str, token: str = None,
             transport: str = "http") -> None:
    server = MCPServerConfig(name=name, transport=transport, url=url, token=token)
    if transport != "http":
        print(f"transport='{transport}' not implemented yet, only 'http' works.",
              file=sys.stderr)
        sys.exit(1)

    client = MCPHTTPClient(server)
    try:
        tools = client.list_tools()
    except Exception as e:
        print(f"Could not reach '{name}' at {url}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"# {len(tools)} tool(s) found on '{name}':\n")
    for t in tools:
        desc = (t.get("description") or "").split(".")[0]  # first sentence only
        print(f"  - {t['name']}: {desc}")

    print(f"\n# Paste into persona.json under \"ovos-mcp-tools\"[\"policy\"]:")
    print("# (default_confirm=true means every tool above needs confirmation")
    print("#  until you list it in never_confirm - safe-by-default)")
    print(json.dumps({
        f"{name}__default_confirm": True,
        f"{name}__always_confirm": "",
        f"{name}__never_confirm": "",
    }, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", required=True, help="Server name, matches persona.json's servers[].name")
    p.add_argument("--url", required=True)
    p.add_argument("--token", default=None)
    p.add_argument("--transport", default="http")
    args = p.parse_args()
    scaffold(args.name, args.url, args.token, args.transport)


if __name__ == "__main__":
    main()
