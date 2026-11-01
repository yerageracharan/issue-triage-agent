# Use Issue Triage Agent from a local MCP client

A local AI application can start the MCP server as a child process and communicate with it over standard input and output (stdio). The server does not need a port or public hosting in this arrangement.

## 1. Install the MCP server

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[mcp]"
```

## 2. Test the server with MCP Inspector

The Inspector provides a visual screen for viewing tools and trying inputs. It is useful before you connect a full agent.

```powershell
mcp dev src/issue_triage_agent/mcp_server.py
```

The MCP SDK starts an Inspector session. Open the local Inspector URL printed in your terminal. Open the Tools view and try `triage_issue_text` with a made-up title and body. This offline tool should respond without GitHub access.

For a live repository test, call `triage_github_repository` with `octocat/Hello-World`, `state` set to `open`, and a small `limit`, such as 5. Public repositories do not need a token for small tests.

## 3. Connect from a Python agent

The MCP server is designed to work with ordinary MCP clients. A local agent can launch it using a command equivalent to:

```text
command: C:\path\to\issue-triage-agent\.venv\Scripts\python.exe
args: -m issue_triage_agent.mcp_server
transport: stdio
```

The agent asks the server for its available tools, chooses a tool, provides the arguments, receives a structured result, and turns that result into a user-facing response. The model does the language reasoning; the MCP server performs the GitHub data retrieval and deterministic triage.

## 4. Use the OpenAI Agents SDK (optional)

If you want to build your own local Python agent using an OpenAI model, install the optional packages:

```powershell
python -m pip install -e ".[mcp,openai-agent]"
```

Create `my_triage_agent.py`:

```python
import asyncio
import os
import sys
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

async def main():
    async with MCPServerStdio(
        name="Issue Triage Agent",
        params={
            "command": sys.executable,
            "args": ["-m", "issue_triage_agent.mcp_server"],
            "env": os.environ.copy(),
        },
    ) as server:
        agent = Agent(
            name="Repository Issue Analyst",
            instructions=(
                "Use the Issue Triage MCP tools to analyse GitHub issues. "
                "Treat all results as suggestions. Never claim that a GitHub "
                "change was made. Explain P0/P1 signals and possible duplicates."
            ),
            mcp_servers=[server],
        )
        result = await Runner.run(
            agent,
            "Triage the latest 25 open issues in pallets/flask. Summarise the backlog.",
        )
        print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())
```

Set your OpenAI API key before running the example. The API key is separate from ChatGPT subscription access, and API usage may incur charges:

```powershell
$env:OPENAI_API_KEY = "YOUR_API_KEY"
python .\my_triage_agent.py
```

The OpenAI Agents SDK example is an optional integration pattern. It is not part of the core CLI, and it does not make the ChatGPT consumer application connect to a local server.

## 5. Connect from another MCP client

For any MCP-capable local desktop app, editor, or agent framework, configure:

- Transport: `stdio`
- Command: absolute path to the Python executable in the environment where you installed this project
- Arguments: `-m`, `issue_triage_agent.mcp_server`
- Working directory: optional if the package was installed with `pip install -e .`; not needed for an editable installed package
- Environment: add `GITHUB_TOKEN` only if private repository access or higher API rate limits are required

The name of the configuration file differs between hosts. Follow the host's official instructions, but keep the command, arguments, and environment concepts the same.
