# ovos-mcp-toolbox

> ⚠️ **WORK IN PROGRESS — NOT PUBLISHED, NOT SAFE FOR REAL SIDE-EFFECT TOOLS.**
> As of 2026-08-20, the full chain works end-to-end including a real
> confirmation gate: a real LLM (via a public demo Ollama) reasons about
> a question, correctly disambiguates between two similarly-named
> entities, and calls tools through `MCPToolBox` against real Home
> Assistant — with a per-server, per-tool-name policy fail-closed
> refusing any call not explicitly allowed. See
> [TESTING_LOG.md](TESTING_LOG.md) for the full trail, including a
> topology mistake found and reversed mid-build (an earlier version
> shared policy via OVOS skill settings, which silently assumed the
> toolbox and a skill share a filesystem — broken for a standalone
> `ovos-persona-server` on a different host; policy now lives in this
> toolbox's own config instead, like the rest of the
> `ovos-agentic-loop` ecosystem already does). There is still **no
> pause-and-ask mechanism** — a call the policy flags is refused
> outright, not paused for a human answer, since `ReActLoopEngine` has
> no built-in way to pause mid-loop yet. Building that is the next
> priority.

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
- [x] Confirmation gate for tools with side-effects — **classification +
      fail-closed enforcement DONE 2026-08-20**, verified live: HassTurnOn
      correctly refused (not in never_confirm), GetDateTime correctly
      allowed (in never_confirm), state independently confirmed unchanged
      after a refused call. Still missing the actual pause-and-ask
      mechanism - see warning banner.
- [x] Graceful degradation when a configured server is unreachable —
      implemented (`LOG.warning` + skip), not yet tested against an
      actually-offline server (only tested against one that was always up)
- [ ] stdio transport — **not implemented**, only HTTP so far
- [x] Tested against a live MCP server (Home Assistant, 192.168.65.186) —
      see [TESTING_LOG.md](TESTING_LOG.md) for exact requests/responses
- [ ] Tested against a second MCP server simultaneously — **not done**
- [x] Run inside an actual `ovos-agentic-loop` `ReActLoopEngine` with a
      real LLM `brain` — **DONE 2026-08-20**, using the public demo
      Ollama (`https://ollama.uoi.io/v1`, `qwen3:8b`) as brain. Full
      question → tool choice → MCP call → live HA data → natural-language
      answer, verified correct against wall-clock time. Two real bugs
      found and worked around along the way — see TESTING_LOG.md.
- [x] Side-effect tools (`HassTurnOn`/`HassTurnOff`) — **DONE 2026-08-20**,
      tested against two safe virtual `input_boolean` helpers created for
      this purpose. LLM correctly disambiguated between two
      similarly-named entities across two separate requests; both
      resulting state changes verified independently against HA's own
      `/api/states`, not just the tool's own reported success.
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

## Config shape

```json
{
  "ovos-mcp-tools": {
    "servers": [
      {
        "name": "ha",
        "transport": "http",
        "url": "http://192.168.65.186/api/mcp",
        "token": "..."
      },
      {
        "name": "dc",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@wonderwhy-er/desktop-commander"]
      }
    ],
    "policy": {
      "ha__default_confirm": true,
      "ha__always_confirm": "HassBroadcast",
      "ha__never_confirm": "GetDateTime,GetLiveContext"
    },
    "scaffold_path": "/home/andlo/.local/state/ovos-mcp-toolbox/policy_scaffold.json"
  }
}
```

`transport: "stdio"` is accepted but not implemented yet - see status
table.

## Confirmation policy

See [policy.py](ovos_mcp_toolbox/policy.py)'s module docstring for the
full design writeup - short version here.

**Server-agnostic, tool-name-based.** The only thing every MCP server's
`tools/list` reliably gives us is a flat list of tool name strings -
no shared ontology across servers (Home Assistant has "domains", a
filesystem MCP server doesn't). MCP's own `annotations`
(`readOnlyHint`/`destructiveHint`) would have been the proper signal,
but HA doesn't send them (checked live, see TESTING_LOG.md) - so
policy is just per-server, per-tool-name:

- `{server}__default_confirm` (bool, default `true` - unknown tool = confirm)
- `{server}__always_confirm` (comma-separated tool names)
- `{server}__never_confirm` (comma-separated tool names)

**Lives in this toolbox's own config, not OVOS skill settings.** An
earlier version stored policy in a companion OVOSSkill's
`settings.json`, shared with `MCPToolBox` by both reading the same
file on disk. That silently assumed the toolbox and ovos-core's skill
manager run on the same host with a shared filesystem - true if the
persona runs inside `ovos-core` itself, false for a standalone
`ovos-persona-server` on a different machine. Reversed in favour of
plain config, matching how `ShellToolBox`'s `allow_shell` and
`FileSystemToolBox`'s `allow_write` already work in
`ovos-agentic-loop` itself - no new infrastructure, works regardless
of where the toolbox actually runs.

**How a user knows what to write.** You can't write a sensible
`never_confirm` list without first seeing what tool names a server
exposes. Two ways to get that:

1. Standalone CLI, before you've even added the server to persona.json:
   ```
   python -m ovos_mcp_toolbox.policy_scaffold \
       --name ha --url http://192.168.65.186/api/mcp --token <token>
   ```
2. Set `"scaffold_path"` in the toolbox's own config (opt-in, `None`/absent
   by default - never guesses a directory on your behalf) and
   `MCPToolBox` writes/updates a reference file there every time
   `discover_tools()` runs successfully, one section per server,
   merging rather than overwriting (a temporarily-offline server keeps
   its last-known entry). Never touches persona.json itself.

**Enforcement is fail-closed, not fail-silent.** `_make_tool_call`'s
closure checks the policy before every call. If confirmation is
required, the call is refused with a clear message back to the
LLM/loop - it is never silently executed and never silently skipped.
There is no pause-and-ask mechanism yet (see warning banner at top);
this is the interim safe default, not the finished feature.

## Not yet decided

- Whether this should live as one `ovos-mcp-toolbox` per persona, or
  whether each MCP server should get its own toolbox instance
- Two-stage discovery design
- What "confirmation" actually looks like on the bus (new message type?
  piggyback on existing `ovos.persona.tools.*` events?)

## License

Apache-2.0 (matches `ovos-agentic-loop` and the rest of the OVOS
ecosystem), once/if this becomes real.
