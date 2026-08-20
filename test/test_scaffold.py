"""
Tests for MCPToolBox's opt-in policy-scaffold writing
(_write_policy_scaffold, triggered from discover_tools when
"scaffold_path" is set in config). Uses a temp file, no network.
"""
import json
from pathlib import Path

from ovos_mcp_toolbox import MCPToolBox


def test_scaffold_disabled_by_default(tmp_path):
    """No scaffold_path configured -> no file written, even if
    discover_tools() runs (with no servers, so nothing to write anyway,
    but this documents the opt-in default explicitly)."""
    tb = MCPToolBox(config={})
    assert tb._scaffold_path is None


def test_scaffold_written_when_enabled(tmp_path):
    scaffold_file = tmp_path / "scaffold.json"
    tb = MCPToolBox(config={"scaffold_path": str(scaffold_file)})
    tb._write_policy_scaffold("ha", [
        {"name": "GetDateTime", "description": "Provides the current date and time."},
        {"name": "HassTurnOn", "description": "Turns on/opens/presses a device."},
    ])
    assert scaffold_file.exists()
    data = json.loads(scaffold_file.read_text())
    assert "ha" in data
    names = [t["name"] for t in data["ha"]["tools"]]
    assert names == ["GetDateTime", "HassTurnOn"]
    assert data["ha"]["paste_into_persona_json_policy"]["ha__default_confirm"] is True


def test_scaffold_merges_does_not_clobber_other_servers(tmp_path):
    """A server that's temporarily unreachable shouldn't lose its
    previously-written scaffold entry when a DIFFERENT server's entry
    gets updated."""
    scaffold_file = tmp_path / "scaffold.json"
    tb = MCPToolBox(config={"scaffold_path": str(scaffold_file)})

    tb._write_policy_scaffold("ha", [{"name": "GetDateTime", "description": ""}])
    tb._write_policy_scaffold("dc", [{"name": "read_file", "description": ""}])

    data = json.loads(scaffold_file.read_text())
    assert "ha" in data and "dc" in data
    assert data["ha"]["tools"][0]["name"] == "GetDateTime"
    assert data["dc"]["tools"][0]["name"] == "read_file"


def test_scaffold_write_failure_is_non_fatal(tmp_path):
    """Pointing at an unwritable path shouldn't raise - see the
    try/except in _write_policy_scaffold."""
    bad_path = tmp_path / "no_such_dir" / "sub" / "scaffold.json"
    tb = MCPToolBox(config={"scaffold_path": str(bad_path)})
    # Simulate a directory creation failure by pointing at a path
    # component that's actually a file, not a directory.
    (tmp_path / "no_such_dir").write_text("I'm a file, not a directory")
    tb._write_policy_scaffold("ha", [{"name": "X", "description": ""}])
    # Should not raise - that's the whole point of this test.
