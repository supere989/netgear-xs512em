"""MCP server exposing the NETGEAR XS512EM switch as typed tools.

Configure via environment before launching:

  * ``XS512EM_HOST`` — switch IP/hostname (required)
  * ``XS512EM_PASSWORD`` or ``XS512EM_PASSWORD_FILE`` — admin credential (required)

Register with an MCP client, e.g. Claude Code::

    XS512EM_HOST=192.168.0.239 XS512EM_PASSWORD=... \
        claude mcp add --scope user xs512em -- xs512em-mcp

Each tool runs a full login → act → logout (the switch allows one session at a time).
"""
from __future__ import annotations

import os

from .client import XS512EM


def _host() -> str:
    host = os.environ.get("XS512EM_HOST")
    if not host:
        raise RuntimeError("XS512EM_HOST is not set")
    return host


def build_server():
    """Construct and return the FastMCP server (imported lazily so the core stays dependency-light)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "the MCP server needs the 'mcp' package — install with: pip install 'netgear-xs512em[mcp]'"
        ) from e

    mcp = FastMCP("xs512em")

    @mcp.tool()
    def xs512_read_vlans() -> dict:
        """Read the 802.1Q VLAN membership table. Returns {vlan_id: [member_ports]}."""
        with XS512EM(_host()) as sw:
            return {"vlans": sw.read_vlans()}

    @mcp.tool()
    def xs512_read_pvids() -> dict:
        """Read each port's PVID (untagged-ingress VLAN). Returns {port: pvid}."""
        with XS512EM(_host()) as sw:
            return {"pvids": sw.read_pvids()}

    @mcp.tool()
    def xs512_read_port_status() -> dict:
        """Read each port's link state. Returns {port: 'Up'|'Down'}.
        Tip: to map a device to its switch port, flap the device's NIC and diff this."""
        with XS512EM(_host()) as sw:
            return {"port_status": sw.read_port_status()}

    @mcp.tool()
    def xs512_enable_advanced_8021q() -> dict:
        """Enable Advanced 802.1Q VLAN mode. WARNING: this ERASES all current VLAN settings."""
        with XS512EM(_host()) as sw:
            return {"http_status": sw.enable_advanced_8021q()}

    @mcp.tool()
    def xs512_create_vlan(vlan_id: int) -> dict:
        """Create an 802.1Q VLAN by id (no members yet). Returns the VLAN table after."""
        with XS512EM(_host()) as sw:
            code = sw.create_vlan(vlan_id)
            return {"http_status": code, "vlans": sw.read_vlans()}

    @mcp.tool()
    def xs512_set_vlan_membership(vlan_id: int, untagged: list[int] | None = None,
                                  tagged: list[int] | None = None) -> dict:
        """Replace a VLAN's port membership. untagged = access ports, tagged = trunk ports;
        any port not listed becomes a non-member. Set matching PVIDs with xs512_set_pvid."""
        with XS512EM(_host()) as sw:
            r = sw.set_membership(vlan_id, untagged=tuple(untagged or ()), tagged=tuple(tagged or ()))
            return {**r, "vlans": sw.read_vlans()}

    @mcp.tool()
    def xs512_set_pvid(ports: list[int], pvid: int) -> dict:
        """Set the PVID for one or more ports (they must already be members of that VLAN)."""
        with XS512EM(_host()) as sw:
            return sw.set_pvid(ports, pvid)

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
