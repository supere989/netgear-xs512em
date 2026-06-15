export const meta = {
  name: 'network-estate-audit',
  description: 'Read-only full audit of every host/VM/VPS/VLAN/VPN/device, then synthesize a master network map',
  phases: [
    { title: 'Audit', detail: 'one read-only agent per node/host/VPS/switch + a device-discovery sweep' },
    { title: 'Synthesize', detail: 'merge all results into the master estate map' },
  ],
}

const NIC = {type:'object', properties:{name:{type:'string'},mac:{type:'string'},speed:{type:'string'},state:{type:'string'},port_type:{type:'string'},driver:{type:'string'},pci:{type:'string'},model:{type:'string'},sfp:{type:'string'},master:{type:'string'},mtu:{type:'string'},ips:{type:'string'}}, required:['name']}
const AUDIT_SCHEMA = {type:'object', properties:{
  target:{type:'string'}, reachable:{type:'boolean'}, access:{type:'string'},
  system:{type:'object', properties:{hostname:{type:'string'},os:{type:'string'},make:{type:'string'},model:{type:'string'},serial:{type:'string'},role:{type:'string'}}},
  nics:{type:'array', items:NIC},
  bridges:{type:'array', items:{type:'object', properties:{name:{type:'string'},members:{type:'string'},stp:{type:'string'},vlan_aware:{type:'string'},ips:{type:'string'}}}},
  bonds:{type:'array', items:{type:'object', properties:{name:{type:'string'},mode:{type:'string'},members:{type:'string'}}}},
  routes:{type:'array', items:{type:'string'}},
  vpn:{type:'array', items:{type:'object', properties:{type:{type:'string'},iface:{type:'string'},detail:{type:'string'}}}},
  guests:{type:'array', items:{type:'object', properties:{vmid:{type:'string'},name:{type:'string'},status:{type:'string'},nics:{type:'string'}}}},
  neighbors:{type:'array', items:{type:'string'}},
  dhcp_leases:{type:'array', items:{type:'string'}},
  issues:{type:'array', items:{type:'string'}},
  notes:{type:'string'}
}, required:['target','reachable']}

const SYNTH_SCHEMA = {type:'object', properties:{
  summary:{type:'string'}, hosts_audited:{type:'number'}, devices_found:{type:'number'},
  subnets:{type:'array', items:{type:'string'}}, vlans:{type:'array', items:{type:'string'}}, vpns:{type:'array', items:{type:'string'}},
  key_issues:{type:'array', items:{type:'string'}}, port_recommendations:{type:'array', items:{type:'string'}},
  open_questions:{type:'array', items:{type:'string'}}, artifacts:{type:'array', items:{type:'string'}}
}, required:['summary']}

const SEED = `ESTATE SEED (confirmed): PVE cluster pve-cluster quorate 3/3 — pve=10.150.1.251 (tailnet pve-1 100.123.3.84, Supermicro), pve1=10.150.1.252 (tailnet pve1 100.126.75.119), pve2=10.150.1.253 (LAN only, ROUTER/PERIMETER host, keep role). Gateway 10.150.1.1 MAC bc:24:11:10:91:4c = a Proxmox virtual NIC => router is a VM (ipfire VM107 / opnsense). Switch NETGEAR XS512EM 10.150.1.239 (44:a5:6e). Subnets: 10.150.1.0/24 (VLAN1), 10.150.2.0/24 (10G vmbr10gwin), 192.168.250.0/24 (pve1 vmbr1); switch VLAN10=ports 1,5,8. VPN: Tailscale tailnet supere989@ (100.64.0.0/10). Probing+read authorized in 10.150.1.0/24, 10.150.2.0/24, 100.0.0.0/8.`

