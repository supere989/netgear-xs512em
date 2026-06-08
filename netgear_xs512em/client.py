"""
netgear_xs512em.client — pure-HTTP client for the NETGEAR XS512EM Smart Managed Plus switch.

The XS512EM exposes no SSH / Telnet / SNMP / REST API — only a web UI and NSDP. This client
talks to the same authenticated HTTP form endpoints the web UI uses, so you can manage the
switch deterministically from code instead of clicking through a browser.

Auth model (reverse-engineered):
  * ``GET /``               → scrape the ``rand`` nonce.
  * ``POST /redirect.html`` → ``LoginPassword = md5(merge(password, rand))`` returns a ``Gambit``
    session token in an auto-submit form. There is **no cookie** — the Gambit token *is* the session.
  * Authenticated requests carry ``Gambit`` (form field and/or query string).
  * ``GET /iss/specific/logout.html?Gambit=<token>`` ends the session.

Port membership is encoded as a 12-character positional string (``hiddenMem``), one digit per
port: ``1`` = untagged, ``2`` = tagged, ``3`` = not a member.

The switch allows **one management session at a time**. Use the class as a context manager so it
always logs out::

    from netgear_xs512em import XS512EM
    with XS512EM("192.168.0.239", password="...") as sw:
        print(sw.read_vlans())

See ``docs/PROTOCOL.md`` for the full decomposed API.
"""
from __future__ import annotations

import hashlib
import os
import re

import requests

# hiddenMem digit meanings
UNTAGGED = "1"
TAGGED = "2"
NONMEMBER = "3"

NUM_PORTS = 12


class SwitchError(RuntimeError):
    """Base error for switch communication failures."""


class AuthError(SwitchError):
    """Login failed or no credentials were provided."""


class SessionBusyError(SwitchError):
    """The switch already has an active management session (single-session limit)."""


def _merge(a: str, b: str) -> str:
    """Interleave two strings char-by-char: ``a0 b0 a1 b1 …`` (the NETGEAR login scramble)."""
    out, i, j = [], 0, 0
    while i < len(a) or j < len(b):
        if i < len(a):
            out.append(a[i])
            i += 1
        if j < len(b):
            out.append(b[j])
            j += 1
    return "".join(out)


def membership_string(untagged=(), tagged=(), nports: int = NUM_PORTS) -> str:
    """Build a ``hiddenMem`` string from 1-based port lists; unlisted ports become non-members."""
    s = [NONMEMBER] * nports
    for p in tagged:
        s[p - 1] = TAGGED
    for p in untagged:
        s[p - 1] = UNTAGGED
    return "".join(s)


def _resolve_password(password, password_file):
    """Resolve a password from (in order): explicit value, file, env var, env file path."""
    if password:
        return password
    if password_file:
        return open(os.path.expanduser(password_file)).read().rstrip("\r\n")
    if os.environ.get("XS512EM_PASSWORD"):
        return os.environ["XS512EM_PASSWORD"]
    if os.environ.get("XS512EM_PASSWORD_FILE"):
        return open(os.path.expanduser(os.environ["XS512EM_PASSWORD_FILE"])).read().rstrip("\r\n")
    raise AuthError(
        "no password supplied — pass password=…, password_file=…, "
        "or set XS512EM_PASSWORD / XS512EM_PASSWORD_FILE"
    )


