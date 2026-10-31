#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Poly - a CTF team console
A single-file terminal console for CTF / cyber-competition teams: a shared
reference board, role assignments, a per-lane tool checklist, a target
board, and a flag tracker. Standard library only, runs anywhere:

    python3 ctf_console.py

Everything team- or event-specific lives in the CONFIG block and the lists
just below it. Edit those for your own team. MIT-licensed; see LICENSE.
"""

import os
import sys
import json
import datetime
import ipaddress
import urllib.parse

# ======================================================================
# CONFIG  -  edit this for your own event and team
# ======================================================================
CONFIG = {
    "event_name": "CTF",                 # shown in the banner
    "team_tag": "your team",             # team or school name
    "event_date": "",                    # "YYYY-MM-DD" for a countdown, or "" to hide it
    "subtitle": "team prep + coordination console",
}

# Team roles. Put a name in the first field, or leave it "" for unassigned.
ROLES = [
    ("", "Web / networking / recon", "Captain: triage the board, assign challenges, catch shells."),
    ("", "Reverse engineering + pwn", "Binary exploitation and privesc. The heavy technical lane."),
    ("", "Cryptography", "Classical and modern crypto, scripted in Python."),
    ("", "OSINT / forensics", "Stego, metadata, easy forensics. A good entry lane."),
]
ROLE_NOTE = ("Each person owns a lane and backs up a second. A small team in a timed event "
             "cannot have everyone good at everything. The biggest risk for a newer member "
             "is going quiet, not lacking skill: make sure everyone knows how to submit an "
             "answer, say 'I am stuck, taking this one out loud', and hand a challenge off.")

# ======================================================================
# content  -  generic CTF reference; edit freely
# ======================================================================
CATEGORIES = [
    ("Networking",   "TCP/IP, nmap, reaching hosts beyond the local subnet (pivoting)."),
    ("Web",          "SQL injection, file inclusion (LFI/RFI), command injection, directory traversal."),
    ("SQL",          "Enumerate databases and tables; SELECT statements and wildcards."),
    ("Forensics",    "Memory analysis (Volatility), disk carving, stego."),
    ("Reverse eng.", "Reversing plus beginner binary exploitation (pwn)."),
    ("Cryptography", "Common algorithms and their weaknesses."),
    ("Shells",       "Create and interact with a reverse shell; know how to catch one."),
    ("Programming",  "Scripting, Python especially."),
    ("Recon / OSINT","Metadata, reverse image search, public records."),
]
CATEGORIES_NOTE = ("Many intro CTFs lean toward attacking a vulnerable network, so reverse "
                   "shells, pivoting and forensics come up a lot. Weight your prep toward "
                   "whatever your event emphasizes.")

SHARED = [
    "A working Linux VM (Kali or Parrot are common; any distro you know is fine).",
    "CyberChef bookmarked (gchq.github.io/CyberChef) - Base64, hex, XOR, ROT, magic bytes. In-browser, zero install.",
    "Volatility 3 for memory forensics:  pipx install volatility3",
    "Agree on comms: one voice channel plus one shared notes doc for flags tried and challenge status.",
]
CHECKLIST = {
    "Web / networking / recon": [
        "nmap, Burp Suite (Community edition is free), ffuf or feroxbuster, gobuster.",
        "sqlmap for SQL injection.",
        "Reverse shells: nc, the bash and python one-liners, and how to CATCH one (nc -lvnp).",
        "Pivoting: chisel or SSH port forwarding for hosts behind a jump box.",
        "Browser plus FoxyProxy to route through Burp.",
    ],
    "Reversing + pwn": [
        "Ghidra (free, the main reversing tool).",
        "pwntools:  pip install pwntools",
        "gdb with GEF or pwndbg.",
        "radare2, plus file / strings / binwalk for triage.",
    ],
    "Cryptography (Python)": [
        "Python 3 with:  pip install pycryptodome sympy gmpy2",
        "CyberChef for quick encodings.",
        "A notebook of common attacks: RSA weak modulus, XOR, classical ciphers, hash cracking.",
    ],
    "OSINT / forensics": [
        "A browser. Most OSINT is search, maps, reverse image search, metadata.",
        "exiftool, binwalk, steghide, zsteg for the 'strings / exif / unzip it' tier.",
        "CyberChef solves a lot of misc and encoding challenges on its own.",
    ],
}

# Generic etiquette. These are common across most CTFs; replace with your
# event's actual rules once you have them.
NOTES = [
    ("Submit as you go", "Don't sit on flags. Score what you have; surprises rarely pay off."),
    ("Show your work", "Many events give points for explaining HOW you got the flag. Keep notes."),
    ("Tools", "Prefer free / open tools unless your event's rules say otherwise."),
    ("Fair play", "No attacks against the scoreboard or other teams. That gets you expelled."),
    ("Read the rules", "Every event differs. Read its rules and any AI-use policy, and agree as a team before you start."),
]

LINKS = [
    ("CyberChef (in-browser)", "https://gchq.github.io/CyberChef/"),
    ("Volatility 3", "https://github.com/volatilityfoundation/volatility3"),
    ("GTFOBins (privesc ref)", "https://gtfobins.github.io/"),
    ("HackTricks (methodology)", "https://book.hacktricks.xyz/"),
    ("CTFtime (events + writeups)", "https://ctftime.org/"),
]

SETUP_SCRIPT = r"""#!/usr/bin/env bash
# Role-aware tool setup. Detects apt vs pacman.
# Installs standard, freely-available security tooling.
# Usage:  bash setup.sh
set -e
if command -v apt >/dev/null 2>&1; then
  PM="sudo apt install -y"
  sudo apt-get -y upgrade 
