"""
Minimal smoke tests. WORK IN PROGRESS - these only check the plugin
loads and honours the ToolBox contract at the shape level. They do
NOT test against a real MCP server yet.
"""
import pytest
from ovos_mcp_toolbox import MCPToolBox


def test_instantiates_with_no_config():
    tb = MCPToolBox(config=None)
    assert tb.toolbox_id == "ovos-mcp-tools"
    assert tb.servers == []


def test_discover_tools_empty_when_unconfigured():
    tb = MCPToolBox(config={})
    assert tb.discover_tools() == []


def test_discover_tools_is_idempotent():
    """ToolBox.discover_tools() contract requires idempotency."""
    tb = MCPToolBox(config={"servers": [{"name": "fake", "url": "http://x"}]})
    first = tb.discover_tools()
    second = tb.discover_tools()
    assert first == second


@pytest.mark.skip(reason="not implemented yet - needs a running MCP server")
def test_discover_tools_against_live_server():
    pass
