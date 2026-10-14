# Architecture

> How Scylla is put together: the pieces, where each one runs, and why the
> boundaries sit where they do. This is a debrief, not a manual.

The whole idea is a single controlled path between a reasoning model and a live
Kali box. The interesting part isn't any one component. It's the layout: what
runs on your machine, what runs inside the VM, and the one thin channel that
crosses between them.

---

## The layout at a glance

Everything lives on one physical machine, but split across a virtualization
boundary. The model stays on the host. Kali, and the server the model talks to,
lives in a VM. They talk over a host-only network.

```
+======================================================================+
|  HOST MACHINE  (your machine, local)                                 |
|                                                                      |
|   +----------------------------+                                     |
|   |  Qwen 3  (local model)     |                                     |
|   |  + the client that talks   |                                     |
|   |    to the server           |                                     |
|   |                            |                                     |
|   |  "Inspect the target's     |                                     |
|   |   exposed services."       |                                     |
|   +--------------+-------------+                                     |
|                  |                                                   |
|                  |  request over HTTP + bearer token                 |
|                  |  to 192.168.56.101:8765/mcp                       |
|                  |                                                   |
|   ...............|........ host-only network (192.168.56.0/24) ..... |
|                  |                                                   |
|   +--------------v-----------------------------------------------+   |
|   |  KALI VM   (guest, isolated, disposable)                     |   |
|   |                                                             |   |
|   |    +----------------------------+                           |   |
|   |    |  SCYLLA SERVER             |   <- the one channel      |   |
|   |    |     mcp-server.py          |                           |   |
|   |    |     Python + FastMCP       |                           |   |
|   |    +--------------+-------------+                           |   |
|   |                   |  Python / OS, over a PTY                 |   |
|   |                   v                                         |   |
|   |    +----------------------------+                           |   |
|   |    |  bash, PTY, filesystem      |                           |   |
|   |    |  nmap, ssh, ftp, ...        |                           |   |
|   |    +----------------------------+                           |   |
|   +--------------------------------------------------------------+   |
+======================================================================+
```

The thing to read off this picture:

- The model runs locally, on your machine. It never executes anything itself.
- Kali runs inside a VM on that same machine, walled off from it.
- The server runs inside Kali, right next to the tools it drives.
- The model reaches into the VM across a host-only network. One port, one token,
  one protocol. That crossing is the only way in.

---

## Who lives where

| Component | Runs on | Role |
|-----------|---------|------|
| Qwen 3 + client | Host | Does the reasoning. Decides what to do, never touches the VM directly |
| `mcp-server.py` | Inside the Kali VM | The one channel: auth, the tools, the terminal, the audit log, the path jail |
| Kali userland | Inside the Kali VM | The actual tools: nmap, ssh, ftp, the filesystem |
| CTF target | Lab network | What the assessment is pointed at |

---

## The three layers

### 1. Reasoning, on the host

A local model (built against Qwen 3) runs the loop laid out in
[`SystemPrompt.md`](./SystemPrompt.md): read the current state, pick the most
useful next objective, run the smallest command that moves it forward, read what
came back, write down anything worth keeping, repeat. It has no direct access to
the VM. It can only ask for actions through the tools, and it only ever sees what
those tools hand back.

### 2. The channel, inside Kali

`mcp-server.py` is a small server kept deliberately short and readable, because
it is the trust boundary. It:

- checks every request against a bearer token (`~/kali-mcp/token`);
- keeps up to five live Bash terminals, defaulting to one shared terminal that
  survives across calls;
- offers a separate one-off runner for clean, non-interactive commands;
- appends every one-off command to an audit log;
- keeps all file reads and writes inside the assessment folder, rejecting
  anything that tries to climb out of it.

### 3. The tools, in the VM

Kali supplies the real tooling and a filesystem. Commands run in
`~/lab-projects/first-assessment/`. The VM is meant to sit on an isolated lab
network and be treated as throwaway.

---

## The one path that crosses the boundary

```
   host                          |  host-only net  |          guest (Kali VM)
   ------------------------------+-----------------+--------------------------
   model  --request + token-->   |   :8765/mcp     |   -->  mcp-server.py --> bash
```

That single arrow is the entire control surface between your machine and the VM.
Nothing else reaches across. It's why the design holds up as a safety story: the
model's intent is powerful, but its reach is exactly one authenticated port into
a disposable guest.

---

## State and evidence

All of this is produced inside the VM during a run. None of it is committed to
the repo.

| Location (on the Kali VM) | Contents |
|---------------------------|----------|
| `~/kali-mcp/token` | The bearer token the server trusts |
| `~/kali-mcp/command-log.jsonl` | Append-only log of one-off commands |
| `~/lab-projects/first-assessment/` | Working dir, the agent's notes, `evidence.md` |

---

## Trust boundaries, in short

```
  1. client -> server      bearer token over HTTP          enforced by code
  2. server -> filesystem  paths resolved to the jail root  enforced by code
  3. agent  -> lab scope   authorized targets only          policy (SystemPrompt.md)
```

The first two are enforced by code. The third is behavior the model is told to
follow, which is exactly why Scylla is for authorized lab and CTF work and
nothing else.
