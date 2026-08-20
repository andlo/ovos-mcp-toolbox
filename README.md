# ovos-mcp-toolbox

> ⚠️ **WORK IN PROGRESS — NOT FUNCTIONAL, NOT TESTED, NOT PUBLISHED.**
> This repo exists to explore an idea. Nothing here has run against a real
> MCP server yet. Expect it to be broken, incomplete, or abandoned. Do not
> install this on a live OVOS instance. Do not point it at anything with
> real side-effects (smart locks, financial tools, etc.) until there is a
> working confirmation-gate and it has been tested extensively.

## The idea

[`ovos-agentic-loop`](https://github.com/OpenVoiceOS/ovos-agentic-loop) lets
an OVOS persona reason over "toolboxes" (filesystem, shell, math, web search,
...) using a ReAct-style loop. Each toolbox is a small Python plugin that
implements one method, `discover_tools()`, and hand-writes an `AgentTool`
per capability.

Separately, the [Model Context Protocol](https://modelcontextprotocol.io)
(MCP) has become the standard way tools are exposed to LLM agents —
Home Assistant, Desktop Commander, and a growing list of other services
all speak it. Every MCP server already answers a `tools/list` call with a
name, description, and JSON schema for each tool it offers.

**The idea is a single toolbox that bridges the two**: instead of writing
one `ovos-*-toolbox` plugin per service, point `ovos-mcp-toolbox` at any
number of MCP server URLs in persona config, and it discovers whatever
tools those servers expose at runtime — translating each into an
`AgentTool` that `ovos-agentic-loop` can already reason about. Add a new
MCP server (Home Assistant, Desktop Commander, whatever comes next) and
the persona gains those capabilities without a single line of new skill
code.

## Why this might not be a good idea

Writing this down honestly, before getting attached to it:

- **Confirmation/safety is unsolved.** Some MCP tools are read-only
  (list files, query a sensor). Some are not (unlock a door, delete a
  file, run a shell command). `ovos-agentic-loop`'s own `ShellToolBox`
  defaults `allow_shell` to `False` for exactly this reason. A generic
  MCP bridge has no way to know which category a remote tool falls into
  from its schema alone — that has to be solved before this touches
  anything with real side-effects.
- **Tool-catalog size.** A handful of MCP servers can produce 100+ tools
  combined (Home Assistant alone exposes 70+). Dumping all of them into
  every LLM call is wasteful and may exceed context/latency budgets. This
  probably needs two-stage discovery (cheap name+description search,
  then full schema only for the shortlist) — not designed yet.
- **Auth model varies per server** (bearer token, none, mTLS, ...) — not
  designed yet, config schema below is a first guess.
- **It might just not be that useful in practice.** Untested hypothesis.

If any of the above turns out to be a dead end, this repo gets archived —
that's a fine outcome.

## Status

- [x] Verified `ToolBox` / `AgentTool` interface against installed
      `ovos-plugin-manager` source (`templates/agent_tools.py`) and the
      real `ovos-wolfram-alpha-plugin` implementation as reference.
- [ ] `MCPToolBox.discover_tools()` — connects to configured MCP servers,
      maps `tools/list` response to `AgentTool` instances
- [ ] `MCPToolBox.<handler>` — calls the remote tool via MCP, returns
      validated `ToolOutput`
- [ ] Confirmation gate for tools with side-effects
- [ ] Graceful degradation when a configured server is unreachable
- [ ] Tested against a live MCP server (ha-mcp) — **blocked, see below**
- [ ] Tested against a second MCP server simultaneously — **not done**
- [ ] Packaged/published — **not done, do not `pip install` from PyPI,
      it isn't there**

**Blocked on infrastructure, not on this repo's code** — see
[TESTING_LOG.md](TESTING_LOG.md) for full details:

1. The entire `ToolBox`/`AgentTool` interface this project depends on
   only exists in **alpha** builds of `ovos-plugin-manager`
   (`>=2.2.1a2`; latest stable is `2.2.0`). Even `ovos-agentic-loop`'s
   PyPI-stable `0.1.0` release requires an alpha `ovos-plugin-manager`.
   Nothing stable to build against yet.
2. Home Assistant's MCP Server integration doesn't answer on any
   standard path on the available test instance (192.168.65.186) —
   unclear yet whether it's installed/enabled at all.
3. No LLM backend (Ollama or otherwise) is running anywhere on the test
   network yet, so there's nothing to wire up as the loop's `brain`
   even once the above are sorted.

## Verified interface (for reference while building)

Confirmed against `ovos_plugin_manager/templates/agent_tools.py` and
`ovos_wolfram_alpha_plugin/__init__.py` on 2026-08-20:

```python
from ovos_plugin_manager.templates.agent_tools import (
    ToolBox, AgentTool, ToolArguments, ToolOutput
)

class MyArgs(ToolArguments):
    query: str

class MyOutput(ToolOutput):
    result: str

class MyToolBox(ToolBox):
    toolbox_id = "my-tools"

    def my_method(self, args: MyArgs) -> MyOutput:
        return MyOutput(result=f"handled {args.query}")

    def discover_tools(self) -> list[AgentTool]:
        return [
            AgentTool(
                name="do_thing",
                description="...",
                argument_schema=MyArgs,
                output_schema=MyOutput,
                tool_call=self.my_method,
            )
        ]
```

`ToolBox.__init__` takes `(toolbox_id, config=None, bus=None)`. Entry
point group is `opm.agents.toolbox`.

## Config shape (draft, unverified)

```json
{
  "ovos-mcp-tools": {
    "servers": [
      {
        "name": "ha",
        "transport": "sse",
        "url": "http://192.168.65.43:8123/mcp_server/sse",
        "token": "..."
      },
      {
        "name": "dc",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@wonderwhy-er/desktop-commander"]
      }
    ]
  }
}
```

## Not yet decided

- Whether this should live as one `ovos-mcp-toolbox` per persona, or
  whether each MCP server should get its own toolbox instance
- Two-stage discovery design
- What "confirmation" actually looks like on the bus (new message type?
  piggyback on existing `ovos.persona.tools.*` events?)

## License

Apache-2.0 (matches `ovos-agentic-loop` and the rest of the OVOS
ecosystem), once/if this becomes real.
