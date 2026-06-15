"""MCP server exposing the NETGEAR XS512EM switch as typed tools.

Supports three transports (MCP spec): **stdio** (default, local), **streamable-http**
(the current spec remote transport — single ``/mcp`` endpoint, SSE upgrade for
streaming), and legacy **sse** (``/sse`` + ``/messages``). Run it once as a remote
service so every Claude/CLI instance shares ONE endpoint instead of each spawning a
local stdio copy.

Configure via environment:

  * ``XS512EM_HOST`` — switch IP/hostname (required)
  * ``XS512EM_PASSWORD`` or ``XS512EM_PASSWORD_FILE`` — admin credential (required)
  * ``MCP_TRANSPORT`` — ``stdio`` | ``streamable-http`` | ``http`` (alias) | ``sse``  (default ``stdio``)
  * ``MCP_HOST`` / ``MCP_PORT`` — bind address for the HTTP transports (default ``0.0.0.0:8765``)
  * ``XS512EM_MCP_TOKEN`` — if set, HTTP clients must send ``Authorization: Bearer <token>``
  * ``MCP_ALLOWED_HOSTS`` — comma list to enable DNS-rebinding host-validation (default: off
    for a shared endpoint — the bearer token + network boundary are the access controls)

Local (stdio) registration::

    XS512EM_HOST=10.150.1.239 XS512EM_PASSWORD_FILE=~/sudo_auth.key \
        claude mcp add --scope user xs512em -- xs512em-mcp

Remote (streamable-http) — run once on the tool-hub, then point clients at it::

    XS512EM_HOST=10.150.1.239 XS512EM_PASSWORD_FILE=/etc/xs512em/pw \
    XS512EM_MCP_TOKEN=$(cat /etc/xs512em/token) \
        xs512em-mcp --transport http --host 0.0.0.0 --port 8765
    # client:
    claude mcp add --transport http xs512em http://<hub>:8765/mcp \
        --header "Authorization: Bearer <token>"

The switch allows ONE management session at a time, so every tool call is a full
login → act → logout AND is serialised behind a process-wide mutex — safe to expose
to multiple concurrent clients.
"""
from __future__ import annotations

import contextlib
import os
import sys
import threading

from .client import XS512EM

# The switch permits a single management session at a time. Serialise every
# operation across all concurrent MCP clients so we never trip "max sessions".
_SWITCH_LOCK = threading.Lock()
_LOCK_TIMEOUT = float(os.environ.get("XS512EM_LOCK_TIMEOUT", "45"))


def _host() -> str:
    host = os.environ.get("XS512EM_HOST")
    if not host:
        raise RuntimeError("XS512EM_HOST is not set")
    return host


@contextlib.contextmanager
def _switch():
    """Yield a logged-in switch client while holding the global single-session lock."""
    if not _SWITCH_LOCK.acquire(timeout=_LOCK_TIMEOUT):
        raise RuntimeError(
            "switch busy: another management operation is in progress — retry shortly"
        )
    try:
        with XS512EM(_host()) as sw:
            yield sw
    finally:
        _SWITCH_LOCK.release()


def build_server(transport_security=None):
    """Construct and return the FastMCP server (imported lazily so the core stays dependency-light)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "the MCP server needs the 'mcp' package — install with: pip install 'netgear-xs512em[mcp]'"
        ) from e

    mcp = FastMCP("xs512em", transport_security=transport_security)

    @mcp.tool()
    def xs512_read_vlans() -> dict:
        """Read the 802.1Q VLAN membership table. Returns {vlan_id: [member_ports]}."""
        with _switch() as sw:
            return {"vlans": sw.read_vlans()}

    @mcp.tool()
    def xs512_read_pvids() -> dict:
        """Read each port's PVID (untagged-ingress VLAN). Returns {port: pvid}."""
        with _switch() as sw:
            return {"pvids": sw.read_pvids()}

    @mcp.tool()
    def xs512_read_port_status() -> dict:
        """Read each port's link state. Returns {port: 'Up'|'Down'}.
        Tip: to map a device to its switch port, flap the device's NIC and diff this."""
        with _switch() as sw:
            return {"port_status": sw.read_port_status()}

    @mcp.tool()
    def xs512_enable_advanced_8021q() -> dict:
        """Enable Advanced 802.1Q VLAN mode. WARNING: this ERASES all current VLAN settings."""
        with _switch() as sw:
            return {"http_status": sw.enable_advanced_8021q()}

    @mcp.tool()
    def xs512_create_vlan(vlan_id: int) -> dict:
        """Create an 802.1Q VLAN by id (no members yet). Returns the VLAN table after."""
        with _switch() as sw:
            code = sw.create_vlan(vlan_id)
            return {"http_status": code, "vlans": sw.read_vlans()}

    @mcp.tool()
    def xs512_set_vlan_membership(vlan_id: int, untagged: list[int] | None = None,
                                  tagged: list[int] | None = None) -> dict:
        """Replace a VLAN's port membership. untagged = access ports, tagged = trunk ports;
        any port not listed becomes a non-member. Set matching PVIDs with xs512_set_pvid."""
        with _switch() as sw:
            r = sw.set_membership(vlan_id, untagged=tuple(untagged or ()), tagged=tuple(tagged or ()))
            return {**r, "vlans": sw.read_vlans()}

    @mcp.tool()
    def xs512_set_pvid(ports: list[int], pvid: int) -> dict:
        """Set the PVID for one or more ports (they must already be members of that VLAN)."""
        with _switch() as sw:
            return sw.set_pvid(ports, pvid)

    return mcp


