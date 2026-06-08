# XS512EM Web API — reverse-engineered protocol

The NETGEAR XS512EM has no SSH/SNMP/REST interface. Its web UI, however, is a thin JavaScript
layer over plain HTTP form `POST`s. This document describes that underlying API so the behaviour
is auditable and portable. Everything here was derived by observing the switch's own web UI talking
to itself; no firmware was modified.

All paths are relative to `http://<switch-ip>`.

## Authentication

There are **no cookies** — a per-session **`Gambit`** token *is* the session, threaded through
query strings and form fields.

1. `GET /` — the login page embeds a numeric nonce: `<input ... id="rand" value="<rand>">`.
2. Compute `LoginPassword = md5( merge(password, rand) )`, where `merge` interleaves the two
   strings character by character — `p0 r0 p1 r1 …` — appending the remainder of the longer one.
   The digest is lowercase hex MD5.
3. `POST /redirect.html` with form field `LoginPassword=<digest>`.
   - On success the response body is a tiny auto-submit form containing
     `<input type="hidden" name="Gambit" value="<token>">` (≈40–44 lowercase chars).
   - If another session is active, the body contains `Maximum number of sessions`.
4. `POST /homepage.html` with `Gambit=<token>` to establish the session (what the browser does next).
5. **Logout:** `GET /iss/specific/logout.html?Gambit=<token>`.

> The switch permits **one** management session at a time. Always log out.

## Writes

Authenticated pages live under `/iss/specific/<page>.html`. A write is a `POST` to that page with
`Gambit` plus a small set of fields. In the UI, the generic helper `submitForm(action)` simply sets
the form's hidden `ACTION` field to `action` and submits — so each operation reduces to one `POST`.

| Operation | Page | Key fields |
|---|---|---|
| Enable Advanced 802.1Q | `Cf8021q.html` | `status=Enable`, `ACTION=` (empty) |
| Create VLAN | `Cf8021q.html` | `ACTION=Add`, `ADD_VLANID=<id>` |
| Delete VLAN | `Cf8021q.html` | `selectedVLANs=<ids>`, `ACTION=<…>` *(payload not yet captured)* |
| Set VLAN membership | `vlanMembership.html` | `VLAN_ID=<v>`, `vlanIdSel=<v>`, `hiddenMem=<12-char>`, `ACTION=` |
| Set port PVID | `vlan_pvidsetting.html` | `PORT_NO="1;5;"`, `PORT_PVID=<v>`, `ACTION=Apply` |

Notes:

- **`hiddenMem`** is a positional string, one character per port (`port1 … port12`):
  `1` = **untagged**, `2` = **tagged**, `3` = **not a member**.
  Example — ports 1 and 5 untagged in a 12-port switch: `133313333333`.
- **`PORT_NO`** (PVID) is a semicolon-separated list **with a trailing semicolon**: ports 1 and 5 → `1;5;`.
  The UI builds this from the row checkboxes via `saveSelectedPorts()`.
- Enabling Advanced 802.1Q triggers a confirm dialog and **erases all current VLAN settings**,
  leaving every port untagged in VLAN 1.

## Reads

Plain `GET /iss/specific/<page>.html?Gambit=<token>`:

| Data | Page | Notes |
|---|---|---|
| VLAN table | `Cf8021q.html` | rows of `VLAN ID` + space-separated member ports |
| Port PVIDs | `vlan_pvidsetting.html` | per-port PVID inputs (nested table — parse with care) |
| Port link/speed | `port_settings.html` | per-port `Up`/`Down` + linked speed |

## NSDP (read-only, unauthenticated)

The NETGEAR Switch Discovery Protocol answers on UDP (`src 63321 → dst <ip>:63322`) and returns
model/firmware plus a VLAN engine table (TLV `0x2400`; mode `0x2000`, value `2` = 802.1Q).
Reads are unauthenticated; writes require a password scramble that is **not** implemented here.

## The login JavaScript

The submit/`ACTION` logic lives in static files served by the switch: `/function.js` and
`/frame.js`. Reading those is the fastest way to confirm field names and `ACTION` values when
porting to a sibling model.

## Porting to other models

Likely to differ on other "Plus"/"Smart Managed Plus" switches: the `merge`/hash scheme, the page
names, the number of ports (so the `hiddenMem` length), and whether a model exposes Basic vs
Advanced 802.1Q. The shape — `rand` nonce → hashed login → `Gambit` token → form `POST`s with an
`ACTION` field — tends to hold. If you map another model, please open a PR.
