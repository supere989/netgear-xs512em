# Contributing

Thanks for your interest! This project is small, focused, and welcomes improvements.

## Ways to help

- **Confirm other models.** If you have a sibling NETGEAR "Plus" / "Smart Managed Plus" switch,
  try the client and report what works. See [docs/PROTOCOL.md](docs/PROTOCOL.md#porting-to-other-models).
- **Fill the gaps.** Known TODOs: the `delete-vlan` POST payload, a robust PVID/port-speed parser,
  and a MAC-address-table read.
- **Bugs & docs.** Issues and small PRs are great.

## Ground rules

- **Never commit credentials or switch-specific addresses.** Configuration is by env var / flag /
  prompt for a reason — keep it that way. `*.key` and `.env` are gitignored.
- Keep the core dependency-light (`requests` only). MCP stays an optional extra.
- Match the existing style: type hints, clear docstrings, small functions.

## Dev setup

```bash
git clone https://github.com/supere989/netgear-xs512em
cd netgear-xs512em
python -m venv .venv && . .venv/bin/activate
pip install -e ".[mcp]"
```

## Reverse-engineering etiquette

This is interoperability tooling for hardware you own. When mapping new endpoints, observe the
switch's *own* web UI (browser dev-tools network tab, or the static `/function.js` / `/frame.js`).
Don't modify firmware. Document new findings in `docs/PROTOCOL.md`.
