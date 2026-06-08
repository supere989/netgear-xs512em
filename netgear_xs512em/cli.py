"""Command-line interface for the NETGEAR XS512EM switch.

Examples::

    export XS512EM_HOST=192.168.0.239
    export XS512EM_PASSWORD='your-admin-password'   # or use --password-file / be prompted

    xs512em read-vlans
    xs512em read-port-status
    xs512em create-vlan 10
    xs512em set-membership 10 --untagged 1,5
    xs512em set-pvid 1,5 10
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from . import __version__
from .client import XS512EM, SwitchError


def _ports(value: str) -> list[int]:
    """Parse '1,5,8' (or '1;5;8') into [1, 5, 8]."""
    return [int(p) for p in value.replace(";", ",").split(",") if p.strip()]


def _connect(args) -> XS512EM:
    host = args.host or os.environ.get("XS512EM_HOST")
    if not host:
        raise SystemExit("error: no host — pass --host or set XS512EM_HOST")
    password = None
    if not args.password_file and not os.environ.get("XS512EM_PASSWORD") \
            and not os.environ.get("XS512EM_PASSWORD_FILE"):
        password = getpass.getpass(f"Password for {host}: ")
    return XS512EM(host, password=password, password_file=args.password_file)


def _emit(obj) -> None:
    print(json.dumps(obj, indent=2))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="xs512em", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", help="switch IP/hostname (or set XS512EM_HOST)")
    p.add_argument("--password-file", help="file containing the admin password")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("read-vlans", help="show VLAN membership table")
    sub.add_parser("read-pvids", help="show per-port PVID")
    sub.add_parser("read-port-status", help="show per-port link state")
    sub.add_parser("enable-8021q", help="enable Advanced 802.1Q (ERASES all VLAN settings)")

    c = sub.add_parser("create-vlan", help="create a VLAN id")
    c.add_argument("vlan_id", type=int)

    m = sub.add_parser("set-membership", help="replace a VLAN's port membership")
    m.add_argument("vlan_id", type=int)
    m.add_argument("--untagged", type=_ports, default=[], help="comma-separated ports")
    m.add_argument("--tagged", type=_ports, default=[], help="comma-separated ports")

    pv = sub.add_parser("set-pvid", help="set PVID for ports")
    pv.add_argument("ports", type=_ports, help="comma-separated ports, e.g. 1,5")
    pv.add_argument("pvid", type=int)

    args = p.parse_args(argv)

    try:
        with _connect(args) as sw:
            if args.cmd == "read-vlans":
                _emit(sw.read_vlans())
            elif args.cmd == "read-pvids":
                _emit(sw.read_pvids())
            elif args.cmd == "read-port-status":
                _emit(sw.read_port_status())
            elif args.cmd == "enable-8021q":
                _emit({"http_status": sw.enable_advanced_8021q()})
            elif args.cmd == "create-vlan":
                _emit({"http_status": sw.create_vlan(args.vlan_id), "vlans": sw.read_vlans()})
            elif args.cmd == "set-membership":
                r = sw.set_membership(args.vlan_id, untagged=args.untagged, tagged=args.tagged)
                _emit({**r, "vlans": sw.read_vlans()})
            elif args.cmd == "set-pvid":
                _emit(sw.set_pvid(args.ports, args.pvid))
    except SwitchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
