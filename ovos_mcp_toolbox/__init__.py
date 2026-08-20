"""
ovos_mcp_toolbox — WORK IN PROGRESS, see README.md and TESTING_LOG.md.

Bridges MCP (Model Context Protocol) servers into ovos-agentic-loop's
ToolBox interface.

Status as of 2026-08-20: discover_tools() and tool execution are
implemented for the Streamable HTTP transport (plain JSON-RPC over
POST, as used by Home Assistant's built-in "Model Context Protocol
Server" integration) and manually verified end-to-end against a real
HA instance - see TESTING_LOG.md for the exact requests/responses.
NOT yet verified: stdio transport, a second simultaneous MCP server,
the confirmation gate, or running inside an actual ovos-agentic-loop
ReActLoopEngine (only tested by calling discover_tools()/tool_call
directly in a script, not through the full loop).
"""
import itertools
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

import requests
from pydantic import create_model
from ovos_plugin_manager.templates.agent_tools import (
    AgentTool, ToolArguments, ToolOutput, ToolBox
)
from ovos_utils.log import LOG

from .policy import MCPExposurePolicy

# Confirmed by hand against a live HA MCP endpoint (see TESTING_LOG.md):
# Accept must list both, or HA returns 400 "Client must accept application/json"
_MCP_ACCEPT_HEADER = "application/json, text/event-stream"


class MCPServerConfig:
    """Plain config holder for one configured MCP server entry.

    transport="http" is the only one implemented so far (verified
    against HA's Streamable HTTP endpoint). "stdio" is accepted here
    but NOT implemented yet - see README status table.
    """

    def __init__(self, name: str, transport: str = "http",
                 url: Optional[str] = None, command: Optional[str] = None,
                 args: Optional[List[str]] = None, token: Optional[str] = None):
        self.name = name
        self.transport = transport
        self.url = url
        self.command = command
        self.args = args or []
        self.token = token


