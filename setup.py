from setuptools import setup, find_packages
from ovos_mcp_toolbox.version import VERSION_MAJOR, VERSION_MINOR, VERSION_BUILD

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="ovos-mcp-toolbox",
    version=f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}",
    description="WORK IN PROGRESS - MCP bridge toolbox for ovos-agentic-loop. Not functional yet.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/andlo/ovos-mcp-toolbox",
    author="Andreas Lorensen",
    author_email="andlo@outlook.dk",
    license="Apache-2.0",
    packages=find_packages(include=["ovos_mcp_toolbox*"]),
    install_requires=[
        "ovos-plugin-manager",
        "ovos-agentic-loop",
        "requests",
    ],
    entry_points={
        "opm.agents.toolbox": [
            "ovos-mcp-tools = ovos_mcp_toolbox:MCPToolBox"
        ]
    },
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
    ],
)
