# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [0.2.0] — 2026-06-15

### Added
- **Remote MCP transports:** `streamable-http` (current MCP spec, `/mcp`) and legacy `sse` (`/sse`),
  selectable via `--transport` / `MCP_TRANSPORT` (stdio stays the default). Bind with `--host/--port`
  or `MCP_HOST/MCP_PORT`.
- **Optional bearer auth** for the HTTP transports (`XS512EM_MCP_TOKEN`) plus an unauthenticated
  `GET /healthz` liveness probe.
- **Process-wide mutex** serialising every switch operation, so one shared remote endpoint is safe
  for concurrent clients despite the switch's single-session limit.
- Deployment artifacts: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, and the
  `deploy/xs512em-mcp.service` systemd unit.

### Changed
- `xs512em-mcp` now accepts CLI args / env for transport selection; the bare invocation is unchanged
  (stdio), so existing `claude mcp add … -- xs512em-mcp` registrations keep working.

## [0.1.0] — 2026-06-08

Initial public release.

### Added
- `XS512EM` HTTP client: login (`md5(merge(pw,rand))` → Gambit session), logout, single-session-safe context manager.
- Reads: `read_vlans`, `read_pvids`, `read_port_status`.
- Writes: `enable_advanced_8021q`, `create_vlan`, `set_membership`, `set_pvid`.
- `xs512em` CLI and `xs512em-mcp` MCP server (optional `[mcp]` extra).
- `docs/PROTOCOL.md` documenting the reverse-engineered web API.

### Known gaps
- `delete_vlan` payload not yet captured.
- PVID / port-speed parsing is best-effort (nested HTML tables).
- No MAC-address-table read yet.
