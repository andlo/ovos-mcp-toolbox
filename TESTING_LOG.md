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


## Full end-to-end test: LLM brain + MCPToolBox + live HA (2026-08-20)

**First time the complete chain has worked**: a real LLM (via the public
demo Ollama, `qwen3:8b`) reasoned about a question, chose the correct
tool through `MCPToolBox`, called real Home Assistant over MCP, and
produced a correct natural-language answer from live data.

```
User: "What is the current date and time?"
Assistant: "The current date and time are August 20, 2026, at 19:28:25
(CEST). This corresponds to Thursday in the Central European Summer
Time zone."
```

Verified correct by comparing to wall-clock time at the moment of the
call - this is real data round-tripped through HA, not a hallucination.

### Two real bugs found and fixed to get here (not hypothetical, found by running the code)

**Bug 1 — `ReActLoopEngine._load_brain()` incompatible with installed `ovos-plugin-manager`.**
`ovos-agentic-loop==0.2.3a1`'s `_load_brain()` calls:
```python
load_chat_plugin(brain_id, config=self.config.get(brain_id, {}))
```
but the installed `ovos-plugin-manager==2.11.1a2`'s `load_chat_plugin()`
signature is `(module_name: str) -> Type[ChatEngine]` — it takes no
`config` arg and returns an *uninstantiated class*, not an instance.
Result: passing `"brain": "ovos-chat-openai-plugin"` in `ReActLoopEngine`
config always fails silently (caught by a bare `except Exception`,
logged as a `LOG.warning`, engine ends up with no brain at all).

This is a genuine version-skew bug between two alpha packages that are
both currently the latest on PyPI — not something fixable in this repo.
**Workaround**: instantiate the `ChatEngine` yourself and inject it via
the engine's `set_brain()` method instead of the `"brain"` config key:
```python
brain = OpenAIChatEngine(config={...})
engine = ReActLoopEngine({"max_iterations": 6})
engine.set_brain(brain)
```

**Bug 2 (config gotcha, not a code bug) — `allow_system_prompts` defaults to `False`.**
`OpenAIChatEngine.__init__` sets
`self.allow_system = self.config.get("allow_system_prompts") or False`.
`ReActLoopEngine`'s entire ReAct mechanism depends on injecting a
system message containing the tool schemas and instructions
(`_build_react_system`). With the default `allow_system=False`,
`validate_messages()` **silently strips every system message** before
the request is sent — the LLM never sees the tool list or ReAct
instructions at all, and just answers as a plain chatbot. No error,
no warning — the loop "worked" but the LLM was blind to every tool.

Diagnosed by: comparing a raw `curl` call with the exact same
15KB system prompt (which got a correct `Thought:/Action:` response)
against the same call through `OpenAIChatEngine.continue_chat()`
(which didn't) — then reading `validate_messages()`'s source to find
the silent strip.

**Fix**: explicitly set `"allow_system_prompts": true` in the brain's
config. Without this, `ovos-agentic-loop`'s ReAct pattern cannot work
with `ovos-chat-openai-plugin` at all, and there's nothing in the docs
of either package (as of 2026-08-20) that flags this interaction.

### Also confirmed working correctly (not a bug)

- `OpenAIChatEngine`'s `api_url` config must be the base URL (e.g.
  `https://ollama.uoi.io/v1`), not the full completions path — the
  plugin appends `/chat/completions` itself. Passing the full path
  produces a 404 on a doubled path.