class MCPHTTPClient:
    """
    Minimal synchronous JSON-RPC client for the MCP Streamable HTTP
    transport. Deliberately NOT using the official `mcp` python SDK's
    async client here - that SDK is built around asyncio context
    managers, which is awkward to call from ToolBox's synchronous
    tool_call contract. Plain `requests` + JSON-RPC is simpler and is
    exactly what was hand-verified in TESTING_LOG.md.

    One instance per configured server. Not thread-safe. Does not yet
    implement session resumption, notifications, or SSE streaming
    responses - only the single-request/single-response JSON path
    that HA's integration returns for initialize/tools/list/tools/call.
    """

    def __init__(self, server: MCPServerConfig, timeout: float = 10.0):
        self.server = server
        self.timeout = timeout
        self._id_counter = itertools.count(1)
        self._initialized = False

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": _MCP_ACCEPT_HEADER,
        }
        if self.server.token:
            headers["Authorization"] = f"Bearer {self.server.token}"
        return headers

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": next(self._id_counter),
        }
        if params is not None:
            payload["params"] = params
        resp = requests.post(
            self.server.url, json=payload, headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP server '{self.server.name}' returned error: {data['error']}")
        return data.get("result", {})

    def initialize(self) -> Dict[str, Any]:
        result = self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ovos-mcp-toolbox", "version": "0.0.1"},
        })
        self._initialized = True
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        if not self._initialized:
            self.initialize()
        return self._rpc("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if not self._initialized:
            self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        parts = [
            block.get("text", "")
            for block in result.get("content", [])
            if block.get("type") == "text"
        ]
        text = "\n".join(parts)
        if result.get("isError"):
            raise RuntimeError(text or f"tool '{name}' reported isError=true")
        return text


_JSON_TYPE_MAP = {
    "string": str, "integer": int, "number": float, "boolean": bool,
}


def _slugify(name: str) -> str:
    """Match ovos-agentic-loop's own SkillMDToolBox convention
    (toolbox.py:12): lower-case, non-alphanumeric -> underscore."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _json_schema_field_type(prop_schema: Dict[str, Any]) -> Any:
    """
    Best-effort JSON-schema-property -> Python type mapping.

    Handles plain {"type": "..."} and {"type": "array", "items": {...}}
    (both seen on the live HA endpoint, e.g. HassTurnOn's `domain`).

    Also handles {"anyOf": [...]} by building a real typing.Union of
    every alternative - NOT by picking the first one. An earlier
    version of this function picked only the first anyOf alternative,
    which passed a naive test but failed for real: HA's
    GetLiveContext.domain is `anyOf: [string, array-of-string]`, and
    picking "string" first meant calling it with a list of domains
    (a perfectly valid call per HA's own schema) raised a pydantic
    ValidationError. Caught by testing an actual list-valued call
    against the live server, not by reading the schema - see
    TESTING_LOG.md. Falls back to `Any` for anything unrecognised
    (nested objects, etc.) rather than guessing wrong and rejecting
    valid LLM-provided arguments.
    """
    if "anyOf" in prop_schema:
        alt_types = tuple(_json_schema_field_type(a) for a in prop_schema["anyOf"])
        alt_types = tuple(dict.fromkeys(alt_types))  # dedupe, preserve order
        if len(alt_types) == 1:
            return alt_types[0]
        return Union[alt_types]
    json_type = prop_schema.get("type")
    if json_type == "array":
        item_type = _json_schema_field_type(prop_schema.get("items", {}))
        return List[item_type]
    return _JSON_TYPE_MAP.get(json_type, Any)


def _build_args_model(tool_name: str, input_schema: Dict[str, Any]) -> Type[ToolArguments]:
    """Build a ToolArguments subclass from a remote tool's JSON schema.

    Verified against real schemas from HA's MCP endpoint (see
    TESTING_LOG.md) for both the plain-`properties` shape (HassTurnOn)
    and the `anyOf`-field shape (GetLiveContext.domain).
    """
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    fields: Dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        py_type = _json_schema_field_type(prop_schema)
        default = ... if prop_name in required else None
        fields[prop_name] = (Optional[py_type] if default is None else py_type, default)
    model_name = f"{_slugify(tool_name)}_Args"
    return create_model(model_name, __base__=ToolArguments, **fields)


class MCPToolCallOutput(ToolOutput):
    result: str
    server: str
    tool: str
    is_error: bool = False


class MCPToolBox(ToolBox):
    """
    WORK IN PROGRESS - see README.md status table before using this
    anywhere near a real ovos-agentic-loop persona.

    Bridges N configured MCP servers into ovos-agentic-loop's ToolBox
    interface. HTTP transport is implemented and hand-verified against
    a live Home Assistant MCP endpoint (TESTING_LOG.md), including
    side-effect tools (HassTurnOn/Off) with a real LLM through the full
    ReActLoopEngine loop.

    Confirmation gate (policy.py): a per-server, per-tool-name policy
    (never based on any server-specific concept like HA's "domains" -
    the only thing every MCP server gives us is a flat tool name list)
    decides whether a call needs confirmation. Policy lives directly in
    this toolbox's OWN config, under the "policy" key - see policy.py's
    docstring for why (short version: an earlier design shared a file
    with a companion OVOSSkill, which only works if the persona runs
    inside ovos-core itself and breaks for a standalone
    ovos-persona-server on another host - dropped for that reason).

    A user can't write a sensible policy without first seeing what tool
    names a server exposes - see policy_scaffold.py for a standalone
    CLI, and "scaffold_path" below for this toolbox writing the same
    kind of reference automatically as a side effect of normal use.

    IMPORTANT: there is no pause-and-ask mechanism yet - ReActLoopEngine
    is a synchronous, blocking call with no built-in way to pause
    mid-loop for a human answer (see README "Confirmation gate" status
    for the open design question). Until that exists, any call the
    policy flags as needing confirmation is REFUSED outright, not
    silently executed and not silently allowed - a clear error comes
    back to the LLM/loop instead of a real-world action. This is a
    deliberate fail-closed choice, not a stand-in implementation.
    """
    toolbox_id = "ovos-mcp-tools"

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 bus: Optional[Any] = None) -> None:
        self.config = config or {}
        self.servers = [
            MCPServerConfig(**s) for s in self.config.get("servers", [])
        ]
        self._clients: Dict[str, MCPHTTPClient] = {
            s.name: MCPHTTPClient(s) for s in self.servers if s.transport == "http"
        }
        self._policy = MCPExposurePolicy(self.config.get("policy", {}))
        # None (default) = scaffold-writing disabled. Set explicitly in
        # persona.json's toolbox config to opt in - never guess a
        # directory on the user's behalf. See _write_policy_scaffold.
        self._scaffold_path = self.config.get("scaffold_path")
        super().__init__(toolbox_id=self.toolbox_id, config=config, bus=bus)


    def discover_tools(self) -> List[AgentTool]:
        """
        Connects to each configured HTTP-transport MCP server, calls
        tools/list, and maps each remote tool to one AgentTool. Tool
        names are prefixed with the server's short name (e.g.
        "ha:HassTurnOn") to avoid collisions across servers.

        A server that's unreachable is skipped with a LOG.warning, not
        raised - satisfies the "graceful degradation" requirement.
        Idempotent per the ToolBox contract (re-running just re-queries
        and rebuilds the same list, modulo whatever changed remotely).

        stdio-transport servers in self.servers are currently skipped
        entirely (not implemented) - logged once per call so it's not
        silent.
        """
        agent_tools: List[AgentTool] = []
        stdio_servers = [s for s in self.servers if s.transport == "stdio"]
        if stdio_servers:
            LOG.warning(
                f"{self.toolbox_id}: stdio transport not implemented yet, "
                f"skipping {[s.name for s in stdio_servers]}"
            )

        for server in self.servers:
            client = self._clients.get(server.name)
            if client is None:
                continue  # non-http server, already warned above
            try:
                remote_tools = client.list_tools()
            except Exception as e:
                LOG.warning(f"{self.toolbox_id}: server '{server.name}' unreachable: {e}")
                continue

            if self._scaffold_path:
                self._write_policy_scaffold(server.name, remote_tools)

            for tool_def in remote_tools:
                remote_name = tool_def["name"]
                prefixed_name = f"{server.name}:{remote_name}"
                args_model = _build_args_model(prefixed_name, tool_def.get("inputSchema", {}))
                agent_tools.append(AgentTool(
                    name=_slugify(prefixed_name),
                    description=tool_def.get("description", ""),
                    argument_schema=args_model,
                    output_schema=MCPToolCallOutput,
                    tool_call=self._make_tool_call(server, remote_name),
                ))
        return agent_tools

    def _write_policy_scaffold(self, server_name: str, tools: List[Dict[str, Any]]) -> None:
        """
        Auto-updates a reference file at self._scaffold_path (opt-in via
        the "scaffold_path" config key - disabled unless explicitly
        set, see __init__) so the user can see what tool names actually
        exist on a server and copy them straight into persona.json's
        "policy" block, instead of guessing.

        Merges rather than overwrites the whole file, so a server that
        fails to connect on a later run doesn't lose its previously
        written entry (only the successfully-queried server's own
        section is replaced each call). Never touches persona.json
        itself - this is a separate, disposable reference file this
        toolbox fully owns.

        Best-effort: any failure here is logged, never raised - this is
        a convenience file, not something that should break tool
        discovery if e.g. the configured directory isn't writable.
        """
        try:
            path = Path(self._scaffold_path)
            existing: Dict[str, Any] = {}
            if path.exists():
                try:
                    existing = json.loads(path.read_text())
                except Exception:
                    existing = {}  # corrupt/foreign file - start fresh rather than crash

            existing[server_name] = {
                "tools": [
                    {"name": t["name"], "description": (t.get("description") or "")[:200]}
                    for t in tools
                ],
                "paste_into_persona_json_policy": {
                    f"{server_name}__default_confirm": True,
                    f"{server_name}__always_confirm": "",
                    f"{server_name}__never_confirm": "",
                },
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(existing, indent=2) + "\n")
        except Exception as e:
            LOG.debug(f"{self.toolbox_id}: could not write policy scaffold: {e}")

    def _make_tool_call(self, server: MCPServerConfig, remote_name: str):
        """Returns a closure matching the ToolCallFunc contract:
        accepts one instantiated ToolArguments, returns a ToolOutput.
        """
        def _call(args: ToolArguments) -> MCPToolCallOutput:
            # Fail-closed confirmation gate - see class docstring. No
            # pause-and-ask mechanism exists yet, so a call requiring
            # confirmation is refused, never silently run or silently
            # skipped past.
            if self._policy.requires_confirmation(server.name, remote_name):
                return MCPToolCallOutput(
                    result=(
                        f"Refused: '{remote_name}' on server '{server.name}' "
                        "requires confirmation, and no confirmation mechanism "
                        "is implemented yet. Add it to this server's "
                        "'never confirm' list in settings if you've verified "
                        "it's safe to auto-run, or wait for the confirmation "
                        "flow to be built."
                    ),
                    server=server.name, tool=remote_name, is_error=True,
                )

            client = self._clients[server.name]
            # Drop unset optional fields rather than sending explicit
            # nulls - some remote schemas may not expect a null for an
            # omitted optional field.
            arguments = {k: v for k, v in args.model_dump().items() if v is not None}
            try:
                text = client.call_tool(remote_name, arguments)
                return MCPToolCallOutput(
                    result=text, server=server.name, tool=remote_name, is_error=False,
                )
            except Exception as e:
                return MCPToolCallOutput(
                    result=str(e), server=server.name, tool=remote_name, is_error=True,
                )
        return _call
