# The Persistent-Terminal Problem

> The core engineering story of Scylla. If you read one doc in this repo, read
> this one — it's where the project actually lived.

---

## Starting assumption (which turned out wrong)

Going in, the mental model was: *the hard part is the hacking.* Give a capable
reasoning model a way to run commands on a Kali box, point it at a CTF, and the
difficulty would be whether the model knows enough to find the flag.

It doesn't take long to flip that. The model knows plenty. It recognizes service
banners, reasons about attack chains, knows exactly what to try against a
writable cron job or a misconfigured `sudo` rule. **Knowledge was never the wall.**

The wall was that a reasoning model thinks in discrete, stateless token passes,
and a shell is a stateful, living thing — and nothing in a plain "run command,
return output" tool bridges those two worldviews.

---

## Why "run a command, return the output" breaks

The obvious first tool is a function that takes a command string, runs it in a
subprocess, and returns stdout. It works for exactly one class of command:
self-contained, non-interactive, one-shot. Real assessment work is none of those
things. It breaks in three distinct ways.

### 1 · State doesn't carry

```
Step 1:  cd /var/www/html        →  (subprocess exits)
Step 2:  ls                       →  lists $HOME, not /var/www/html
```

Each call is a fresh subprocess. `cd`, `export`, a mounted share, a set
environment variable — all gone the instant the command returns. The model
reasons *"now I'm in the web root, let me look around"* and the machine has
already forgotten it was ever there. The agent's mental model and the shell's
reality silently diverge, and every step after compounds the drift.

### 2 · Interactivity is impossible — the one that actually bit us

This is the failure that kicked off the whole project. Run a scan, find a
service, go to authenticate — and the program stops and asks for input:

```
Step 1:  ssh user@target          →  hangs on "password:" … then the call times out
```

A huge fraction of offensive work is interactive: `ssh`, `ftp`, `mysql`, `su`,
`sudo` password prompts, `nc` sessions, anything with a menu. A one-shot runner
has no way to *see* the prompt and no way to *answer* it. The program is sitting
there waiting for input on a PTY that the tool already abandoned.

And here's the part that made it obvious how fundamental the problem was: **it
broke even when there was no password.** The lab was set up so some auth steps
took an empty password — you just had to press **Enter**. The model knew that.
It had the right answer. But a one-shot tool gives you nowhere to *send a
keystroke into a running program* — there's no "the command already launched and
is now waiting on stdin." So the single most trivial possible input, hitting
Enter on an empty prompt, was enough to wedge the entire loop. If a blank
password breaks you, the interface is the problem, not the model.

This is what forced the move to a real PTY: the model needed a terminal it could
keep *typing into*, not just fire a command at.

### 3 · Context and goal erode

Even when individual commands work, the *assessment* has to persist: what's the
target, what's been found, what's been ruled out, what's the current access
level, what's the goal. Across dozens of steps — and across context-window
resets — that thread has to survive outside the model's short-term context, or
the agent loops, re-enumerates things it already knew, and loses the plot.

---

## A related trap: the "super command"

There was a behavioral failure sitting right alongside the plumbing one. Left to
its own devices, the model kept trying to do *everything in one shot* — one
enormous chained command meant to scan, enumerate, pivot, and discover the whole
target in a single go:

```
nmap -sV target && hydra ... && ssh ... && find / -perm -4000 && cat $(grep -rl flag /)
```

That's just not how assessment works. The output of step one *changes what step
two should even be.* You can't pipe your way past the need to **look at what came
back before deciding what's next.** These are the moments where the model is
genuinely strong — reading a result, orienting, forming the next move — and
cramming them into one mega-command throws exactly that strength away. It also
tends to hang the instant any link in the chain hits an interactive prompt (see
above), so the two failure modes fed each other.

The real shape of the work is a tight loop: **run one meaningful thing → look at
the output → re-evaluate where you are and what you can now see → take the next
step.** Continuous evaluation, not one heroic command. The persistent terminal
makes that loop cheap and natural, and the operating contract in
[`SystemPrompt.md`](../SystemPrompt.md) leans on it directly — *"execute the
minimum useful command(s)," "evaluate the actual results,"* then pick the next
highest-value action. The fix was as much about getting the model to take small,
observed steps as it was about keeping the shell alive.

## The fix: a real PTY that lives between calls

The solution is to stop thinking of a "command" as the unit and start thinking
of a **session** as the unit. Scylla forks a real pseudo-terminal running Bash
and keeps it alive across tool calls:

```python
pid, fd = pty.fork()
if pid == 0:
    os.chdir(workdir)
    os.execv("/bin/bash", ["/bin/bash", "--noprofile", "--norc"])
```

That one `pty.fork()` is the hinge of the whole project. Because it's a genuine
PTY and the process persists:

- **`cd` sticks.** Working directory, environment, shell state — all retained,
  because it's literally the same shell process from call to call.
- **Interactive programs work.** `ssh` prints its `password:` prompt into the
  PTY; the model reads it and writes the answer back into the *same* terminal.
- **Output is drained, not awaited.** Reads are non-blocking with a bounded
  wait, so a long-running or still-producing command doesn't deadlock the tool —
  the model can read now and read again.

The tool surface splits along exactly the failure modes above:

| Failure mode | Tool that answers it |
|---|---|
| State doesn't carry | `terminal()` — issues a command into the persistent shell |
| Can't see ongoing output | `terminal_read()` — drains what's arrived without sending anything |
| Can't answer prompts | `terminal_input()` — writes into the live PTY (password, menu, confirm) |
| Shell wedged | `reset_terminal()` — tear down, fork a clean one |
| Need durable memory | `write_project_file()` / `read_project_file()` — context outside the window |
| Need an auditable record | `run_disposable_command()` + `export_evidence()` |

The persistent terminal carries live state; the project files carry durable
state. Between them, the model can hold a working directory *and* an assessment
across a context reset.

---

## Why this connects to the bigger theme

Offensive security is two kinds of work braided together (the README calls this
out directly):

- **Deterministic traversal** — skim a directory, back out, open the next one,
  thirty times. Reflexive and near-free for a human.
- **Open-ended reasoning** — chain findings, form a hypothesis, pick the path.
  The model's home turf.

A one-shot tool taxes the *traversal* half brutally: every trivial `ls` costs a
full command → output → inference → next-command cycle. The persistent terminal
is, in large part, an attempt to **lower that tax** — to let the cheap,
deterministic browsing happen inside a live shell instead of paying a reasoning
pass for each step, so the model's expensive thinking is spent on the part it's
actually good at.

That's the quiet argument of the whole project: the model's *knowledge* was
ready on day one. What took building was an **interface where its reasoning could
stay in contact with a live machine** without the plumbing falling apart
underneath it. Get that seam right, and you're looking at what the combination of
machine reasoning and human-like traversal could become.

---

## What we'd flag as still-open

Honest debrief, so: the persistent terminal solved statefulness, not the cost
asymmetry. A model doing deterministic browsing is still slower and pricier than
a human doing the same skim. The interesting unfinished work is giving the model
cheaper ways to *traverse* — batched or scripted enumeration, better summaries of
large trees, ways to glance without spending a full reasoning step — so the
expensive reasoning is reserved for the moments that actually need it.