- The public demo endpoints (`https://ollama.uoi.io/v1`,
  `https://llama.smartgic.io/v1` — both referenced as example URLs in
  OVOS's own package READMEs) were both reachable and responsive at
  test time, serving identical model lists (likely same backend).
  `qwen3:8b` reliably produces correctly-formatted ReAct output
  (`Thought:`/`Action:`/`Action Input:`) once it actually receives the
  system prompt.

### Full working example (isolated venv, NOT run on the live OVOS instance)

```python
from ovos_agentic_loop.react import ReActLoopEngine
from ovos_plugin_manager.templates.agents import AgentMessage, MessageRole
from ovos_openai_plugin.chat import OpenAIChatEngine
from ovos_mcp_toolbox import MCPToolBox

brain = OpenAIChatEngine(config={
    "api_url": "https://ollama.uoi.io/v1",
    "model": "qwen3:8b",
    "allow_system_prompts": True,  # required, see Bug 2 above
})

engine = ReActLoopEngine({"max_iterations": 6})
engine.set_brain(brain)  # required, see Bug 1 above - "brain" config key doesn't work

toolbox = MCPToolBox(config={"servers": [
    {"name": "ha", "transport": "http",
     "url": "http://192.168.65.186/api/mcp", "token": "<long-lived token>"}
]})
engine.load_toolboxes([toolbox])

response = engine.continue_chat([
    AgentMessage(role=MessageRole.USER, content="What is the current date and time?")
])
print(response.content)
```

Run entirely from an isolated venv (`/tmp/mcp_probe`), not the live
OVOS instance's pinned venv on `.43` - the alpha-dependency decision
for the production instance is still open, unaffected by this test.

### Still not tested / known gaps after this milestone

- Only tested with a read-only, no-argument tool (`GetDateTime`).
  Have NOT tested a full loop run that picks a side-effect tool like
  `HassTurnOn` - there is still no confirmation gate, so this is a real
  risk, not a hypothetical one, the moment a persona is pointed at
  entities that matter.
- Only one demo Ollama call cycle tested; model behaviour with a public,
  shared, unthrottled demo server under repeated/concurrent use is
  unknown — no rate limits observed, but not stress-tested either.
- `qwen3:8b`'s ReAct-format reliability was observed over a handful of
  calls, not systematically. Small/cheaper models may follow the
  format less reliably; not tested.
- Multi-tool reasoning (a question requiring 2+ sequential tool calls)
  not tested — only single-tool-call happy path so far.


## Side-effect tools tested for the first time (2026-08-20, continued)

Created two safe virtual `input_boolean` helpers on the live HA test
instance specifically for this: `input_boolean.mcp_test_lamp` and
`input_boolean.mcp_test_fan` (via the HA UI - no REST/API path exists
for helper creation, see below). Neither controls anything real.

### Helper creation - no working programmatic path found

Tried three ways to create helpers via API before falling back to the
UI:
1. `PUT /api/config/input_boolean/config/<id>` (legacy editable-YAML
   REST endpoint) → `404 Not Found`. Appears removed in this HA version.
2. `POST /api/config/config_entries/flow` with
   `{"handler": "input_boolean", ...}` → `404 {"message":"Invalid
   handler specified"}`. Modern HA creates helpers via a WebSocket-only
   flow, not this REST endpoint.
3. A Claude-side `ha-mcp` connector tool (`ha_config_set_helper`)
   exists and could do this - but turned out to be pointed at a
   **different** HA instance, not this test instance. Confirmed by
   comparing `/api/config` on both: same `location_name` ("Hjem") and
   `time_zone`, but **different HA core version** (test instance
   `2026.8.1` vs the other instance `2026.8.2`) - different versions
   queried moments apart rules out same-instance. Did not use that
   connector here to avoid touching the wrong installation.

**Conclusion**: helper creation on this HA version requires either the
UI or the WebSocket API - no simple REST path exists. Andreas created
both helpers manually via Settings → Devices & Services → Helpers.

### Exposure to Assist also has no REST path

`POST /api/services/homeassistant/expose_entity` → `400 Bad Request`.
Checked `/api/services` - no `expose_entity` service is registered at
all. Voice-assistant exposure is a WebSocket-only command
(`homeassistant/expose_entity`), not a callable service. Andreas set
this manually via Settings → Voice assistants → Expose.

Once exposed, `ha_getlivecontext` with `domain: "input_boolean"` found
both correctly. Note: filtering by `name: "MCP Test"` (partial/multi-word)
returned "No exposed entities matched" even though both entities exist
and are exposed - the `name` filter's matching behaviour is stricter or
different than expected; `domain` filtering is more reliable for
verification purposes.

### Test 1: direct tool call, state verified independently

```
Before: GET /api/states/input_boolean.mcp_test_lamp -> "off"
tb.call_tool("ha_hassturnon", {"name": "MCP Test Lamp"})
  -> {"speech": {}, "response_type": "action_done",
      "data": {"success": [{"name": "MCP Test Lamp", "type": "entity",
                             "id": "input_boolean.mcp_test_lamp"}],
                "failed": []}}
After:  GET /api/states/input_boolean.mcp_test_lamp -> "on"
```
State change verified via a separate, direct `/api/states` GET call -
not just trusting the tool's own "success" response.

### Test 2: full natural-language loop, picking correctly between two similarly-named entities

```
$ python examples/live_ha_demo.py "Turn off the MCP Test Lamp"
The MCP Test Lamp is now turned off.

$ python examples/live_ha_demo.py "Turn on the MCP Test Fan"
The fan is now activated.
```
Independently verified via `/api/states`:
- `input_boolean.mcp_test_lamp` -> `off` (correct)
- `input_boolean.mcp_test_fan` -> `on` (correct)

This is the first test where the LLM had to disambiguate between two
targets with near-identical names ("MCP Test Lamp" vs "MCP Test Fan")
and pick the one actually named in the request - it did so correctly
both times, with no confusion between the two.

### What this milestone does and doesn't prove

Proves: `MCPToolBox` correctly passes through side-effect tool calls,
`ReActLoopEngine` + the demo LLM correctly disambiguate between similar
entities, and the whole chain reliably produces the intended real-world
state change.

Does NOT prove: safety. There is still no confirmation gate. This test
used harmless virtual helpers specifically so that a wrong tool choice
or a hallucinated entity name would have zero real consequence. The
same mechanism, pointed at `HassTurnOn` for a real lock or real
appliance, would execute immediately and without confirmation. Building
the confirmation gate is the next real priority, not further
capability testing.
