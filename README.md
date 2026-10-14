<div align="center">

```
  ███████╗ ██████╗██╗   ██╗██╗     ██╗      █████╗
  ██╔════╝██╔════╝╚██╗ ██╔╝██║     ██║     ██╔══██╗
  ███████╗██║      ╚████╔╝ ██║     ██║     ███████║
  ╚════██║██║       ╚██╔╝  ██║     ██║     ██╔══██║
  ███████║╚██████╗   ██║   ███████╗███████╗██║  ██║
  ╚══════╝ ╚═════╝   ╚═╝   ╚══════╝╚══════╝╚═╝  ╚═╝
```

### Neural reasoning, wired into a Kali box — a project debrief

<p>
  <img alt="type" src="https://img.shields.io/badge/type-project%20debrief-6E56CF">
  <img alt="domain" src="https://img.shields.io/badge/domain-AI%20%2B%20offensive%20security-111">
  <img alt="protocol" src="https://img.shields.io/badge/protocol-MCP-6E56CF">
  <img alt="framework" src="https://img.shields.io/badge/framework-FastMCP-0A7E8C">
  <img alt="scope" src="https://img.shields.io/badge/scope-authorized%20lab%20only-red">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
</p>

<em>What happens when you stop prompting a model about hacking and actually hand
it the terminal? Scylla is the write-up of finding out — and of the plumbing
that turned out to be the real work.</em>

</div>

---

