# Contributing to Scylla

Thanks for your interest in improving Scylla. This is an experimental project,
so contributions of all sizes are welcome.

## Ground rules

- Scylla is a tool for **authorized** security work. Contributions that are
  primarily designed to facilitate unauthorized access, evade detection for
  malicious purposes, or enable mass/indiscriminate targeting will not be
  accepted.
- Keep the MCP tool surface small, explicit, and auditable. New tools should
  have a clear purpose and sane limits.

## Development setup

```bash
git clone <your-fork-url>
cd Scylla
python -m venv .venv && source .venv/bin/activate
pip install fastmcp
```

Scylla is designed to run on the Kali VM it controls. For local iteration you
can run the server anywhere, but tool calls that touch Kali utilities assume a
Kali-like environment.

## Making changes

1. Branch from `main`.
2. Keep changes focused; one logical change per PR.
3. Match the existing style; the server is intentionally dependency-light and
   readable.
4. Update [`docs/tools.md`](./docs/tools.md) and the README tool table if you
   add, remove, or change a tool.
5. Note user-facing changes in [`CHANGELOG.md`](./CHANGELOG.md).

## Pull requests

- Describe **what** changed and **why**.
- Call out any change to the safety model or tool surface explicitly.
- Confirm you tested against a lab/CTF target you are authorized to use.

## Reporting bugs

Open an issue with: what you expected, what happened, the relevant tool call(s),
and your environment (OS, Python version, FastMCP version).