const COMMON = `You perform a STRICTLY READ-ONLY audit of ONE target as part of a full network-estate map. NEVER modify anything (no set/add/create/delete/ifreload/ip link set/systemctl/reboot — read-only commands ONLY). Use short ssh timeouts (-o BatchMode=yes -o ConnectTimeout=8) and do not hang; if a command needs a tty or sudo you don't have, skip it and note it.
${SEED}
COLLECT and return the structured object:
- system: hostname, os/version, make, model, serial, vendor — Linux+root: 'dmidecode -t system' and '-t baseboard' (serial/product), 'lshw -short'; Windows: powershell 'Get-CimInstance Win32_ComputerSystem,Win32_BIOS,Win32_BaseBoard'. Set system.role (hypervisor/router/firewall/workstation/fileserver/vps/switch/etc).
- nics: EVERY interface (physical+virtual): name, mac, speed, state, port_type (ethtool: Twisted Pair/Direct Attach Copper/FIBRE), driver, pci ('lspci -nnk' for NICs), model, sfp ('ethtool -m' identifier/vendor/PN if an SFP module is present), master (bond/bridge), mtu, ips.
- bridges (name/members/stp/vlan_aware/ips), bonds (name/mode/members).
- routes: 'ip route' + 'ip -6 route' (or Windows 'route print'/'Get-NetRoute').
- vpn: 'tailscale status --json' (summarize self + peers/exit-nodes/subnet-routes), 'wg show' if WireGuard present.
- neighbors: 'ip neigh' (skip FAILED) or Windows 'Get-NetNeighbor'.
- PROXMOX NODES ONLY: for EVERY guest run 'qm config <vmid>' (and 'pct config <id>' for LXC); extract each netN: bridge, tag (=VLAN), macaddr, model, firewall — put one row per guest in guests[] with nics as a compact string. Get vmids from 'qm list' and 'pct list'.
- ROUTER/FIREWALL targets (pve2 and its VMs 105/106/107, the .1 gateway VM): ALSO capture routing/NAT/forwarding (sysctl net.ipv4.ip_forward, iptables/nft summary), firewall zones, WAN iface, and DHCP leases (dnsmasq/kea/isc leases file, or ipfire/opnsense lease list) into dhcp_leases[].
- issues: flag loops, STP-off with redundant links, duplicate IP/MAC, speed/duplex mismatch, MTU mismatch, anything odd.
Then: 'mkdir -p /home/raymondj/ops/12-network-audit/raw' and write your full result as pretty JSON to /home/raymondj/ops/12-network-audit/raw/<KEY>.json. Then RETURN the same object. If the target is unreachable after a genuine attempt, set reachable=false and explain in notes (still write the file).`

const TARGETS = [
 {key:'procreator', label:'procreator (this Garuda box, daily driver)', access:'LOCAL — you are ON procreator; run commands directly (no ssh). It has enp12s0 10GBASE-T 10.150.1.128, enp11s0 down, tailscale0.'},
 {key:'pve', label:'pve node (hypervisor; VMs 100 Win2022, 101 LinuxProxy)', access:'ssh root@10.150.1.251'},
 {key:'pve1', label:'pve1 node (hypervisor; many guests; vmbr0 1G+SFP+, vmbr10gwin 10G, vmbrOPNLAN/WAN, vmbr1)', access:'ssh root@pve1 (10.150.1.252)'},
 {key:'pve2', label:'pve2 node (ROUTER/PERIMETER hypervisor — AUDIT DEEPEST incl its firewall/router VMs 105 crowdsec-dns-fw, 106 dns-knot, 107 ipfire-edge-fw, 500 openclaw-host)', access:'ssh root@10.150.1.253 ; also inspect the router VMs via qm config and, if the .1 gateway VM lives here, its NAT/DHCP/firewall'},
 {key:'nobara-pc', label:'nobara-pc (old workstation, Nobara)', access:'ssh nobara (raymond@10.150.1.8); use sudo -n only if passwordless, else skip privileged bits'},
 {key:'rtx2080', label:'rtx2080 / desktop-kdlbae7 (Windows, RTX 2080 training box)', access:'ssh rtx2080 ; WINDOWS — use powershell Get-NetAdapter|Get-NetIPConfiguration|Get-NetRoute|Get-CimInstance'},
 {key:'rtx2080-wsl', label:'rtx2080-wsl / raymond-wsl (WSL2 Linux on the RTX2080 box)', access:'ssh rtx2080-wsl'},
 {key:'aiq-fs-001', label:'aiq-fs-001 file server (Windows, 10.150.1.58)', access:'ssh raymond@10.150.1.58 ; WINDOWS powershell as above'},
 {key:'switch-xs512em', label:'NETGEAR XS512EM 12-port 10G/MultiGig switch', access:'NO ssh. Run SEQUENTIALLY (single-session switch, login->act->logout each): /home/raymondj/projects/netgear-xs512em/.venv/bin/xs512em --host 10.150.1.239 --password-file /home/raymondj/sudo_auth.key read-vlans ; then read-pvids ; then read-port-status. Represent each switch port as a nics[] entry (name=port N, state=up/down) and record VLAN membership + PVID in notes/bridges. role=switch.'},
 {key:'vps-hetzner-alma', label:'alma-8gb-hel1-1 (Hetzner VPS, Tailscale exit node)', access:'ssh root@alma-8gb-hel1-1 (or root@100.80.149.11)'},
 {key:'vps-openclaw', label:'openclaw (Hetzner VPS, Tailscale exit node)', access:'ssh root@openclaw (or root@100.66.12.57)'},
 {key:'vps-valheim', label:'valheim-playmods-hil1 (Hetzner game-server VPS)', access:'ssh root@valheim-playmods-hil1 (or root@100.101.57.114)'},
 {key:'vps-vultr', label:'Vultr / webhost VPS', access:'try ssh aliases from ~/.ssh/config: vultr , vultr-raymond , webhost — audit each that connects; if multiple, list them all in notes and audit the primary.'},
 {key:'vps-activeiq', label:'active-iq.com hosts (chat, dns)', access:'try ssh aliases chat.active-iq.com and dns.active-iq.com from ~/.ssh/config; audit each that connects.'},
 {key:'net-discovery', label:'subnet sweep + connected-device discovery (incl unmanaged/IoT)', access:'LOCAL on procreator. Discover EVERY device on 10.150.1.0/24, 10.150.2.0/24, 192.168.250.0/24. Prefer: nmap -sn (and -Pn -p 22,80,443,3389 for ICMP-blocking Windows). If nmap absent, do a ping-sweep loop then read ip neigh. ALSO ssh root@10.150.1.251/.252/.253 and run ip neigh to harvest their ARP tables. Resolve each MAC OUI to a vendor (first 3 octets). Put one device per neighbors[] entry: "<ip> <mac> <vendor> <hostname-if-known> <subnet>". role=discovery.'},
]

