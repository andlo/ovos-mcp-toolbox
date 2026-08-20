"""
Minimal smoke tests. Fast unit tests need no network. Live tests
against a real MCP server are opt-in via env vars (never hardcode a
token here) and are skipped by default / in CI.
"""
import os
import pytest
from ovos_mcp_toolbox import MCPToolBox, _build_args_model, _slugify


def test_instantiates_with_no_config():
    tb = MCPToolBox(config=None)
    assert tb.toolbox_id == "ovos-mcp-tools"
    assert tb.servers == []


def test_discover_tools_empty_when_unconfigured():
    tb = MCPToolBox(config={})
    assert tb.discover_tools() == []


def test_slugify_matches_agentic_loop_convention():
    assert _slugify("ha:HassTurnOn") == "ha_hassturnon"
    assert _slugify("web-search") == "web_search"


def test_build_args_model_plain_properties():
    """Matches HassTurnOn's real schema shape from TESTING_LOG.md."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "domain": {"type": "array", "items": {"type": "string"}},
        },
    }
    model = _build_args_model("ha:HassTurnOn", schema)
    instance = model(name="kitchen light", domain=["light"])
    assert instance.name == "kitchen light"
    assert instance.domain == ["light"]


def test_build_args_model_anyof_accepts_both_alternatives():
    """
    Regression test for a real bug found while testing against live HA:
    GetLiveContext.domain is `anyOf: [string, array-of-string]`. An
    earlier version of _json_schema_field_type picked only the FIRST
    anyOf alternative, so passing a list raised a pydantic
    ValidationError even though HA's own schema allows it. Caught by
    calling the real endpoint with a list, not by reading the schema.
    See TESTING_LOG.md, 2026-08-20 entry, for the original failure.
    """
    schema = {
        "type": "object",
        "properties": {
            "domain": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ]
            },
        },
    }
    model = _build_args_model("ha:GetLiveContext", schema)
    assert model(domain="sun").domain == "sun"
    assert model(domain=["sun", "weather"]).domain == ["sun", "weather"]


_LIVE_URL = os.environ.get("OVOS_MCP_TEST_URL")
_LIVE_TOKEN = os.environ.get("OVOS_MCP_TEST_TOKEN")

requires_live_server = pytest.mark.skipif(
    not (_LIVE_URL and _LIVE_TOKEN),
    reason="set OVOS_MCP_TEST_URL and OVOS_MCP_TEST_TOKEN to run against a real MCP server",
)


@requires_live_server
def test_live_discover_tools_returns_real_tools():
    tb = MCPToolBox(config={"servers": [
        {"name": "ha", "transport": "http", "url": _LIVE_URL, "token": _LIVE_TOKEN}
    ]})
    tools = tb.discover_tools()
    assert len(tools) > 0
    names = [t.name for t in tools]
    assert len(names) == len(set(names)), "tool names must be unique"


@requires_live_server
def test_live_call_readonly_tool():
    tb = MCPToolBox(config={"servers": [
        {"name": "ha", "transport": "http", "url": _LIVE_URL, "token": _LIVE_TOKEN}
    ]})
    result = tb.call_tool("ha_getdatetime", {})
    assert result.is_error is False
    assert "date" in result.result
