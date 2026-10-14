import getpass
import socket
import subprocess
import os
import pty
import select
import signal
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

auth_token = (Path.home() / "kali-mcp" / "token").read_text().strip()
mcp = FastMCP("Kali Lab", auth=StaticTokenVerifier(
    tokens={auth_token: {"client_id": "open-webui", "scopes": ["lab"]}}
))

@dataclass
class TerminalSession:
    pid: int
    fd: int
    created_at: float
    output: str = ""
    closed: bool = False

terminal_sessions: dict[str, TerminalSession] = {}
default_terminal_id: str | None = None


def _read_pty(session: TerminalSession, wait_seconds: float = 0.2) -> str:
    """Read currently available PTY output without blocking indefinitely."""
    if session.closed:
        return ""

    chunks = []
    deadline = time.time() + max(0.0, min(float(wait_seconds), 2.0))

    while time.time() < deadline:
        readable, _, _ = select.select([session.fd], [], [], 0.05)

        if not readable:
            continue

        try:
            data = os.read(session.fd, 4096)
        except OSError:
            session.closed = True
            break

        if not data:
            session.closed = True
            break

        chunks.append(data.decode("utf-8", errors="replace"))

    new_output = "".join(chunks)
    session.output += new_output
    return new_output

def _create_terminal_session() -> tuple[str, TerminalSession]:
    """Create a persistent Bash PTY."""

    workdir = Path.home() / "lab-projects" / "first-assessment"
    workdir.mkdir(parents=True, exist_ok=True)

    active = [s for s in terminal_sessions.values() if not s.closed]
    if len(active) >= 5:
        raise ValueError("Maximum of 5 active terminal sessions reached")

    session_id = uuid.uuid4().hex[:12]

    pid, fd = pty.fork()

    if pid == 0:
        os.chdir(workdir)
        os.execv(
            "/bin/bash",
            ["/bin/bash", "--noprofile", "--norc"]
        )

    session = TerminalSession(
        pid=pid,
        fd=fd,
        created_at=time.time(),
    )

    terminal_sessions[session_id] = session

    time.sleep(0.15)
    _read_pty(session, 0.3)

    return session_id, session

def _get_default_terminal() -> tuple[str, TerminalSession]:
    """Return the persistent default terminal, creating it if necessary."""

    global default_terminal_id

    if default_terminal_id is not None:
        session = terminal_sessions.get(default_terminal_id)

        if session is not None and not session.closed:
            return default_terminal_id, session

    session_id, session = _create_terminal_session()
    default_terminal_id = session_id

    return session_id, session


@mcp.tool
def terminal_read(wait_seconds: float = 0.8) -> dict:
    """Read new output from the persistent Kali assessment terminal."""

    session_id, session = _get_default_terminal()

    output = _read_pty(
        session,
        max(0.1, min(float(wait_seconds), 2.0))
    )

    return {
        "output": output[-12000:],
        "terminal_active": not session.closed,
    }


@mcp.tool
def terminal(command: str, wait_seconds: float = 0.8) -> dict:
    """Execute a command in the persistent Kali assessment terminal.

    THIS IS THE DEFAULT TOOL FOR RUNNING KALI COMMANDS.

    The Bash shell persists between calls, including its working directory,
    environment variables, shell state, and interactive programs.

    If a command starts an interactive program or displays a prompt, the
    terminal remains active. Use terminal_input() to respond to that program.

    Prefer this tool over run_disposable_command for normal assessment work.
    """

    session_id, session = _get_default_terminal()

    # Clear any output that arrived since the previous interaction.
    _read_pty(session, 0.05)

    os.write(session.fd, (command + "\n").encode("utf-8"))

    time.sleep(0.10)
    output = _read_pty(
        session,
        max(0.1, min(float(wait_seconds), 2.0))
    )

    return {
        "command": command,
        "output": output[-12000:],
        "terminal_active": not session.closed,
    }
    
    
    

@mcp.tool
def terminal_input(
    text: str = "",
    press_enter: bool = True,
    wait_seconds: float = 0.8
) -> dict:
    """Send input to the current persistent Kali terminal.

    Use this when the current command requests a password, confirmation,
    menu selection, shell input, or other interactive response.

    This always communicates with the same terminal used by terminal().
    """

    session_id, session = _get_default_terminal()

    data = text

    if press_enter:
        data += "\n"

    os.write(session.fd, data.encode("utf-8"))

    time.sleep(0.10)
    output = _read_pty(
        session,
        max(0.1, min(float(wait_seconds), 2.0))
    )

    return {
        "sent": repr(data),
        "output": output[-12000:],
        "terminal_active": not session.closed,
    }


