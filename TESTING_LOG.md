# Testing log

Real findings from probing the actual infrastructure, 2026-08-20.
Written here instead of guessed at, so the README's status section stays honest.

## OVOS test instance (192.168.65.43)

- SSH reachable, `ovos-core`, `ovos-audio`, `ovos-messagebus`, `ovos-phal`
  all running via systemd --user units, as expected.
- venv at `~/.venvs/ovos`, Python 3.11.
- Currently installed: `ovos-plugin-manager==2.2.0` (latest **stable**),
  `ovos_wolfram_alpha_solver==0.0.4`. `ovos-agentic-loop` is **not**
  installed here yet.
- **Important finding**: `ovos_plugin_manager.templates.agent_tools`
  (the `ToolBox`/`AgentTool` module this whole project depends on) does
  **not exist in any stable release** of `ovos-plugin-manager`. It only
  exists starting at `2.2.1a2`, i.e. alpha-only, all the way up through
  the current `2.11.1a2`. Latest stable is still `2.2.0`.
- Even `ovos-agentic-loop`'s own PyPI-labelled-stable release, `0.1.0`,
  declares `Requires-Dist: ovos-plugin-manager<3.0.0,>=2.3.0a1` — so
  there is currently **no way to use ovos-agentic-loop without pulling
  in an alpha dependency**, regardless of which ovos-agentic-loop
  version is used.
- No LLM backend (checked `:11434` for Ollama) is reachable on `.43` or
  `.186`. Nothing to wire up as `brain` yet even if the toolbox worked.
- **Consequence for this project**: before `MCPToolBox` can be tested
  end-to-end on this instance, it needs `pip install --pre
  ovos-plugin-manager ovos-agentic-loop` in the ovos venv (not done yet
  — didn't want to touch a live instance's dependency pins without
  Andreas's go-ahead), plus some `brain` ChatEngine pointed at a real
  LLM endpoint.

## Home Assistant (192.168.65.186)

**UPDATE 2026-08-20, later same day**: The official MCP Server
integration has now been added. Full round-trip tested manually with
`curl` + a long-lived access token (token itself NOT stored in this
repo or logged anywhere here):

- `initialize` → `200 OK`, `serverInfo: {"name": "home-assistant",
  "version": "1.26.0"}`, protocol `2024-11-05`.
- `tools/list` → **10 real tools** returned: `HassBroadcast`,
  `GetLiveContext`, `HassTurnOn`, `HassTurnOff`, `HassCancelAllTimers`,
  `GetDateTime`, `todo_get_items`, `HassListAddItem`,
  `HassListCompleteItem`, `HassListRemoveItem`.
- `tools/call` on `GetDateTime` (read-only, no args) → `200 OK`,
  `{"content": [{"type": "text", "text": "{...}"}], "isError": false}`
  — confirms the response shape `MCPToolBox._call_remote_tool()` in
  the skeleton already assumes (`block.text` per content item) is
  correct.
- Auth: two gotchas found by trial, worth remembering — (1) requires
  `Accept: application/json, text/event-stream`, not just
  `application/json`, or HA returns `400 Client must accept
  application/json`; (2) requires `Authorization: Bearer <long-lived
  token>`, standard OAuth-style 401 challenge otherwise.
- **Schema complexity note**: `HassTurnOn`'s schema uses a plain
  `properties` object (matches the skeleton's `_schema_to_pydantic`),
  but `GetLiveContext`'s `domain` field uses `anyOf: [string, array]` —
  the skeleton's naive JSON-schema-to-pydantic mapper does **not**
  handle `anyOf` yet. Needs fixing before real use.
- **Confirmation-gate relevance confirmed for real**: `HassTurnOn`'s
  own description states it performs a lock action for locks — exactly
  the kind of tool that must sit behind a confirmation gate, not
  hypothetical.

Old findings below, from before the integration existed:

- Reachable on port 80 directly (not proxied) — confirmed genuine HA
  instance via `/manifest.json` and frontend HTML.
- Standard MCP Server integration paths all 404:
  - `/mcp_server/sse` → 404
  - `/api/mcp` → 404
  - `/mcp` → 404
- No HA long-lived access token available in this session to check the
  installed integrations list via `/api/`. Can't yet tell whether the
  "Model Context Protocol Server" integration is simply not
  installed/enabled, or exposed at a non-default path.
- **Next step**: check HA's Settings → Devices & Services for the MCP
  Server integration directly in the UI (or supply a long-lived token
  here), rather than guessing at more URL paths.

## 192.168.65.42

- Does not respond to ping, ARP entry is `INCOMPLETE` (no MAC learned).
  Nothing is currently answering on this address on this subnet.
  Andreas confirmed `.43` is the correct OVOS test instance instead.

## Net effect on this project's status

Nothing in `MCPToolBox` has been tested against a live MCP server yet,
and it currently can't be, because:

1. The MCP Server integration doesn't appear to be reachable on the
   available HA instance yet, and
2. `ovos-agentic-loop` itself isn't installed on the OVOS test instance,
   and installing it means opting the instance into alpha-tier
   dependencies.

Neither of those is a problem with this repo's code — they're
prerequisites that need sorting out (enable/find the HA MCP endpoint,
decide whether the OVOS test instance should run alpha deps) before a
real end-to-end test is possible.
