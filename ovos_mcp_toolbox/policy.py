"""
ovos_mcp_toolbox/policy.py — WORK IN PROGRESS, see README.md.

Generic, per-MCP-server confirmation policy for MCPToolBox.

Deliberately server-agnostic: the ONLY thing every MCP server's
tools/list response is guaranteed to give us is a flat list of tool
`name` strings (per the MCP spec). There is no shared ontology across
servers to build a policy on top of - a Home Assistant server has
"domains" (light, lock, cover...), but that concept means nothing to a
filesystem MCP server or a Desktop Commander MCP server.

MCP tool `annotations` (readOnlyHint/destructiveHint, part of the MCP
spec) would have been the "proper", protocol-native signal - checked
against a live HA response (TESTING_LOG.md) and HA does not send them
(all `annotations: null`), so nothing to build on there either.

DELIBERATELY NOT stored in OVOS skill settings. An earlier version of
this file did exactly that (a companion OVOSSkill owning settings.json,
MCPToolBox reading the same file via json_database.JsonStorage) - see
TESTING_LOG.md for why that was abandoned: it silently assumed
MCPToolBox and ovos-core's skill manager share a filesystem, which only
holds if the persona runs inside ovos-core itself. A standalone
ovos-persona-server on a different host would have its MCPToolBox
reading a file no skill ever writes to. This toolbox has to work
regardless of where the persona actually runs, so the policy now lives
in MCPToolBox's OWN config - the same persona-JSON dict every other
ovos-agentic-loop toolbox (ShellToolBox's allow_shell,
FileSystemToolBox's allow_write, ...) already uses. No new
infrastructure, no topology assumption, matches the rest of the
ecosystem's convention.

Policy model, per configured server (grouped by the server's own
`name` from its config entry, e.g. "ha", "dc" - so multiple servers,
even two of the same underlying product, each get independent policy),
inside MCPToolBox's config under the "policy" key:

  {
    "policy": {
      "ha__default_confirm": true,
      "ha__always_confirm": "HassBroadcast",
      "ha__never_confirm": "GetDateTime,GetLiveContext"
    }
  }

  {server}__default_confirm   bool, default True (unknown tool = confirm)
  {server}__always_confirm    comma-separated tool names - confirm
                               these regardless of the default
  {server}__never_confirm     comma-separated tool names - never
                               confirm these regardless of the default

Two explicit override lists (rather than one list whose meaning flips
depending on the default) so a setting always means the same thing no
matter how default_confirm is set.

A user won't know what to write here without first seeing what tool
names a server actually exposes - see policy_scaffold.py (standalone
CLI) and MCPToolBox's own auto-written scaffold file (discover_tools(),
gated by the "scaffold_path" config key) for how that gets solved.

NOT YET WIRED to actually block execution and pause for a human answer
- see README "Confirmation gate" status. What exists here is
*classification* (does this call need confirmation). Enforcement in
__init__.py's _make_tool_call currently refuses (does not silently
allow) any call this classifies as needing confirmation, since the
pause-and-ask mechanism itself doesn't exist yet.
"""
from typing import Any, Dict, List, Optional


def _split_names(raw: str) -> List[str]:
    return [n.strip() for n in raw.split(",") if n.strip()]


class MCPExposurePolicy:
    """
    Answers one question: ``requires_confirmation(server_name, tool_name)
    -> bool``. Server-agnostic by construction - only ever looks at tool
    name strings, never at any server-specific schema concept.

    Takes a plain dict (MCPToolBox's own config["policy"]), not a file
    path - policy lives and travels with the toolbox's own config,
    wherever that config comes from.
    """

    def __init__(self, raw: Optional[Dict[str, Any]] = None):
        self._raw: Dict[str, Any] = raw or {}

    def requires_confirmation(self, server_name: str, tool_name: str) -> bool:
        default = self._raw.get(f"{server_name}__default_confirm", True)
        always = _split_names(self._raw.get(f"{server_name}__always_confirm", ""))
        never = _split_names(self._raw.get(f"{server_name}__never_confirm", ""))

        if tool_name in always:
            return True
        if tool_name in never:
            return False
        return bool(default)