elif command -v dnf   >/dev/null 2>&1; then
  PM="sudo dnf install -y"
  sudo dnf -y upgrade --refresh  # sys update
elif command -v pacman >/dev/null 2>&1; then
  PM="sudo pacman -S --needed --noconfirm"
elif command -v emerge >/dev/null 2>&1; then
  PM="sudo emerge --ask"
  sudo emerge --sync # sys update 
else
  echo "No supported package manager found"
  echo "Install the packages manually instead"
  exit 1
fi
echo "[*] Core triage"
$PM nmap curl wget git python3 python3-pip file binwalk exiftool steghide foremost gdb radare2 || true
echo "[*] Web"
$PM ffuf gobuster sqlmap || true
echo "[*] Python libs (pip)"
pip install --user pwntools pycryptodome sympy gmpy2 2>/dev/null || pip install --break-system-packages pwntools pycryptodome sympy gmpy2 || true
echo "[*] Memory forensics"
command -v pipx >/dev/null 2>&1 || $PM pipx || true
pipx install volatility3 2>/dev/null || true
echo "[*] Done. Bookmark CyberChef (gchq.github.io/CyberChef) and install Ghidra separately."
"""

# ======================================================================
# skull banner
# ======================================================================
SKULL = r"""
                     ⣀⣠⣤⣤⣤⣤⣤⣤⣤⣄⣀⣀
                ⢀⣤⣴⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⣤⣀
             ⣀⣴⣾⣿⣿⣿⣿⣿⣿⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⣄
          ⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⠘⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣄⡀
       ⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⡈⢿⣿⣿⣿⣿⣿⣿⣿⡿⠟⠛⠋⠉⠉⠉⠉⠙⠛⠻⠷⣄
     ⢀⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠁⣼⣿⣿⣿⣿⠟⠋⢀⣠⣴⣶⣾⣿⣿⣿⣿⣿⣶⣦⣄⡀
    ⢀⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠁⣼⣿⣿⣿⠟⠁⣠⣾⣿⣿⠿⠟⠛⠉⠉⠉⠉⠛⠛⠿⣿⣿⣷⣄
    ⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠁⣠⣾⣿⡿⠋⢡⣶⣤⣤⠀⠀⠀⠀⠀⠀⠀⠀⠙⢿⣿⣷⣄
   ⢸⣿⣿⣿⣿⣿⣿⣿⣿⡿⠿⠛⠛⠛⠿⢿⣿⣿⣿⡿⠀⣰⣿⣿⠏⠀⢀⣼⡿⠛⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⣿⣿⣦
   ⣾⣿⣿⣿⣿⣿⣿⣿⡟⠉⠀⠀⠀⠀⠀⠀⠀⠈⠻⣿⠁⢰⣿⣿⠇⠀⠰⣿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⣿⡆
   ⣿⣿⣿⣿⣿⣿⣿⡏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠀⣾⣿⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⣿⣿
   ⣿⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿
   ⢻⣿⣿⣿⣿⣿⣿⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢿⣿⣧⠠⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⡄⣸⣿⣿
   ⠈⠛⢿⣿⣿⣿⣿⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⡀⠸⣿⣿⡄⢻⣷⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⡟⢠⣿⣿⡏
       ⠉⠻⢿⣿⣿⣿⣦⣄⡀⠀⠀⠀⢀⣀⣴⣿⣿⣧⠀⠹⣿⣿⣄⠙⢿⣆⠀⠀⠀⠀⣠⠟⣠⣿⣿⡟
          ⠉⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⠀⠙⢿⣿⣷⣄⠙⠷⣦⣀⣀⠤⠚⣡⣴⣿⣿⣏
             ⠙⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠀⠀⠀⠙⢿⣿⣿⣶⣤⣤⣶⣿⣿⡿⢿⣿⣿⣷⣄
              ⣿⣿⣿⣿⣿⣿⣿⣿⡟⠀⠀⠀⢹⣦⣀⠈⠛⠿⣿⣿⡿⠿⠛⠉⠙⢿⣿⣿⣿⡿⢃⣄
              ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠰⣿⡿⢋⣴⣿⣿⣷⡄
              ⣿⣿⣿⠀⣿⣿⡇⢸⣿⣿⠀⣿⣿⡇⢸⣿⣿⠀⣿⣿⡇⢸⣿⣿⣿⠙⠿⢋⣴⣿⣿⣿⡿⢃⣄
              ⣿⣉⣉⠀⣉⣉⡁⢈⣉⣉⠀⣉⣉⡁⢈⣉⣉⠀⣉⣉⡁⢈⣉⣉⣿⠀⠙⢿⣿⡿⢋⣴⣿⣿⣷
              ⣿⣿⣿⠀⣿⣿⡇⢸⣿⣿⠀⣿⣿⡇⢸⣿⣿⠀⣿⣿⡇⢸⣿⣿⣿⠀⠉⢴⣿⣿⣿⠟⣡⣾⣷⣄
              ⢿⣿⣿⠀⣿⣿⡇⢸⣿⣿⠀⣿⣿⡇⢸⣿⣿⠀⣿⣿⡇⢸⣿⣿⣿⠀⠀⠙⠟⣡⣾⣿⣿⣿⣿⣷⣄
               ⠻⢿⣤⣿⣿⣧⣼⣿⣿⣤⣿⣿⣧⣼⣿⣿⣤⣿⣿⣧⣼⣿⠟⠀⠀⠙⢿⣿⣿⣿⣿⣿⣿⣷⡄
                                                        ⠙⢿⣿⣿⣿⣿⣿⡇
                                                          ⠙⠿⠿⠿⠋
