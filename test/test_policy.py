"""
Tests for policy.py's confirmation-classification logic.

Policy is now plain config (a dict, matching MCPToolBox's own
config["policy"]) - no file I/O, no OVOS skill dependency. See
policy.py's module docstring for why the earlier file-sharing design
was abandoned (topology assumption that broke for a standalone
ovos-persona-server on a different host than ovos-core).
"""
from ovos_mcp_toolbox.policy import MCPExposurePolicy


def test_no_config_defaults_to_confirm():
    pol = MCPExposurePolicy()
    assert pol.requires_confirmation("ha", "AnyTool") is True


def test_never_confirm_overrides_default_true():
    pol = MCPExposurePolicy({
        "ha__default_confirm": True,
        "ha__never_confirm": "GetDateTime, GetLiveContext",
    })
    assert pol.requires_confirmation("ha", "GetDateTime") is False
    assert pol.requires_confirmation("ha", "GetLiveContext") is False
    assert pol.requires_confirmation("ha", "HassTurnOn") is True


def test_always_confirm_overrides_default_false():
    pol = MCPExposurePolicy({
        "ha__default_confirm": False,
        "ha__always_confirm": "HassBroadcast",
    })
    assert pol.requires_confirmation("ha", "HassBroadcast") is True
    assert pol.requires_confirmation("ha", "GetDateTime") is False


def test_policy_is_scoped_per_server():
    """Same tool name, two different servers - only 'ha's override applies."""
    pol = MCPExposurePolicy({
        "ha__default_confirm": True,
        "ha__never_confirm": "run_command",
        "dc__default_confirm": True,
        # dc has no never_confirm override for run_command
    })
    assert pol.requires_confirmation("ha", "run_command") is False
    assert pol.requires_confirmation("dc", "run_command") is True
