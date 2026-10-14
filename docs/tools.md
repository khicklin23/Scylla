# MCP Tool Reference

Scylla exposes the following tools over MCP. All `wait_seconds` values are
clamped to a safe range by the server.

---

## Terminal (persistent)

The persistent terminal is a real Bash PTY that survives across calls. Working
directory, environment variables, shell state, and interactive programs persist
until the session is reset. This is the **default** path for assessment work.

### `terminal(command, wait_seconds=0.8)`
Execute a command in the persistent terminal and return newly produced output.
If the command launches an interactive program, the terminal stays active, so
respond with `terminal_input`.

### `terminal_read(wait_seconds=0.8)`
Drain output that has arrived since the last interaction, without sending a
command. Useful when a long-running command is still producing output.

### `terminal_input(text="", press_enter=True, wait_seconds=0.8)`
Send input to the current terminal: a password, menu selection, confirmation,
or any shell input the running program is waiting for.

### `reset_terminal()`
Destroy the current terminal and create a fresh Bash shell. Use only when the
terminal is stuck or a clean shell is explicitly required.

> Up to **5** active terminal sessions may exist at once.

---

## Disposable execution

### `run_disposable_command(command, timeout_seconds=120, stdin_text="")`
Run a command in a brand-new, isolated subprocess. Shell state, directory
changes, and running programs are discarded on return. Intended only for
commands known to be fully non-interactive where isolation is useful.

Every call is appended to `~/kali-mcp/command-log.jsonl` with timestamp,
command, exit code, and truncated stdout/stderr. This is the evidence trail.

---

## Diagnostics

### `run_diagnostic(name)`
Run a named, read-only probe. Allowed values:
`whoami`, `pwd`, `uname`, `ip_addr`, `ip_route`.

### `kali_status()`
Return the VM's hostname, current user, and network addresses.

---

## Project files (sandboxed)

All paths resolve against `~/lab-projects/first-assessment/` and are rejected if
they escape that root.

### `write_project_file(relative_path, content)`
Write a report, checklist, or note into the assessment folder. Content is capped
at 100,000 characters.

### `read_project_file(relative_path)`
Read a file from the assessment folder (first 100,000 characters).

### `export_evidence(limit=12)`
Render the most recent logged disposable commands into `evidence.md` inside the
assessment folder. `limit` is clamped to `1..50`.

---

## Notes

- Output returned to the model is truncated (tail) to keep responses compact.
- The persistent terminal and disposable runner are **separate** execution
  contexts, so state does not carry between them.
- Treat tool output as the source of truth; do not infer success without it.
