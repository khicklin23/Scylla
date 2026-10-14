<div align="center">

```
                      ███████╗ ██████╗██╗   ██╗██╗     ██╗      █████╗
                      ██╔════╝██╔════╝╚██╗ ██╔╝██║     ██║     ██╔══██╗
                      ███████╗██║      ╚████╔╝ ██║     ██║     ███████║
                      ╚════██║██║       ╚██╔╝  ██║     ██║     ██╔══██║
                      ███████║╚██████╗   ██║   ███████╗███████╗██║  ██║
                      ╚══════╝ ╚═════╝   ╚═╝   ╚══════╝╚══════╝╚═╝  ╚═╝
```

### Wiring a local reasoning model into a Kali box. A project debrief.

<p>
  <img alt="type" src="https://img.shields.io/badge/type-project%20debrief-6E56CF">
  <img alt="domain" src="https://img.shields.io/badge/domain-AI%20%2B%20offensive%20security-111">
  <img alt="protocol" src="https://img.shields.io/badge/protocol-MCP-6E56CF">
  <img alt="scope" src="https://img.shields.io/badge/scope-authorized%20lab%20only-red">
</p>

<em>What happens when you stop asking a model about hacking and actually hand it
the terminal? This is the write-up of finding out, and of the plumbing that
turned out to be the real work.</em>

</div>

---

