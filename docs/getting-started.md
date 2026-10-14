# Getting Started

This guide takes you from a fresh Kali VM to an AI agent solving a CTF target
through Scylla.

## Prerequisites

- A Kali Linux VM (or compatible) reachable on an **isolated lab network**.
- Python 3.11+ on that VM.
- An MCP-capable client (for example, Open WebUI) that can send a bearer token.
- An LLM to drive the agent (Scylla was designed against Qwen 3, but any
  tool-capable model works).

## 1. Install dependencies

On the Kali VM:

```bash
pip install fastmcp
```

## 2. Provision an auth token

Scylla reads a single bearer token from `~/kali-mcp/token` and rejects any
request that does not present it.

```bash
mkdir -p ~/kali-mcp
head -c 32 /dev/urandom | base64 > ~/kali-mcp/token
cat ~/kali-mcp/token   # copy this into your MCP client
```

## 3. Review the bind address

By default the server binds the host-only lab interface:

```python
mcp.run(transport="http", host="192.168.56.101", port=8765, path="/mcp")
```

Adjust `host`/`port` in `mcp-server.py` to match your lab network before
launching. **Do not** bind a publicly reachable interface.

## 4. Launch Scylla

```bash
python mcp-server.py
```

The MCP endpoint is now available at:

```
http://<host>:8765/mcp
```

## 5. Wire up the agent

1. In your MCP client, add the endpoint above and supply the bearer token.
2. Load [`../SystemPrompt.md`](../SystemPrompt.md) as the agent's system prompt.
3. Give the agent a target that is inside your authorized lab scope — e.g.
   *"The target is 192.168.56.120. Find the flag."*

## 6. Working directory & artifacts

- Commands run in `~/lab-projects/first-assessment/`.
- Reports and checklists written by the agent land in that folder.
- Disposable-command history is logged to `~/kali-mcp/command-log.jsonl`.
- `export_evidence()` renders recent history into `evidence.md`.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `401` / auth errors | Token mismatch between client and `~/kali-mcp/token` |
| Terminal seems stuck | Call `reset_terminal()` for a fresh shell |
| File tool rejects a path | Path escaped the assessment root — use a relative path |
| No output from a command | Increase `wait_seconds`, or drain with `terminal_read()` |