> [!NOTE]
> **This repo is a debrief, not a product.** It documents an experiment in
> driving a Kali Linux VM with a local reasoning model over the
> [Model Context Protocol](https://modelcontextprotocol.io), what worked, and —
> more usefully — what *didn't* until it was engineered to. There's a
> [run-it-yourself](#running-it-yourself) section too, but the point is the
> lessons, not the tool.

> [!WARNING]
> **Authorized use only.** Everything here was built and run against CTF targets
> and self-owned lab machines. Only point it at systems you own or are explicitly
> authorized to test. See [`SECURITY.md`](./SECURITY.md).

---

## The thesis

A large reasoning model already *knows* offensive security. It doesn't need to
be taught what an SUID binary is, how to read an `nmap` scan, or what to try when
it finds a writable cron script. The training is there.

So the interesting question was never "does the model know enough?" It was:

> **Can the model's reasoning actually stay in contact with a live machine long
> enough, and tightly enough, to _use_ what it knows?**

That reframes the whole project. The bottleneck isn't knowledge. It's the loop —
the integration between a model that thinks in tokens and a shell that lives in
state. Most of the real engineering in Scylla went into that seam, not into the
hacking.

---

## Two kinds of work, and where each one wins

Spend time watching an agent solve a CTF and a split appears. Offensive security
is really two different jobs braided together:

| | **Deterministic traversal** | **Open-ended reasoning** |
|---|---|---|
| What it looks like | `cd`, `ls`, read a file, back out, try the next of thirty folders | "these three findings chain into a privesc" |
| Who's good at it | **Humans.** Fast, cheap, almost reflexive — eyes skim, hands move | **The model.** Idea generation, hypothesis forming, connecting scattered clues |
| Cost per step | Near zero for a person | One full command → output → analyze → **generate tokens** per step |
| Where it drags | Tedious but trivial for us | Slow and expensive for us; the model doesn't tire |

This is the crux. When the task is *"glance through a dozen directories and
notice the odd one out,"* a human is wildly more efficient than a model that must
run one command, read the output, and spend an inference pass to decide the next
`ls`. The model shines at the opposite end — **problem-solving, idea generation,
seeing the chain** — where a human slows down.

Scylla's working belief is that **the future of offensive security is combining
the two**: let the model reason about the path, but give it an interface where
the cheap, deterministic browsing doesn't cost a full reasoning cycle every
step. A lot of the design decisions below are really attempts to shrink the tax
on that deterministic half.

---

## The problem that actually mattered: the persistent terminal

Here's the honest retrospective: **most of the friction in this project had
nothing to do with the model's knowledge or training.** It came from the
integration layer — getting MCP and a custom server to give the model a terminal
that behaves like a terminal.

A naive "run a command, return the output" tool breaks almost immediately,
because real assessment work is *stateful*:

- `cd` into a directory — the next command has to still be there.
- `export` a variable, start an `ssh` session, open an `ftp` prompt — the shell
  has to stay alive and interactive.
- Keep the *goal* and the accumulated context stable across dozens of steps and
  context resets.

The failure that kicked it all off was dumbly simple: a scan finds a service,
the model goes to authenticate, and the program asks for a password. A one-shot
tool has nowhere to *send a keystroke into a running program* — so it hung. It
hung **even when the password was blank and all it needed was to press Enter.**
If an empty prompt breaks you, the interface is the problem, not the model.

Right alongside it was a behavioral trap: the model kept trying to do everything
in one **"super command"** — scan, pivot, and discover the whole box in a single
chained line. But the output of each step changes what the next step should be;
the work is a tight *look → orient → step* loop, not one heroic command. Each of
these is a place the loop quietly falls apart if the plumbing — and the
interaction model — is wrong.
Solving the **persistent terminal session** — a real Bash PTY that survives
across tool calls, keeps its working directory and environment, handles
interactive prompts, and holds context over time — was the central engineering
win of the project.

📖 **The full walkthrough is the centerpiece of this debrief:**
[`docs/the-persistent-terminal-problem.md`](./docs/the-persistent-terminal-problem.md)

---

## How it's built

Scylla is one controlled strait between a local reasoning model and a disposable
Kali VM. The model runs on the host; Kali (and the MCP server inside it) runs in
a VM; they meet over a single authenticated port on a host-only network.

```
🖥️  HOST ─ local model (Qwen 3) ──MCP/HTTP+token──▶ 💠 KALI VM ─ Scylla server ─▶ 🐚 bash
```

The full topology — host vs. guest, the single crossing, trust boundaries — is
in [`Architecture.md`](./Architecture.md).

### The tool surface that makes the loop work

| Tool | Why it exists |
|------|---------------|
| `terminal(command)` | **The default.** Persistent Bash PTY — state survives between calls |
| `terminal_read()` | Drain output from a still-running command without issuing a new one |
| `terminal_input(text)` | Answer interactive prompts (passwords, menus) — the thing naive tools can't do |
| `reset_terminal()` | Escape hatch when a shell gets wedged |
| `run_diagnostic(name)` | Cheap read-only orientation probes |
| `run_disposable_command(command)` | Isolated one-shot runs, logged as evidence |
| `write_project_file` / `read_project_file` | Durable, path-jailed memory for the assessment |
| `export_evidence(limit)` | Turn the command log into a Markdown evidence trail |
| `kali_status()` | Where am I, who am I, what's my network |

Reference: [`docs/tools.md`](./docs/tools.md).

---

## What this repo contains

```
Scylla/
├── mcp-server.py          # The MCP server — the strait between model and VM
├── SystemPrompt.md        # The operating contract the agent reasons under
├── Architecture.md        # Topology debrief: host · VM · the one channel
├── README.md              # This write-up
├── docs/
│   ├── the-persistent-terminal-problem.md   # ★ the core engineering story
│   ├── getting-started.md                    # run-it-yourself walkthrough
│   └── tools.md                              # MCP tool reference
├── SECURITY.md · CONTRIBUTING.md · CHANGELOG.md · LICENSE · .gitignore
```

---

## Takeaways

- **Knowledge wasn't the constraint — interface was.** The model could already
  do the security work; the project was mostly about building a loop it could
  stay inside.
- **The persistent terminal was the unlock.** Statefulness (working dir, env,
  interactive sessions, durable context) is what separates a chat about hacking
  from an agent that hacks.
- **Reasoning and traversal want different interfaces.** The model is strongest
  at the thinking; the open opportunity is making the cheap, deterministic
  browsing cost less than a full inference step each time.
- **The frontier is the combination.** Human-like reflexive traversal + machine
  reasoning, in one loop, is the direction worth chasing.

---

## Running it yourself

If you want to reproduce the setup on your own authorized lab, the full
walkthrough — token, bind address, launch, wiring the agent — lives in
[`docs/getting-started.md`](./docs/getting-started.md). The short version:

```bash
pip install fastmcp
mkdir -p ~/kali-mcp && head -c 32 /dev/urandom | base64 > ~/kali-mcp/token
python mcp-server.py     # serves http://192.168.56.101:8765/mcp
```

Then point an MCP client at that endpoint with the token, load
[`SystemPrompt.md`](./SystemPrompt.md) as the system prompt, and give it a target
inside your authorized scope.

---

## License

[MIT](./LICENSE).