class XS512EM:
    """Client for a NETGEAR XS512EM Smart Managed Plus switch.

    Args:
        host: switch IP or hostname (e.g. ``"192.168.0.239"``).
        password: admin password. If omitted, read from ``password_file`` or the
            ``XS512EM_PASSWORD`` / ``XS512EM_PASSWORD_FILE`` environment variables.
        password_file: path to a file whose contents are the password.
        timeout: per-request timeout in seconds.
    """

    def __init__(self, host: str, password: str | None = None, *,
                 password_file: str | None = None, timeout: int = 12):
        if not host:
            raise ValueError("host is required")
        self.host = host
        self.base = f"http://{host}"
        self.timeout = timeout
        self._password = _resolve_password(password, password_file)
        self.gambit: str | None = None
        self._session = requests.Session()

    # ------------------------------------------------------------------ session
    def __enter__(self) -> "XS512EM":
        self.login()
        return self

    def __exit__(self, *exc) -> None:
        self.logout()

    def login(self) -> str:
        """Authenticate and return the Gambit session token."""
        r = self._session.get(self.base + "/", timeout=self.timeout)
        m = re.search(r"id=['\"]?rand['\"]?\s+value=['\"]?(\d+)", r.text)
        if not m:
            raise AuthError("could not find the 'rand' nonce on the login page")
        digest = hashlib.md5(_merge(self._password, m.group(1)).encode()).hexdigest()
        r2 = self._session.post(self.base + "/redirect.html",
                                data={"LoginPassword": digest}, timeout=self.timeout)
        if "Maximum number of sessions" in r2.text:
            raise SessionBusyError(
                "switch reports 'Maximum number of sessions reached' — another session is open; "
                "wait for the idle timeout (a few minutes) and retry"
            )
        g = (re.search(r'name="Gambit"\s+value="([0-9a-z]+)"', r2.text)
             or re.search(r"Gambit=([0-9a-z]+)", r2.text))
        if not g:
            raise AuthError("login failed (no Gambit token returned) — check the password")
        self.gambit = g.group(1)
        # hand the token to homepage.html to establish the session (mirrors the browser)
        try:
            self._session.post(self.base + "/homepage.html",
                               data={"Gambit": self.gambit}, timeout=self.timeout)
        except requests.RequestException:
            pass
        return self.gambit

    def logout(self) -> None:
        """End the management session (safe to call when not logged in)."""
        if self.gambit:
            try:
                self._session.get(f"{self.base}/iss/specific/logout.html?Gambit={self.gambit}",
                                  timeout=6)
            except requests.RequestException:
                pass
            self.gambit = None

    # ------------------------------------------------------------------ helpers
    def _post(self, page: str, fields: dict) -> requests.Response:
        data = {"Gambit": self.gambit, **fields}
        return self._session.post(f"{self.base}/iss/specific/{page}?Gambit={self.gambit}",
                                  data=data, timeout=self.timeout)

    def _get(self, page: str) -> requests.Response:
        return self._session.get(f"{self.base}/iss/specific/{page}?Gambit={self.gambit}",
                                 timeout=self.timeout)

    # ------------------------------------------------------------------ reads
    def read_vlans(self) -> dict:
        """Return ``{vlan_id: [member_ports]}`` parsed from the VLAN configuration table."""
        html = self._get("Cf8021q.html").text
        out: dict[int, list[int]] = {}
        for vid, members in re.findall(
            r"<td[^>]*>\s*(\d+)\s*</td>\s*<td[^>]*>\s*([\d\s]+?)\s*</td>", html
        ):
            out[int(vid)] = [int(x) for x in members.split()]
        return out

    def read_pvids(self) -> dict:
        """Return ``{port: pvid}`` parsed from the Port PVID table (best-effort)."""
        html = self._get("vlan_pvidsetting.html").text
        out: dict[int, int] = {}
        for port, pvid in re.findall(r"Port\s*(\d+).*?value=['\"](\d+)['\"]", html, re.S):
            out.setdefault(int(port), int(pvid))
        return out

    def read_port_status(self) -> dict:
        """Return ``{port: 'Up'|'Down'}`` link state for all ports, in port order.

        Handy for mapping a device to its switch port: flap the device's NIC and diff this.
        """
        html = self._get("port_settings.html").text
        links = re.findall(r">\s*(Up|Down)\s*<", html)[:NUM_PORTS]
        return {i + 1: (links[i] if i < len(links) else None) for i in range(NUM_PORTS)}

    # ------------------------------------------------------------------ writes
    def enable_advanced_8021q(self) -> int:
        """Enable Advanced 802.1Q VLAN mode.

        WARNING: the switch ERASES all existing VLAN settings when this is enabled
        (every port returns to untagged VLAN 1). Returns the HTTP status code.
        """
        return self._post("Cf8021q.html", {"status": "Enable", "ACTION": ""}).status_code

    def create_vlan(self, vlan_id: int) -> int:
        """Create an 802.1Q VLAN by id (with no members yet). Returns the HTTP status code."""
        return self._post("Cf8021q.html",
                          {"status": "Enable", "ADD_VLANID": str(vlan_id), "ACTION": "Add"}).status_code

    def set_membership(self, vlan_id: int, untagged=(), tagged=()) -> dict:
        """Replace a VLAN's port membership.

        ``untagged`` ports egress untagged (access), ``tagged`` ports egress tagged (trunk),
        and any port not listed becomes a non-member. A port may be untagged in only one VLAN —
        set its PVID to match with :meth:`set_pvid`.
        """
        hidden = membership_string(untagged, tagged)
        r = self._post("vlanMembership.html",
                       {"VLAN_ID": str(vlan_id), "vlanIdSel": str(vlan_id),
                        "hiddenMem": hidden, "ACTION": ""})
        return {"status": r.status_code, "hiddenMem": hidden}

    def set_pvid(self, ports, pvid: int) -> dict:
        """Set the PVID (untagged-ingress VLAN) for one or more ports.

        The ports must already be members of ``pvid``'s VLAN (see :meth:`set_membership`),
        otherwise untagged frames will be dropped.
        """
        port_no = ports if isinstance(ports, str) else "".join(f"{p};" for p in ports)
        r = self._post("vlan_pvidsetting.html",
                       {"PORT_NO": port_no, "PORT_PVID": str(pvid), "ACTION": "Apply"})
        return {"status": r.status_code, "PORT_NO": port_no, "PORT_PVID": pvid}
