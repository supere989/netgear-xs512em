# netgear-xs512em

**Pure-Python control of the NETGEAR XS512EM Smart Managed Plus switch — a real API for a switch that doesn't have one.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

The XS512EM (12-port 10G/Multi-Gig "Smart Managed Plus") ships with **no SSH, Telnet, SNMP, or REST API** — your only options are a clunky web UI and a read-only discovery protocol. That makes it painful to automate and impossible to put under version control.

This project reverse-engineers the switch's web UI down to its underlying HTTP form API and wraps it in a clean, deterministic interface: a **Python library**, a **CLI**, and an **[MCP](https://modelcontextprotocol.io) server**. VLANs, port membership, and PVIDs become a few lines of code or a single command — no browser, no clicking.

> **Not affiliated with NETGEAR.** This is independent interoperability tooling for managing *your own* switch. Use at your own risk; see [Disclaimer](#disclaimer).

---

## Features

- 🔌 **No browser required** — talks directly to the switch's authenticated HTTP endpoints.
- 🧱 **802.1Q VLAN management** — enable Advanced 802.1Q, create VLANs, set per-port tagged/untagged membership and PVIDs.
- 👀 **Read state** — VLAN table, per-port PVIDs, per-port link status.
- 🤖 **MCP server** — drive the switch from any MCP client (e.g. Claude Code) with typed tools.
- 🔐 **Credentials stay local** — password via env var, file, or prompt; never hard-coded, never logged.
- 🪶 **Tiny footprint** — one runtime dependency (`requests`); the MCP server is an optional extra.

## Supported operations

| Operation | Library | CLI | MCP tool |
|---|---|---|---|
| Read VLAN membership | `read_vlans()` | `read-vlans` | `xs512_read_vlans` |
| Read port PVIDs | `read_pvids()` | `read-pvids` | `xs512_read_pvids` |
| Read port link status | `read_port_status()` | `read-port-status` | `xs512_read_port_status` |
| Enable Advanced 802.1Q | `enable_advanced_8021q()` | `enable-8021q` | `xs512_enable_advanced_8021q` |
| Create VLAN | `create_vlan(id)` | `create-vlan` | `xs512_create_vlan` |
| Set VLAN membership | `set_membership(...)` | `set-membership` | `xs512_set_vlan_membership` |
| Set port PVID | `set_pvid(...)` | `set-pvid` | `xs512_set_pvid` |

## Install

```bash
pip install git+https://github.com/supere989/netgear-xs512em
# with the MCP server:
pip install "netgear-xs512em[mcp] @ git+https://github.com/supere989/netgear-xs512em"
```

The machine running this must be on the same L2 segment as the switch's management IP.

## Configuration

| Setting | How |
|---|---|
| Host | `--host`, or `XS512EM_HOST` |
| Password | `XS512EM_PASSWORD`, `XS512EM_PASSWORD_FILE`, `--password-file`, or interactive prompt |

```bash
export XS512EM_HOST=192.168.0.239
export XS512EM_PASSWORD='your-admin-password'
```

## Quickstart

### CLI

```bash
xs512em read-vlans
xs512em read-port-status

# Build an isolated VLAN 10 on ports 1 and 5 (access ports):
xs512em create-vlan 10
xs512em set-membership 10 --untagged 1,5
xs512em set-pvid 1,5 10
```

### Python

```python
from netgear_xs512em import XS512EM

with XS512EM("192.168.0.239", password="...") as sw:   # logs out on exit
    print(sw.read_vlans())                  # {1: [1, 2, ...], 10: [1, 5]}
    sw.create_vlan(20)
    sw.set_membership(20, tagged=[1], untagged=[2])
    sw.set_pvid([2], 20)
```

### MCP server (Claude Code, etc.)

```bash
XS512EM_HOST=192.168.0.239 XS512EM_PASSWORD='...' \
    claude mcp add --scope user xs512em -- xs512em-mcp
```

Then ask your agent to read or change the switch with the `xs512_*` tools.

## How it works

Under the GUI, the switch is an authenticated HTTP form API: login is
`md5(merge(password, rand))` → a `Gambit` session token (no cookies), and each
operation is a single `POST` to an `/iss/specific/*.html` endpoint. Port membership
is a 12-character positional string (`1`=untagged, `2`=tagged, `3`=not-member).

The full decomposition — login flow, endpoints, field formats — is documented in
**[docs/PROTOCOL.md](docs/PROTOCOL.md)**.

## Safety notes

- **Single session.** The switch allows only one management session at a time. The client
  always logs out (it's a context manager); don't run two operations concurrently.
- **`enable-8021q` erases VLAN settings.** Enabling Advanced 802.1Q resets every port to
  untagged VLAN 1 — by design of the switch firmware. Read the current config first.
- **Moving a port between VLANs** can cut traffic on that port mid-change; set membership and
  PVID together, and verify after.

## Compatibility

Developed and tested against the **XS512EM** (firmware `1.0.2.8`). Other NETGEAR "Smart Managed
Plus" / "Plus" switches share much of this web stack, so the approach may port with small tweaks —
reports and PRs welcome. See [docs/PROTOCOL.md](docs/PROTOCOL.md) for what to check.

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Especially useful: confirmations
on other switch models, the `delete-vlan` payload, and a robust PVID/port-speed parser.

## Disclaimer

This software is provided "as is", without warranty of any kind. It is **not affiliated with,
endorsed by, or supported by NETGEAR, Inc.** "NETGEAR" and "XS512EM" are trademarks of their
respective owner, used here only to describe compatibility. You are responsible for any changes
you make to your own equipment.

## License

[MIT](LICENSE) © supere989
