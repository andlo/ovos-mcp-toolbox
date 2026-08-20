"""
ovos_mcp_toolbox — WORK IN PROGRESS, see README.md.

Bridges MCP (Model Context Protocol) servers into ovos-agentic-loop's
ToolBox interface. Not functional yet — discover_tools() and the tool
handlers below are stubs pending live testing against ha-mcp.
"""
from typing import Any, Dict, List, Optional

from ovos_plugin_manager.templates.agent_tools import (
    AgentTool, ToolArguments, ToolOutput, ToolBox
)
from ovos_utils.log import LOG


class MCPServerConfig:
    """Plain config holder for one configured MCP server entry."""

    def __init__(self, name: str, transport: str = "sse",
                 url: Optional[str] = None, command: Optional[str] = None,
                 args: Optional[List[str]] = None, token: Optional[str] = None):
        self.name = name
        self.transport = transport
        self.url = url
        self.command = command
        self.args = args or []
        self.token = token


class MCPToolCallArgs(ToolArguments):
    """Generic passthrough args - a remote MCP tool's real schema is
    discovered at runtime, so this stays permissive for now.
    TODO: build a proper dynamic ToolArguments subclass per remote tool
    from its JSON schema instead of this placeholder."""
    model_config = {"extra": "allow"}


class MCPToolCallOutput(ToolOutput):
    result: str
    server: str
    tool: str
    is_error: bool = False


class MCPToolBox(ToolBox):
    """
    WORK IN PROGRESS. Do not use.

    Intended to bridge N configured MCP servers into ovos-agentic-loop.
    See README.md status section for what is and isn't implemented.
    """
    toolbox_id = "ovos-mcp-tools"

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 bus: Optional[Any] = None) -> None:
        self.config = config or {}
        self.servers = [
            MCPServerConfig(**s) for s in self.config.get("servers", [])
        ]
        self._sessions: Dict[str, Any] = {}
        super().__init__(toolbox_id=self.toolbox_id, config=config, bus=bus)


    def discover_tools(self) -> List[AgentTool]:
        """
        STUB. Not implemented yet.

        Intended behaviour: connect to each configured MCP server,
        call tools/list, map each remote tool to one AgentTool with
        a name prefixed by the server's short name (e.g. "ha:turn_on").
        A server that's unreachable should be skipped with a LOG.warning,
        not raise - see README "graceful degradation" status item.

        Returns [] until this is implemented so at least importing and
        instantiating the class doesn't explode.
        """
        if not self.servers:
            LOG.debug(f"{self.toolbox_id}: no MCP servers configured")
        else:
            LOG.warning(
                f"{self.toolbox_id}: discover_tools() is a stub, "
                f"{len(self.servers)} configured server(s) not yet queried"
            )
        return []

    def _call_remote_tool_stub(self, args: MCPToolCallArgs) -> MCPToolCallOutput:
        """Placeholder tool_call target - not wired to any AgentTool yet."""
        raise NotImplementedError(
            "MCPToolBox tool execution is not implemented yet"
        )
