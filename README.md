# ovos-mcp-toolbox

> ⚠️ **WORK IN PROGRESS — NOT PUBLISHED, NOT SAFE FOR SIDE-EFFECT TOOLS.**
> As of 2026-08-20, `discover_tools()` and tool execution over the MCP
> Streamable HTTP transport are implemented and hand-verified end-to-end
> against a real Home Assistant MCP endpoint — see
> [TESTING_LOG.md](TESTING_LOG.md). There is still **no confirmation gate**:
> every discovered tool, including side-effect ones like `HassTurnOn`
> (which can unlock doors), is callable immediately. This has only been run
> by calling `discover_tools()`/`call_tool()` directly in a script — never
> through an actual `ovos-agentic-loop` `ReActLoopEngine` with a real LLM
> making the tool-choice decisions. Do not point this at anything with real
> side-effects in an unsupervised loop yet.

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
- [x] `MCPToolBox.discover_tools()` — connects to configured MCP servers
      over HTTP transport, maps `tools/list` to `AgentTool` instances.
      Verified against live HA: all 10 real tools discovered, JSON-schema
      → pydantic conversion handles both plain `properties` and `anyOf`
      fields correctly (the `anyOf` case needed a real bugfix — see
      TESTING_LOG.md).
- [x] Tool execution — calls the remote tool via MCP `tools/call`, returns
      validated `ToolOutput`. Verified through the *full* `ToolBox.call_tool()`
      path (input validation → execution → output validation), not just
      the bare HTTP call.
- [ ] Confirmation gate for tools with side-effects — **not implemented,
      the main safety gap right now**
- [x] Graceful degradation when a configured server is unreachable —
      implemented (`LOG.warning` + skip), not yet tested against an
      actually-offline server (only tested against one that was always up)
- [ ] stdio transport — **not implemented**, only HTTP so far
- [x] Tested against a live MCP server (Home Assistant, 192.168.65.186) —
      see [TESTING_LOG.md](TESTING_LOG.md) for exact requests/responses
- [ ] Tested against a second MCP server simultaneously — **not done**
- [ ] Run inside an actual `ovos-agentic-loop` `ReActLoopEngine` with a
      real LLM `brain` — **not done**, only called directly in scripts.
      No LLM backend (Ollama etc.) is running on the test network yet.
- [ ] Packaged/published — **not done, do not `pip install` from PyPI,
      it isn't there**

**Still blocked on one piece of infrastructure**, unrelated to whether
the code works: the entire `ToolBox`/`AgentTool` interface this project
depends on only exists in **alpha** builds of `ovos-plugin-manager`
(`>=2.2.1a2`; latest stable is `2.2.0`). Even `ovos-agentic-loop`'s
PyPI-stable `0.1.0` release requires an alpha `ovos-plugin-manager`. That
means running this for real on the OVOS test instance (currently on
stable `2.2.0`) means opting it into alpha dependencies first — a decision
for Andreas, not made yet.

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
