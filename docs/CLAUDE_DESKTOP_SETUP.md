# Connect to Claude Desktop (local MCP)

This is the easiest assistant connection for a personal Windows computer. Claude Desktop starts the MCP server as a local child process. You do not need to host a website or open a port.

## 1. Install the project with MCP support

Open PowerShell in the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[mcp]"
```

The `[mcp]` extra installs the official MCP Python SDK and its command-line developer tools. The ordinary `issue-triage` command does not need this extra.

## 2. Find the Python executable

While the virtual environment is active, run:

```powershell
python -c "import sys; print(sys.executable)"
```

Copy the complete path printed. It will look similar to:

```text
C:\Users\YOUR_WINDOWS_USER\Projects\issue-triage-agent\.venv\Scripts\python.exe
```

Use your actual path. Do not copy the example path literally.

## 3. Open Claude Desktop's MCP configuration

Claude Desktop's local MCP settings can be managed in its Extensions / Developer settings. For a manual stdio configuration, open the Claude Desktop configuration file. On Windows, the common location is:

```text
%APPDATA%\Claude\claude_desktop_config.json
```

If the file does not exist, create the `Claude` folder and the file. Close Claude Desktop before editing, then reopen it after saving.

Add this entry. Replace the Python path with the path you copied:

```json
{
  "mcpServers": {
    "issue-triage-agent": {
      "command": "C:\\Users\\YOUR_WINDOWS_USER\\Projects\\issue-triage-agent\\.venv\\Scripts\\python.exe",
      "args": ["-m", "issue_triage_agent.mcp_server"]
    }
  }
}
```

If the file already has an `mcpServers` object, add only the `issue-triage-agent` entry inside it. Do not delete other server entries. JSON does not allow comments or trailing commas.

## 4. Optional: private repositories

Public repositories can be analysed without a token for small runs. For private repositories, create a fine-grained GitHub token limited to the required repository and **read-only Issues** permission. Set `GITHUB_TOKEN` in the `env` object:

```json
{
  "mcpServers": {
    "issue-triage-agent": {
      "command": "C:\\Users\\YOUR_WINDOWS_USER\\Projects\\issue-triage-agent\\.venv\\Scripts\\python.exe",
      "args": ["-m", "issue_triage_agent.mcp_server"],
      "env": {
        "GITHUB_TOKEN": "YOUR_FINE_GRAINED_READ_ONLY_TOKEN"
      }
    }
  }
}
```

This places the token in a local configuration file as plain text. Do not share that file, commit it, upload it, or paste it into a chat. Use the narrowest possible token permissions. If you do not need private repositories, leave the token out.

## 5. Restart and verify

1. Save the JSON file.
2. Fully quit Claude Desktop; closing only the window may leave it running in the background.
3. Start Claude Desktop again.
4. Open the tools / connectors picker in a conversation.
5. Find `issue-triage-agent` and check that these tools appear:
   - `triage_github_repository`
   - `triage_issue_text`
   - `explain_triage_rules`

Ask Claude:

> Use issue-triage-agent to analyse the 30 most recent open issues in `pallets/flask`. Summarise categories, provisional priorities, incomplete reports and possible duplicates. Do not make changes to GitHub.

The server is intentionally read-only. A successful connection does not give Claude permission to edit GitHub issues.

## 6. Troubleshooting Claude Desktop

- **No tools appear:** confirm Claude Desktop was fully restarted, the JSON syntax is valid, and the `command` path points to the virtual environment's Python executable.
- **Module not found:** activate the same virtual environment and run `python -m pip install -e ".[mcp]"` again. Confirm `python -c "import issue_triage_agent"` works in that environment.
- **MCP package missing:** check `python -m pip show mcp`. Install the `[mcp]` extra if it is absent.
- **A private repository returns 404:** GitHub can hide private repositories from tokens that lack access. Confirm the token can read Issues for that exact repository.
- **GitHub rate limit:** set a fine-grained read-only token. Do not request write permissions.
- **Server starts and immediately exits:** inspect the Claude Desktop MCP logs. Run `python -m issue_triage_agent.mcp_server` in a terminal to check for a Python import error; when run normally over stdio, a healthy server waits quietly for the host.

For current host UI labels and the newer one-click Desktop Extensions flow, use Anthropic's official guide: <https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop>.
