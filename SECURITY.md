# Security & Responsible Use

Scylla drives a real Kali Linux VM from an AI agent. Treat it accordingly.

## Authorized use only

Scylla is intended **exclusively** for:

- Capture-the-Flag (CTF) exercises, and
- security assessments against systems you own or have explicit written
  authorization to test.

Do **not** point Scylla at third-party systems, production infrastructure, or
any target outside a clearly authorized lab scope. The operating contract in
[`SystemPrompt.md`](./SystemPrompt.md) instructs the agent to treat only
user-supplied lab targets as in-scope and to avoid pivoting to unrelated
reachable systems, but ultimate responsibility rests with the operator.

## Built-in guardrails

- **Non-destructive validation.** The agent is directed to use the minimum
  action necessary to establish a vulnerability, and to *record*, not execute,
  destructive proofs (DoS, data corruption, service crashes).
- **Path jailing.** `write_project_file` / `read_project_file` resolve all paths
  against the assessment root and reject traversal outside it.
- **Token authentication.** The MCP server refuses requests without a valid
  bearer token loaded from `~/kali-mcp/token`.
- **Audit log.** Disposable commands are appended to an append-only JSONL log
  and can be exported as evidence.

These are safety rails, not a sandbox boundary. Run Scylla on an isolated lab
network, behind a host-only / NAT interface, on a VM you can discard.

## Operational recommendations

- Keep the Kali VM on a dedicated, isolated network segment.
- Rotate the auth token between engagements.
- Never commit `~/kali-mcp/` or `~/lab-projects/`; they are gitignored by default.
- Review the command log after each session.

## Reporting a vulnerability

If you find a security issue in Scylla itself, please open a private report
rather than a public issue, and allow reasonable time for a fix before
disclosure.
