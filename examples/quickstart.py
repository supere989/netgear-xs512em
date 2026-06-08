#!/usr/bin/env python3
"""Minimal example: read state, then build an isolated VLAN on two access ports.

Run with credentials in the environment:

    export XS512EM_HOST=192.168.0.239
    export XS512EM_PASSWORD='your-admin-password'
    python examples/quickstart.py
"""
import os

from netgear_xs512em import XS512EM

HOST = os.environ["XS512EM_HOST"]          # e.g. "192.168.0.239"
VLAN = 10
ACCESS_PORTS = [1, 5]

with XS512EM(HOST) as sw:                   # password from XS512EM_PASSWORD; logs out on exit
    print("VLANs before:", sw.read_vlans())
    print("Port status :", sw.read_port_status())

    # Create an isolated VLAN with two untagged (access) ports.
    sw.create_vlan(VLAN)
    sw.set_membership(VLAN, untagged=ACCESS_PORTS)
    sw.set_pvid(ACCESS_PORTS, VLAN)

    print("VLANs after :", sw.read_vlans())
