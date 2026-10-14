# Changelog

All notable changes to Scylla are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Reframed the repository as a **project debrief** on LLM reasoning applied to
  offensive security, rather than a usage manual.
- `docs/the-persistent-terminal-problem.md`: the centerpiece write-up of the
  core engineering challenge (stateful shell vs. stateless inference).
- Architecture overview showing the host → VM → Kali → MCP-server topology and
  the single authenticated channel between them.
- Security policy, contributing guide, and a `docs/` reference set.

## [0.1.0] - 2026-10-13

### Added
- Initial MCP server (`mcp-server.py`) built on FastMCP with static bearer-token auth.
- Persistent Bash PTY terminal with interactive I/O (`terminal`, `terminal_read`,
  `terminal_input`, `reset_terminal`).
- Disposable one-shot command runner with JSONL audit logging.
- Named read-only diagnostics and a `kali_status` probe.
- Path-jailed project file I/O and Markdown evidence export.
- Autonomous assessment operating contract (`SystemPrompt.md`).