@mcp.tool
def reset_terminal() -> dict:
    """Destroy the current persistent terminal and create a fresh Bash shell.

    Use only when the terminal is stuck, corrupted, or a completely fresh
    shell is explicitly required.
    """

    global default_terminal_id

    if default_terminal_id is not None:
        session = terminal_sessions.pop(default_terminal_id, None)

        if session is not None and not session.closed:
            try:
                os.kill(session.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

            try:
                os.close(session.fd)
            except OSError:
                pass

            session.closed = True

    default_terminal_id = None

    session_id, session = _get_default_terminal()

    return {
        "reset": True,
        "terminal_active": not session.closed,
    }


@mcp.tool
def kali_status() -> dict:
    """Report this Kali VM's hostname, user, and network addresses."""
    result = subprocess.run(
        ["ip", "-br", "addr"], capture_output=True, text=True,
        timeout=5, check=True
    )
    return {
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
        "addresses": result.stdout,
    }

@mcp.tool
def run_diagnostic(
    name: Literal["whoami", "pwd", "uname", "ip_addr", "ip_route"]
) -> dict:
    """Run a named diagnostic command in the Kali VM."""
    commands = {
        "whoami": ["whoami"],
        "pwd": ["pwd"],
        "uname": ["uname", "-a"],
        "ip_addr": ["ip", "-br", "addr"],
        "ip_route": ["ip", "route"],
    }
    command = commands[name]
    print(f"Running: {' '.join(command)}", flush=True)
    result = subprocess.run(
        command, cwd=Path.home(), capture_output=True,
        text=True, timeout=15
    )
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@mcp.tool
def run_disposable_command(
    command: str,
    timeout_seconds: int = 120,
    stdin_text: str = ""
) -> dict:
    """Run a command in a NEW disposable subprocess.

    DO NOT use this for normal Kali assessment commands.
    Use terminal() by default.

    Use this only when the command is known to be completely non-interactive
    and isolation from the persistent assessment shell is specifically useful.

    Shell state, working-directory changes, environment changes, and running
    programs are discarded when this function returns.
    """

    import json
    from datetime import datetime, timezone

    workdir = Path.home() / "lab-projects" / "first-assessment"
    workdir.mkdir(parents=True, exist_ok=True)
    timeout = max(1, min(int(timeout_seconds), 180))
    print(f"Running: {command}", flush=True)

    # Allocate a pseudo-terminal when requested.
    argv = ["/bin/bash", "-lc", command]

    try:
        process = subprocess.run(
            argv,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=stdin_text
        )

        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "command": command,
            "exit_code": process.returncode,
            "stdout": process.stdout[-12000:],
            "stderr": process.stderr[-4000:],
        }

    except subprocess.TimeoutExpired as error:
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "command": command,
            "timed_out": True,
            "stdout": str(error.stdout or "")[-12000:],
            "stderr": str(error.stderr or "")[-4000:],
        }

    with (Path.home() / "kali-mcp" / "command-log.jsonl").open("a") as log:
        log.write(json.dumps(record) + "\n")

    return record


def _project_path(relative_path: str) -> Path:
    root = (Path.home() / "lab-projects" / "first-assessment").resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Path must stay inside the assessment folder")
    return target

@mcp.tool
def write_project_file(relative_path: str, content: str) -> str:
    """Write a report or checklist in the Kali assessment folder."""
    if len(content) > 100_000:
        raise ValueError("File exceeds 100,000 characters")
    target = _project_path(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    print(f"Wrote project file: {target}", flush=True)
    return str(target)

@mcp.tool
def read_project_file(relative_path: str) -> str:
    """Read a file from the Kali assessment folder."""
    target = _project_path(relative_path)
    return target.read_text()[:100_000]


@mcp.tool
def export_evidence(limit: int = 12) -> dict:
    """Save recent real command results as evidence for the assessment."""
    import json

    source = Path.home() / "kali-mcp" / "command-log.jsonl"
    records = [json.loads(line) for line in source.read_text().splitlines()]
    count = max(1, min(int(limit), 50))
    selected = records[-count:]
    first_number = len(records) - len(selected) + 1

    def as_code(value: object, maximum: int) -> str:
        text = str(value or "")
        clipped = text[:maximum]
        lines = clipped.splitlines() or ["(none)"]
        if len(text) > maximum:
            lines.append("[truncated]")
        return "\n".join("    " + line for line in lines)

    sections = ["# Kali assessment command evidence",
                "Generated from `~/kali-mcp/command-log.jsonl`."]

    for number, record in enumerate(selected, first_number):
        status = "timed out" if record.get("timed_out") else str(record.get("exit_code", "unknown"))
        sections.extend([
            f"## C{number:04d}",
            f"Recorded: {record.get('time', 'unknown')}",
            f"Exit status: {status}",
            "Command:",
            as_code(record.get("command"), 1000),
            "Stdout:",
            as_code(record.get("stdout"), 4000),
            "Stderr:",
            as_code(record.get("stderr"), 2000),
        ])

    target = _project_path("evidence.md")
    target.write_text("\n\n".join(sections) + "\n")
    print(f"Exported {len(selected)} command records to {target}", flush=True)
    return {"path": str(target), "records": len(selected)}

if __name__ == "__main__":
    mcp.run(transport="http", host="192.168.56.101", port=8765, path="/mcp")