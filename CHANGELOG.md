# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

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
