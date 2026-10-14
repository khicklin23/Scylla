# Keeping the Terminal Alive

> The core engineering story of Scylla. If you read one doc in this repo, read
> this one. It's where the project actually lived.

---

## What we assumed going in (and got wrong)

The starting assumption was simple: the hard part is the hacking. Give a capable
model a way to run commands on a Kali box, point it at a CTF, and the only real
question is whether it knows enough to find the flag.

It doesn't take long to flip that around. The model knows plenty. It recognizes
service banners, reasons about how to get in, knows exactly what to try against a
writable cron job or a loose sudo rule. Knowledge was never the wall.

The wall was that a model thinks in short, stateless bursts, and a shell is a
living, stateful thing that keeps running after the model looks away. Nothing in
a plain "run a command, return the output" tool bridges those two worlds.

---

## Why "run a command, return the output" falls apart

The obvious first tool takes a command, runs it, and hands back whatever it
printed. That works for exactly one kind of command: self-contained,
non-interactive, one and done. Real work is none of those things. It breaks in
three distinct ways.

### 1. State doesn't carry

```
Step 1:  cd /var/www/html        ->  (the command finishes and the shell exits)
Step 2:  ls                       ->  lists your home folder, not /var/www/html
```

Every call is a brand new shell. A `cd`, an exported variable, a mounted share,
all gone the instant the command returns. The model reasons "okay, I'm in the web
root now, let me look around," and the machine has already forgotten it was ever
there. The model's picture of where it is and the shell's reality quietly drift
apart, and every step after that only makes it worse.

### 2. You can't answer a prompt (this is the one that actually bit us)

This is the failure that started the whole project. Run a scan, find a service,
go to log in, and the program stops and asks for something:

```
Step 1:  ssh user@target          ->  sits on "password:" ... then the call times out
```

A huge amount of this work is interactive: ssh, ftp, mysql, su, sudo asking for a
password, a netcat session, anything with a menu. A one-shot runner has no way to
*see* the prompt and no way to *answer* it. The program is just sitting there
waiting for input on a terminal the tool already walked away from.

Here's the part that made it obvious how deep the problem went: it broke even
when there was no password. The lab was set up so some logins took an empty
password and all you had to do was press Enter. The model knew that. It had the
right answer. But a one-shot tool gives you nowhere to send a single keystroke
into a program that's already running. So the most trivial input imaginable,
hitting Enter on a blank prompt, was enough to jam the entire loop. If an empty
prompt breaks you, the problem is the interface, not the model.

That's what forced the move to a real terminal. The model needed something it
could keep typing into, not just fire a command at.

### 3. Context and the goal wear away

Even when the individual commands work, the assessment itself has to persist.
What's the target. What's been found. What's been ruled out. What level of access
we have right now. What the goal is. Across dozens of steps, and across the
model's context filling up and getting trimmed, that thread has to live somewhere
outside the model's short-term memory, or it starts looping, re-scanning things
it already knew, and losing the plot.

---

## A related trap: the one giant command

There was a habit problem sitting right next to the plumbing one. Left to its own
devices, the model kept trying to do everything in a single shot: one huge chained
command meant to scan, enumerate, break in, and find the flag all at once.

```
nmap -sV target && hydra ... && ssh ... && find / -perm -4000 && cat $(grep -rl flag /)
```

That just isn't how the work goes. What comes back from the first step changes
what the second step should even be. You can't pipe your way past the need to
look at the result before deciding what's next. And these are exactly the moments
where the model is genuinely good: reading a result, getting its bearings, and
picking the next move. Cramming them into one mega-command throws that strength
away. It also tends to hang the second any link in the chain hits a prompt (see
above), so the two problems fed each other.

The real shape of the work is a tight loop: run one meaningful thing, look at
what came back, figure out where you are and what you can now see, take the next
step. Continuous checking, not one hero command. A live terminal makes that loop
cheap and natural, and the ground rules in
[`SystemPrompt.md`](../SystemPrompt.md) lean on it directly: run the smallest
useful command, look at the actual result, then pick the next best move. The fix
was as much about getting the model to take small, checked steps as it was about
keeping the shell alive.

---

## The fix: a real terminal that lives between calls

The trick is to stop treating a "command" as the unit and start treating a
*session* as the unit. Scylla forks a real pseudo-terminal running Bash and keeps
it alive across calls:

```python
pid, fd = pty.fork()
if pid == 0:
    os.chdir(workdir)
    os.execv("/bin/bash", ["/bin/bash", "--noprofile", "--norc"])
```

That one `pty.fork()` is the hinge of the whole project. Because it's a real
terminal and the process stays alive:

- `cd` sticks. Working directory, environment, shell state, all kept, because
  it's literally the same shell from one call to the next.
- Interactive programs work. ssh prints its "password:" into the terminal, the
  model reads it, and it writes the answer back into the same terminal.
- Output gets drained, not waited on. Reads are non-blocking with a short bound,
  so a long-running or still-printing command doesn't lock up the tool. The model
  can read now and read again.

The tools split along exactly the failure modes above:

| What broke | The tool that fixes it |
|---|---|
| State doesn't carry | `terminal()`, runs a command in the live shell |
| Can't see ongoing output | `terminal_read()`, drains what's arrived without sending anything |
| Can't answer prompts | `terminal_input()`, types into the live terminal (password, menu, Enter) |
| Shell got stuck | `reset_terminal()`, tear it down and start a clean one |
| Need durable memory | `write_project_file()` / `read_project_file()`, notes outside the context window |
| Need a record | `run_disposable_command()` plus `export_evidence()` |

The live terminal carries the moment-to-moment state. The project files carry the
durable state. Between them, the model can hold both a working directory and a
whole assessment across a context reset.

---

## Why this ties back to the bigger theme

The work is really two things braided together (the README spells this out):

- Moving around: skim a folder, back out, open the next, thirty times. Reflexive
  and nearly free for a person.
- Thinking it through: chain findings, form a guess, pick the path. The model's
  home turf.

A one-shot tool taxes the moving-around half brutally. Every trivial `ls` costs a
full command, output, reasoning step, next command. The live terminal is, in
large part, an attempt to lower that tax: let the cheap, repetitive looking
happen inside a running shell instead of paying a reasoning step for each one, so
the model's expensive thinking goes toward the part it's actually good at.

That's the quiet argument of the whole project. The model's knowledge was ready
on day one. What took building was an interface where its reasoning could stay in
contact with a live machine without the glue falling apart underneath it. Get
that seam right and you start to see what the mix of machine reasoning and
human-style quick looking could become.

---

## What's still open

Honest debrief, so: the live terminal solved the state problem, not the cost
problem. A model doing the moving-around work is still slower and pricier than a
person doing the same skim. The interesting unfinished work is giving the model
cheaper ways to look: batched or scripted enumeration, better summaries of big
directory trees, ways to glance without spending a full reasoning step, so the
expensive thinking is saved for the moments that actually need it.