> [!NOTE]
> This repo is a debrief, not a product. It's a record of an experiment: driving
> a Kali Linux VM with a local reasoning model, what worked, and (more usefully)
> what kept breaking until it got engineered properly. There's a short
> [run-it-yourself](#running-it-yourself) section near the bottom, but the point
> here is the lessons, not the tool.

> [!WARNING]
> Authorized use only. Everything here was built and run against practice CTF
> targets and lab machines we owned. Only point it at systems you own or are
> explicitly allowed to test. See [`SECURITY.md`](./SECURITY.md).

---

## The idea

A good reasoning model already knows offensive security. You don't have to teach
it what a setuid binary is, or how to read an nmap scan, or what to try when it
finds a cron job it can write to. That knowledge is baked in.

So the question was never "does the model know enough?" It was more like:

> Can the model's reasoning actually stay in contact with a live machine long
> enough, and closely enough, to *use* what it already knows?

That turned the project on its head. The hard part wasn't the hacking. It was
the seam between a model that thinks in short, stateless bursts and a shell that
lives in state and keeps running after you walk away from it. Almost all of the
real work went into that seam.

---

## Two kinds of work, and who's better at each

Watch an agent work a CTF for a while and a split shows up. Offensive security is
really two jobs tangled together.

One is just moving around. Change into a directory, list it, read a file, back
out, open the next of thirty folders. For a person this is almost free: your
eyes skim, your hands move, you barely think about it.

The other is the actual thinking. These three findings chain into a way in.
That odd service is worth a closer look. This is where the model is strong, and
where a person slows down.

| | Moving around | Thinking it through |
|---|---|---|
| Looks like | `cd`, `ls`, read, back out, repeat | "these findings chain into a foothold" |
| Humans | fast, cheap, almost reflexive | slower, we get tired |
| The model | one command, read output, then a whole thinking step just to pick the next `ls` | strong, and it never gets bored |

That gap is the whole point. When the task is "glance through a dozen folders
and notice the weird one," a person runs circles around a model that has to run
a command, read it, and spend a full reasoning step deciding where to look next.
The model wins at the other end, the part where you have to actually reason about
a path.

The bet behind this project is that the future is putting those two together:
let the model reason about the route, but give it an interface where the cheap,
repetitive looking doesn't cost a full thinking step every single time. A lot of
the design is really just trying to lower the price of that looking.

---

## The thing that actually mattered: keeping the terminal alive

Here's the honest version. Most of the trouble in this project had nothing to do
with how smart the model was. It came from the glue: getting the model a terminal
that behaves like a real terminal.

The simplest possible tool, run a command and hand back the output, falls apart
almost immediately, because real work keeps state:

- You `cd` somewhere and the next command has to still be there.
- You start an ssh or ftp session and the shell has to stay open and let you
  keep typing into it.
- You have to hold the goal and everything you've learned steady across dozens of
  steps.

The failure that kicked the whole thing off was embarrassingly simple. A scan
finds a service, the model goes to log in, and the program stops and asks for a
password. A one-command-at-a-time tool has nowhere to *send a keystroke into a
program that's already running*, so it just hung. It hung even when there was no
password and all it needed to do was press Enter. If an empty prompt is enough to
break you, the problem is the interface, not the model.

Right next to that was a habit problem. Left alone, the model kept trying to do
everything in one giant command: scan, pivot, and find the flag all in a single
chained line. But that isn't how it works. What comes back from one step changes
what the next step should even be. You have to look before you decide. The job is
a tight loop of look, get your bearings, take one step, look again, not one hero
command that does it all.

The fix for both was a real, persistent terminal: a Bash shell that stays alive
between calls, keeps its working directory and environment, lets the model answer
prompts, and holds its context over time. That was the central win of the
project, and it's written up in full here:

[`docs/the-persistent-terminal-problem.md`](./docs/the-persistent-terminal-problem.md)

---

## How it's put together

There's one controlled path between a local model and a throwaway Kali VM. The
model runs on your machine. Kali, and the small server the model talks to, runs
inside a VM. They meet over a single locked-down port on a host-only network.

```
HOST   local model  ---- request + token ---->   KALI VM   small server   --->   bash
```

The full picture, host versus guest, the single crossing, and where the trust
boundaries sit, is in [`Architecture.md`](./Architecture.md).

### The tools that make the loop work

| Tool | Why it's there |
|------|----------------|
| `terminal(command)` | The default. A Bash shell that keeps its state between calls |
| `terminal_read()` | Read more output from a command that's still running |
| `terminal_input(text)` | Answer a prompt (a password, a menu). The thing the naive tool can't do |
| `reset_terminal()` | Start a clean shell when one gets stuck |
| `run_diagnostic(name)` | Cheap read-only "where am I" checks |
| `run_disposable_command(command)` | A clean one-off run, logged as evidence |
| `write_project_file` / `read_project_file` | Durable notes that outlive the model's short memory |
| `export_evidence(limit)` | Turn the command log into a readable evidence trail |
| `kali_status()` | Who am I, where am I, what's my network |

Full reference: [`docs/tools.md`](./docs/tools.md).

---

## What's in here

```
Scylla/
├── mcp-server.py          # The server the model talks to, sitting between it and the VM
├── SystemPrompt.md        # The ground rules the agent works under
├── Architecture.md        # The topology: your machine, the VM, and the one channel between
├── README.md              # This write-up
├── docs/
│   ├── the-persistent-terminal-problem.md   # the core story, read this one
│   ├── getting-started.md                    # how to run it yourself
│   └── tools.md                              # what each tool does
├── SECURITY.md · CONTRIBUTING.md · CHANGELOG.md · .gitignore
```

---

## What we took away

- The knowledge was never the bottleneck. The interface was. The model could
  already do the security work; the project was mostly about building a loop it
  could stay inside of.
- Keeping the terminal alive was the unlock. State, like the working directory,
  an open ssh session, and remembered context, is what separates a chat about
  hacking from something that actually hacks.
- Reasoning and looking want different interfaces. The model is best at the
  thinking. The open problem is making the cheap, repetitive looking cost less
  than a full reasoning step each time.
- The interesting direction is the combination: human-style quick looking plus
  machine-style reasoning, in one loop.

---

## Running it yourself

If you want to reproduce this on your own lab, the full walkthrough (token, bind
address, launch, wiring up the agent) is in
[`docs/getting-started.md`](./docs/getting-started.md). The short version:

```bash
pip install fastmcp
mkdir -p ~/kali-mcp && head -c 32 /dev/urandom | base64 > ~/kali-mcp/token
python mcp-server.py     # serves http://192.168.56.101:8765/mcp
```

Then point your client at that address with the token, load
[`SystemPrompt.md`](./SystemPrompt.md) as the system prompt, and give it a target
inside your authorized scope.