"""

# ======================================================================
# colours
# ======================================================================
class C:
    R = "\033[31m"
    BR = "\033[91m"
    G = "\033[32m"
    Y = "\033[33m"
    B = "\033[34m"
    CY = "\033[36m"
    W = "\033[97m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    X = "\033[0m"

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(_HERE, "poly_flags.json")
TARGETS_FILE = os.path.join(_HERE, "poly_targets.json")

# ----------------------------------------------------------------------
# target input: accept an IP (optional :port) OR a link, detect + parse
# ----------------------------------------------------------------------
def classify_target(raw):
    """Return dict: kind ('host'|'web'), host, port, scheme, path, display."""
    s = raw.strip()
    if not s:
        return None
    if "://" in s:
        u = urllib.parse.urlparse(s)
        host = u.hostname or ""
        port = u.port
        return {"kind": "web", "host": host, "port": port, "scheme": u.scheme,
                "path": u.path or "/", "display": s}
    host_part, _, port_part = s.partition(":")
    port = None
    if port_part and port_part.split("/")[0].isdigit():
        port = int(port_part.split("/")[0])
    is_ip = False
    try:
        ipaddress.ip_address(host_part)
        is_ip = True
    except ValueError:
        is_ip = False
    has_path = "/" in s
    if has_path:
        return {"kind": "web", "host": host_part, "port": port, "scheme": "http",
                "path": "/" + s.split("/", 1)[1], "display": s}
    return {"kind": "host", "host": host_part, "port": port, "scheme": None,
            "path": None, "display": s, "is_ip": is_ip}

WEB_METHOD = [
    "robots.txt, sitemap.xml, /.git/, view-source + HTML comments.",
    "Directory + file brute: ffuf / feroxbuster / gobuster.",
    "Test every parameter for SQLi (sqlmap), then LFI/RFI, command injection, path traversal.",
    "Check cookies, headers, and auth. Try default / weak creds.",
    "Route through Burp (FoxyProxy) to see and replay requests.",
]
HOST_METHOD = [
    "Full service scan: nmap -sV -sC -p- against the host, then enumerate each open port.",
    "Low-hanging: anonymous FTP, open SMB shares, exposed admin panels.",
    "Match service versions to known CVEs.",
    "After a foothold: enumerate for privesc (GTFOBins, sudo -l, SUID).",
    "Pivot: from this host, nmap/forward to hosts beyond the local subnet.",
]

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def clear():
    os.system("cls" if os.name == "nt" else "clear")

def _event_date():
    try:
        return datetime.datetime.strptime(CONFIG.get("event_date", ""), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

def header():
    print(C.BR + SKULL + C.X)
    print(f"  {C.BOLD}{C.W}{CONFIG['event_name']}{C.X}  ::  {C.CY}{CONFIG['team_tag']}{C.X}")
    ed = _event_date()
    line = f"  {C.DIM}{CONFIG['subtitle']}{C.X}"
    if ed:
        d = (ed - datetime.date.today()).days
        if d > 0:
            cd = f"{C.BR}{d} days{C.X} to go"
        elif d == 0:
            cd = f"{C.BR}TODAY. Good luck.{C.X}"
        else:
            cd = f"{C.DIM}event passed{C.X}"
        line = f"  {C.Y}{ed.isoformat()}{C.X}  ::  {cd}   {C.DIM}{CONFIG['subtitle']}{C.X}"
    print(line)
    print(C.DIM + "  " + "-" * 64 + C.X)

def pause():
    input(f"\n  {C.DIM}[enter to go back]{C.X} ")

def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"  {C.R}could not save: {e}{C.X}")

# ----------------------------------------------------------------------
# screens
# ----------------------------------------------------------------------
def screen_categories():
    clear(); header()
    print(f"\n  {C.BOLD}{C.W}COMMON CTF CATEGORIES{C.X}\n")
    for area, desc in CATEGORIES:
        print(f"  {C.G}{area:<14}{C.X} {desc}")
    print(f"\n  {C.Y}Note:{C.X} {CATEGORIES_NOTE}")
    pause()

def screen_roles():
    clear(); header()
    print(f"\n  {C.BOLD}{C.W}ROLE BOARD{C.X}  {C.DIM}(everyone owns a lane + backs up a second){C.X}\n")
    for who, lane, role in ROLES:
        name = who if who else f"{C.DIM}(unassigned){C.X}"
        print(f"  {C.CY}{name:<14}{C.X} {C.W}{lane}{C.X}")
        print(f"  {' ':<14} {C.DIM}{role}{C.X}\n")
    print(f"  {C.Y}Note:{C.X} {ROLE_NOTE}")
    pause()

def screen_checklist():
    clear(); header()
    print(f"\n  {C.BOLD}{C.W}TOOL CHECKLIST{C.X}  {C.DIM}(install your lane ahead of time, not during the event){C.X}\n")
    print(f"  {C.G}Shared by everyone{C.X}")
    for item in SHARED:
        print(f"    {C.DIM}-{C.X} {item}")
    print()
    for lane, items in CHECKLIST.items():
        print(f"  {C.G}{lane}{C.X}")
        for item in items:
            print(f"    {C.DIM}-{C.X} {item}")
        print()
    print(f"  {C.Y}Tip:{C.X} menu option [7] writes a role-aware setup.sh (apt/pacman) to share with the team.")
    pause()

def screen_notes():
    clear(); header()
    print(f"\n  {C.BOLD}{C.W}ETIQUETTE / NOTES{C.X}  {C.DIM}(edit NOTES for your event's real rules){C.X}\n")
    for title, desc in NOTES:
        print(f"  {C.G}{title:<16}{C.X} {desc}")
    pause()

def screen_links():
    clear(); header()
    print(f"\n  {C.BOLD}{C.W}QUICK LINKS{C.X}  {C.DIM}(bookmark these on every machine){C.X}\n")
    for name, url in LINKS:
        print(f"  {C.G}{name:<28}{C.X} {C.CY}{url}{C.X}")
    pause()

def screen_tracker():
    while True:
        clear(); header()
        flags = _load(DATA_FILE)
        print(f"\n  {C.BOLD}{C.W}FLAG / CHALLENGE TRACKER{C.X}  {C.DIM}({DATA_FILE}){C.X}\n")
        if not flags:
            print(f"  {C.DIM}nothing tracked yet.{C.X}")
        else:
            marks = {"todo": f"{C.Y}[ ]{C.X}", "wip": f"{C.B}[~]{C.X}", "done": f"{C.G}[x]{C.X}", "stuck": f"{C.R}[!]{C.X}"}
            for i, fl in enumerate(flags):
                m = marks.get(fl.get("status", "todo"), "[ ]")
                print(f"  {m} {C.W}{fl['name']:<28}{C.X} {C.DIM}owner:{C.X} {fl.get('owner','-'):<10} {C.DIM}{fl.get('cat','')}{C.X}")
        print(f"\n  {C.DIM}[a] add   [s] set status   [d] delete   [b] back{C.X}")
        ch = input("  > ").strip().lower()
        if ch == "b":
            return
        elif ch == "a":
            name = input("  challenge name: ").strip()
            if not name:
                continue
            cat = input("  category (web/pwn/crypto/forensics/osint/...): ").strip()
            owner = input("  owner: ").strip()
            flags.append({"name": name, "cat": cat, "owner": owner, "status": "todo"})
            _save(DATA_FILE, flags)
        elif ch == "s":
            idx = input("  row number: ").strip()
            if idx.isdigit() and 0 <= int(idx) < len(flags):
                st = input("  status [todo/wip/done/stuck]: ").strip().lower()
                if st in ("todo", "wip", "done", "stuck"):
                    flags[int(idx)]["status"] = st
                    _save(DATA_FILE, flags)
        elif ch == "d":
            idx = input("  row number: ").strip()
            if idx.isdigit() and 0 <= int(idx) < len(flags):
                flags.pop(int(idx))
                _save(DATA_FILE, flags)

def screen_targets():
    while True:
        clear(); header()
        targets = _load(TARGETS_FILE)
        print(f"\n  {C.BOLD}{C.W}TARGETS{C.X}  {C.DIM}(accepts an IP, host:port, or a link){C.X}\n")
        if not targets:
            print(f"  {C.DIM}no targets yet. [a] to add one.{C.X}")
        else:
            for i, t in enumerate(targets):
                tag = f"{C.CY}web{C.X}" if t["kind"] == "web" else f"{C.G}host{C.X}"
                portstr = f":{t['port']}" if t.get("port") else ""
                print(f"  {C.W}{i}{C.X}  [{tag}] {C.W}{t['display']}{C.X}  "
                      f"{C.DIM}{t['host']}{portstr}  owner:{t.get('owner','-')}{C.X}")
        print(f"\n  {C.DIM}[a] add   [v] view methodology   [o] set owner   [d] delete   [b] back{C.X}")
        ch = input("  > ").strip().lower()
        if ch == "b":
            return
        elif ch == "a":
            raw = input("  target (IP, host:port, or https://... link): ").strip()
            parsed = classify_target(raw)
            if not parsed:
                continue
            owner = input("  owner (optional): ").strip()
            parsed["owner"] = owner or "-"
            targets.append(parsed)
            _save(TARGETS_FILE, targets)
        elif ch == "v":
            idx = input("  row number: ").strip()
            if idx.isdigit() and 0 <= int(idx) < len(targets):
                t = targets[int(idx)]
                clear(); header()
                portstr = f":{t['port']}" if t.get("port") else ""
                print(f"\n  {C.BOLD}{C.W}{t['display']}{C.X}")
                print(f"  {C.DIM}parsed as{C.X} {C.G}{t['kind']}{C.X}  "
                      f"{C.DIM}host={C.X}{t['host']}{portstr}"
                      + (f"  {C.DIM}path={C.X}{t['path']}" if t.get('path') else ""))
                method = WEB_METHOD if t["kind"] == "web" else HOST_METHOD
                label = "WEB APP - manual methodology" if t["kind"] == "web" else "NETWORK HOST - manual methodology"
                print(f"\n  {C.Y}{label}{C.X}  {C.DIM}(reference checklist, run these yourself){C.X}\n")
                for step in method:
                    print(f"    {C.DIM}-{C.X} {step}")
                pause()
        elif ch == "o":
            idx = input("  row number: ").strip()
            if idx.isdigit() and 0 <= int(idx) < len(targets):
                targets[int(idx)]["owner"] = input("  owner: ").strip() or "-"
                _save(TARGETS_FILE, targets)
        elif ch == "d":
            idx = input("  row number: ").strip()
            if idx.isdigit() and 0 <= int(idx) < len(targets):
                targets.pop(int(idx))
                _save(TARGETS_FILE, targets)

def write_setup():
    clear(); header()
    path = os.path.join(_HERE, "setup.sh")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(SETUP_SCRIPT)
        os.chmod(path, 0o755)
        print(f"\n  {C.G}Wrote role-aware setup script to:{C.X} {path}")
        print(f"  Run it on any machine:  {C.CY}bash setup.sh{C.X}")
        print(f"  {C.DIM}Installs standard free tooling via apt or pacman. Review it before running.{C.X}")
    except Exception as e:
        print(f"\n  {C.R}could not write setup.sh: {e}{C.X}")
    pause()

# ----------------------------------------------------------------------
# main loop
# ----------------------------------------------------------------------
MENU = [
    ("1", "Common CTF categories", screen_categories),
    ("2", "Role board", screen_roles),
    ("3", "Tool checklist (per lane)", screen_checklist),
    ("4", "Etiquette / notes", screen_notes),
    ("5", "Quick links", screen_links),
    ("6", "Targets (IP or link)", screen_targets),
    ("7", "Flag / challenge tracker", screen_tracker),
    ("8", "Write role-aware setup.sh", write_setup),
]

def main():
    if "--check" in sys.argv:
        header()
        for _, _, fn in MENU:
            assert callable(fn)
        print("selftest ok")
        return
    while True:
        clear(); header()
        print(f"\n  {C.BOLD}{C.W}MENU{C.X}\n")
        for key, label, _ in MENU:
            print(f"   {C.G}[{key}]{C.X} {label}")
        print(f"   {C.R}[0]{C.X} quit")
        choice = input(f"\n  {C.W}>{C.X} ").strip()
        if choice == "0":
            clear()
            print(f"{C.BR}stay sharp. good luck.{C.X}\n")
            return
        for key, _, fn in MENU:
            if choice == key:
                fn()
                break

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{C.BR}bye.{C.X}")
