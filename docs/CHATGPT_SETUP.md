# Connect to ChatGPT

ChatGPT's custom MCP connection is different from Claude Desktop's local-process connection. This distinction matters: **ChatGPT does not connect directly to a server that is only listening on `localhost` on your computer.** It needs a remote MCP endpoint reachable by ChatGPT, or a supported Secure MCP Tunnel.

## Before you start: check account availability

Custom MCP support in ChatGPT depends on account type, workspace policy, and product rollout. OpenAI's current Help Center documentation describes custom MCP server connections, remote HTTPS endpoints, and Secure MCP Tunnel. It also documents plan differences: full MCP functionality is currently available for Business, Enterprise, and Edu workspaces, while Pro supports read/fetch access in developer mode. The documentation does not promise the feature for every consumer plan. Check the current Plugins / Apps settings in your own ChatGPT account before deploying anything.

Official guide: <https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt>.

## Option A: use a supported Secure MCP Tunnel

This is the route to consider when you want to keep the Python process on your own computer rather than deploy a public server.

1. Install the project and MCP extra as described in the main README.
2. Run the server using the HTTP transport on loopback:

   ```powershell
   issue-triage-mcp --transport streamable-http --host 127.0.0.1 --port 8000
   ```

3. Confirm that the server is running locally. The MCP endpoint is `/mcp`, so the local address is `http://127.0.0.1:8000/mcp`.
4. In ChatGPT, open the custom MCP server connection flow, choose the Tunnel option if it is available, and follow the product's current instructions to associate a Secure MCP Tunnel with your local server.
5. Complete the authentication and risk-review steps shown by ChatGPT.
6. Ask ChatGPT to inspect a small public repository first, then inspect its returned categories and suggested priorities.

The tunnel feature is controlled by ChatGPT and may not be available on every account. This repository does not create, register, or manage a Secure MCP Tunnel for you.

## Option B: deploy a remote MCP endpoint

If you operate a server and understand network security, you can host the Streamable HTTP transport on infrastructure reachable over HTTPS. The MCP endpoint path is `/mcp`.

**Do not put this server directly on the public internet as-is.** The starter server does not implement user authentication, OAuth, account-level access control, request quotas, or a production secrets manager. Before public deployment, put it behind an authentication layer that ChatGPT supports, terminate HTTPS, restrict who can connect, keep GitHub tokens out of source control, and monitor access. Use a dedicated read-only GitHub token with access only to the intended repositories.

A production deployment should include, at minimum:

- HTTPS with a valid certificate.
- Authentication suitable for the selected ChatGPT custom MCP connection flow.
- A dedicated least-privilege GitHub token.
- Secret storage outside the repository and container image.
- Request and rate limits.
- Logs that exclude access tokens and issue-body secrets.
- A review of what repository issue content is sent to the model.

The local launch command below is only a way to test the HTTP transport. It is not a production deployment recipe:

```bash
issue-triage-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

When using a real hosted environment, follow the hosting provider's process model, health checks, TLS, secrets, and authentication documentation. Set the MCP URL in ChatGPT to the final secure HTTPS endpoint supplied by that environment.

## What to ask ChatGPT after connecting

> Use `triage_github_repository` on `owner/repository`, inspect the latest 40 open issues, and return a table grouped by category and priority. Explain each P0 or P1 signal, list missing report details, and separate possible duplicates from confirmed facts. Do not change GitHub.

## If custom MCP is unavailable in your ChatGPT account

You can still use the same MCP server from Claude Desktop or another local MCP host, and you can use the CLI directly. You can also build a separate local application with the OpenAI Agents SDK and connect it to the MCP server over stdio. That uses the OpenAI API and is not the same thing as attaching an MCP server to the ChatGPT consumer chat interface.
