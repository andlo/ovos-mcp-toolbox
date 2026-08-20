"""
Working end-to-end example: LLM brain + MCPToolBox + live MCP server.

Verified working 2026-08-20 - see TESTING_LOG.md for the full write-up,
including two real bugs (one upstream in ovos-agentic-loop, one a silent
config gotcha in ovos-openai-plugin) that had to be worked around to get
this to run. Both workarounds are baked into this example - read the
comments, they matter.

Requires (in an isolated venv, NOT the live OVOS instance's venv):
    pip install --pre ovos-agentic-loop ovos-openai-plugin
    pip install -e .   # this repo

Usage:
    export MCP_URL="http://<ha-host>/api/mcp"
    export MCP_TOKEN="<long-lived access token>"
    python examples/live_ha_demo.py "What is the current date and time?"
"""
import os
import sys

from ovos_agentic_loop.react import ReActLoopEngine
from ovos_openai_plugin.chat import OpenAIChatEngine
from ovos_plugin_manager.templates.agents import AgentMessage, MessageRole

from ovos_mcp_toolbox import MCPToolBox


def build_engine(mcp_url: str, mcp_token: str) -> ReActLoopEngine:
    brain = OpenAIChatEngine(config={
        # Public OVOS community demo endpoint - "no uptime guaranteed",
        # see README. Swap for a self-hosted Ollama for anything real.
        "api_url": "https://ollama.uoi.io/v1",
        "model": "qwen3:8b",
        # REQUIRED. Without this, OpenAIChatEngine silently strips every
        # system message (default allow_system=False) before sending -
        # which means the LLM never sees the ReAct instructions or the
        # tool list at all, and just answers as a plain chatbot with no
        # error or warning. See TESTING_LOG.md "Bug 2".
        "allow_system_prompts": True,
    })

    # REQUIRED workaround. Passing {"brain": "ovos-chat-openai-plugin"}
    # in the engine config does NOT work with the currently-published
    # ovos-agentic-loop==0.2.3a1 + ovos-plugin-manager==2.11.1a2 combo -
    # _load_brain() calls load_chat_plugin() with a `config` kwarg that
    # plugin-manager's version of that function doesn't accept. Fails
    # silently (caught, logged as a warning, brain ends up None). See
    # TESTING_LOG.md "Bug 1". Instantiate the brain yourself instead.
    engine = ReActLoopEngine({"max_iterations": 6})
    engine.set_brain(brain)

    toolbox = MCPToolBox(config={"servers": [
        {"name": "ha", "transport": "http", "url": mcp_url, "token": mcp_token}
    ]})
    engine.load_toolboxes([toolbox])
    return engine


def main() -> None:
    mcp_url = os.environ.get("MCP_URL")
    mcp_token = os.environ.get("MCP_TOKEN")
    if not mcp_url or not mcp_token:
        print("Set MCP_URL and MCP_TOKEN environment variables first.", file=sys.stderr)
        sys.exit(1)

    question = " ".join(sys.argv[1:]) or "What is the current date and time?"
    engine = build_engine(mcp_url, mcp_token)
    response = engine.continue_chat([AgentMessage(role=MessageRole.USER, content=question)])
    print(response.content)


if __name__ == "__main__":
    main()