# --------------------------------------------------------------------------- #
# HTTP transports (streamable-http / sse) with optional bearer auth + health
# --------------------------------------------------------------------------- #
class _HealthAndAuth:
    """Thin ASGI wrapper: always answers ``/healthz`` (unauthenticated, for
    container/uptime probes) and, if a token is configured, requires
    ``Authorization: Bearer <token>`` on every other HTTP request. Non-HTTP
    scopes (lifespan, websocket) pass straight through so the MCP session
    manager's lifespan runs normally."""

    def __init__(self, app, token: str | None):
        self.app = app
        self._expected = f"Bearer {token}" if token else None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path", "").rstrip("/") in ("/healthz", "/health"):
            await self._plain(send, 200, b"ok")
            return
        if self._expected is not None:
            headers = {k.lower(): v for k, v in scope.get("headers") or []}
            if headers.get(b"authorization", b"").decode() != self._expected:
                await self._plain(send, 401, b"unauthorized")
                return
        await self.app(scope, receive, send)

    @staticmethod
    async def _plain(send, status: int, body: bytes):
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def _transport_security():
    """DNS-rebinding protection for the HTTP transports. A *shared* remote endpoint is
    reached by IP/hostname (not localhost), so the SDK's default host-validation rejects
    it (HTTP 421 Misdirected Request). Set ``MCP_ALLOWED_HOSTS`` (comma list, e.g.
    ``10.150.1.201:8765,switch-mcp.lan:8765``) to enforce an allowlist; otherwise we
    disable host-validation and rely on the bearer token + network boundary."""
    from mcp.server.transport_security import TransportSecuritySettings
    hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    origins = [o.strip() for o in os.environ.get("MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if hosts:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=origins or ["*"],
        )
    return TransportSecuritySettings(enable_dns_rebinding_protection=False)


def serve_http(transport: str, host: str, port: int, token: str | None = None) -> None:
    """Serve the MCP server over an HTTP transport via uvicorn."""
    import uvicorn

    server = build_server(_transport_security())
    server.settings.host = host
    server.settings.port = port
    app = server.sse_app() if transport == "sse" else server.streamable_http_app()
    app = _HealthAndAuth(app, token)

    endpoint = "/sse" if transport == "sse" else "/mcp"
    print(
        f"[xs512em-mcp] transport={transport} bind={host}:{port}{endpoint} "
        f"auth={'bearer' if token else 'NONE (open on the bound interface!)'} "
        f"switch={os.environ.get('XS512EM_HOST', '<unset!>')}",
        file=sys.stderr, flush=True,
    )
    uvicorn.run(app, host=host, port=port, log_level=os.environ.get("MCP_LOG_LEVEL", "info"))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="xs512em-mcp",
        description="MCP server for the NETGEAR XS512EM switch (stdio / streamable-http / sse).",
    )
    parser.add_argument("--transport", default=os.environ.get("MCP_TRANSPORT", "stdio"),
                        choices=["stdio", "streamable-http", "http", "sse"],
                        help="MCP transport (default: stdio). 'http' is an alias for 'streamable-http'.")
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "0.0.0.0"),
                        help="bind address for HTTP transports (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8765")),
                        help="bind port for HTTP transports (default: 8765)")
    args = parser.parse_args()

    transport = "streamable-http" if args.transport == "http" else args.transport
    if transport == "stdio":
        build_server().run()
    else:
        serve_http(transport, args.host, args.port, os.environ.get("XS512EM_MCP_TOKEN"))


if __name__ == "__main__":
    main()
