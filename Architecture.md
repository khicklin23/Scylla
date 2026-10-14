# Architecture

> A look at how Scylla was put together — the pieces, where each one runs, and
> why the boundaries fall where they do. This is a debrief, not a manual.

Scylla's whole idea is a single controlled strait between a reasoning model and
a live Kali box. The interesting part isn't any one component — it's the
**topology**: what runs on the host, what runs inside the VM, and the one thin
channel that crosses between them.

---

## The topology at a glance

Everything lives on one physical machine, but split across a virtualization
boundary. The model stays on the host. Kali — and the MCP server inside it —
lives in a VM. They talk over a host-only network.

```
╔══════════════════════════════════════════════════════════════════════╗
║  🖥️  HOST MACHINE  (local)                                             ║
║                                                                        ║
║   ┌────────────────────────────┐                                      ║
║   │  🧠  Qwen 3  — local model  │                                      ║
║   │      + MCP client           │                                      ║
║   │                             │                                      ║
║   │  "Inspect the target's      │                                      ║
║   │   exposed services."        │                                      ║
║   └──────────────┬──────────────┘                                      ║
║                  │                                                     ║
║                  │  MCP over HTTP + bearer token                       ║
║                  │  →  192.168.56.101:8765/mcp                         ║
║                  │                                                     ║
║   ░░░░░░░░░░░░░░░░│░░░░░░░░ host-only network (192.168.56.0/24) ░░░░░░  ║
║                  │                                                     ║
║   ╭──────────────▼──────────────────────────────────────────────╮    ║
║   │  💠  KALI VM   (guest, isolated, disposable)                  │    ║
║   │                                                              │    ║
║   │    ┌────────────────────────────┐                           │    ║
║   │    │  ⚙️  SCYLLA MCP SERVER      │   ← the strait            │    ║
║   │    │       mcp-server.py         │                           │    ║
║   │    │       Python · FastMCP      │                           │    ║
║   │    └──────────────┬─────────────┘                           │    ║
║   │                   │  Python / OS · PTY                       │    ║
║   │                   ▼                                          │    ║
║   │    ┌────────────────────────────┐                           │    ║
║   │    │  🐚  bash · PTY · filesystem │                           │    ║
║   │    │      nmap · ssh · ftp · …    │                           │    ║
║   │    └────────────────────────────┘                           │    ║
║   ╰──────────────────────────────────────────────────────────────╯    ║
╚══════════════════════════════════════════════════════════════════════╝
```

The key thing to read off this picture:

- The **model runs locally, on the host** — it never executes anything itself.
- **Kali runs inside a VM** on that same host, walled off from it.
- The **MCP server runs inside Kali**, right next to the tools it drives.
- The model reaches *into* the VM across a **host-only network** — one port, one
  token, one protocol. That crossing is the only way in.

---

## Who lives where

| Component | Runs on | Role |
|-----------|---------|------|
| 🧠 Qwen 3 + MCP client | **Host** | Reasoning; decides what to do, never touches the VM directly |
| ⚙️ `mcp-server.py` | **Inside Kali VM** | The strait — auth, tool surface, PTY, audit, path jail |
| 🐚 Kali userland | **Inside Kali VM** | The actual teeth: `nmap`, `ssh`, `ftp`, filesystem |
| 🎯 CTF target | Lab network | What the assessment is pointed at |

---

## The three layers

### 🧠 1 · Reasoning — on the host

An LLM (built against Qwen 3) runs the assessment loop from
[`SystemPrompt.md`](./SystemPrompt.md): read state → pick the highest-value
objective → act with the minimum useful command → interpret evidence → record
durable findings → repeat. It has **no direct access** to the VM. It can only
*ask* for actions through MCP tools, and it only ever sees what those tools
return.

### ⚙️ 2 · Control — the strait, inside Kali

`mcp-server.py` is a small FastMCP server deliberately kept readable, because it
*is* the trust boundary. It:

- authenticates every request against a static bearer token
  (`~/kali-mcp/token`);
- keeps up to five persistent Bash PTY sessions, defaulting to one shared
  assessment terminal that survives across calls;
- offers a disposable one-shot runner for clean non-interactive commands;
- appends every disposable command to an append-only JSONL audit trail;
- jails all file I/O to the assessment root, rejecting traversal.

### 🐚 3 · Execution — the VM's userland

Kali supplies the real tooling and a filesystem. Commands run in
`~/lab-projects/first-assessment/`. The VM is meant to sit on an isolated lab
network and be treated as throwaway.

---

## The one channel that crosses the boundary

```
   host                         │  host-only net  │          guest (Kali VM)
   ─────────────────────────────┼─────────────────┼──────────────────────────
   Qwen 3  ──MCP/HTTP+token──▶   │   :8765/mcp     │   ──▶  mcp-server.py ──▶ bash
```

That single arrow is the entire attack-and-control surface between host and VM.
Nothing else reaches across. It's the reason the design works as a safety story:
the model's intent is powerful, but its *reach* is exactly one authenticated
port into a disposable guest.

---

## State & evidence

All runtime state is produced **inside the VM** during an engagement — none of
it is committed to the repo.

| Location (on the Kali VM) | Contents |
|---------------------------|----------|
| `~/kali-mcp/token` | Bearer token the server trusts |
| `~/kali-mcp/command-log.jsonl` | Append-only log of disposable commands |
| `~/lab-projects/first-assessment/` | Working dir, agent reports, `evidence.md` |

---

## Trust boundaries, summarized

```
  ① client → server     bearer-token auth over HTTP   ..... mechanical
  ② server → filesystem path resolved to jail root     ..... mechanical
  ③ agent  → lab scope  authorized targets only         ..... policy (SystemPrompt.md)
```

The first two are enforced by code. The third is behavior the model is
*instructed* to follow — which is exactly why Scylla is scoped to authorized lab
and CTF work, and nothing else.