phase('Audit')
const results = await parallel(TARGETS.map(t => () =>
  agent(`${COMMON}\n\n=== YOUR TARGET: ${t.label} ===\nKEY (filename + target field) = "${t.key}"\nAccess: ${t.access}`,
    {label:`audit:${t.key}`, phase:'Audit', schema:AUDIT_SCHEMA})
))
const ok = results.filter(Boolean)
const reach = ok.filter(r=>r.reachable).length
log(`Audit complete: ${ok.length}/${TARGETS.length} agents returned, ${reach} reachable. Synthesizing...`)

phase('Synthesize')
const synth = await agent(
`You are the network-estate-map SYNTHESIZER. Build ONE authoritative map of the whole estate.
1) Read ALL raw files: 'cat /home/raymondj/ops/12-network-audit/raw/'*.json (they are per-host audit results). Also use the inline DATA below as backup.
2) Produce /home/raymondj/ops/12-network-audit/master-map.md — a thorough Markdown document with: (a) an estate overview; (b) a per-host section (make/model/serial/role, every NIC with MAC/speed/port-type/SFP, bridges/bonds, IPs); (c) a DEVICE INVENTORY table of every discovered device (IP, MAC, vendor, host, subnet); (d) VLAN map (which VLAN = which subnet = which ports/ifaces/guests); (e) VPN map (Tailscale peers/exit-nodes/subnet-routes, any WireGuard); (f) CURRENT ROUTING TOPOLOGY (who is the gateway/router, NAT, inter-subnet paths, the pve2 perimeter role); (g) a PER-PORT table for the pve nodes + the XS512EM switch (port -> current use -> link speed -> VLAN); (h) an ISSUES section (the eno7/eno8 loop in pve1 vmbr0 with STP off; any duplicate/mismatch/misconfig found).
3) Write a machine-readable /home/raymondj/ops/12-network-audit/inventory.json (hosts[], devices[], vlans[], vpns[], links[]).
4) RETURN the structured summary (counts, subnets, vlans, vpns, key_issues, port_recommendations = first-pass thoughts on best use of each link/port keeping pve2 as router, open_questions to ask the operator before the deployment phase, and artifacts = files written).
INLINE DATA (per-host audit JSON):\n${JSON.stringify(ok).slice(0, 140000)}`,
  {label:'synthesize', phase:'Synthesize', schema:SYNTH_SCHEMA})

return synth