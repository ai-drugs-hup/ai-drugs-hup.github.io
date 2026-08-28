#!/usr/bin/env python3
"""Fetch a PDB entry and trim it to what the home-page viewer actually draws.

The hero shows one catalytic domain, its bound inhibitor and the catalytic zinc.
Everything else in the crystal -- extra chains, waters, crystallisation ions --
is weight the visitor downloads and never sees, so it is stripped here rather
than hidden in the browser.

    python3 scripts/fetch-structure.py 4LXZ --chain A --keep SHH ZN

Writes assets/structure/<id>-trimmed.pdb. Regenerate rather than hand-edit.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "assets" / "structure"
SOURCE = "https://files.rcsb.org/download/{pdb_id}.pdb"


def fetch(pdb_id: str) -> str:
    url = SOURCE.format(pdb_id=pdb_id.upper())
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise SystemExit(f"could not download {url}: {exc}") from exc


def trim(text: str, chain: str, keep: set[str]) -> tuple[str, dict]:
    out: list[str] = []
    stats = {"protein": 0, "ligand": 0, "dropped": 0}
    for line in text.splitlines():
        tag = line[:6]
        if tag in ("ATOM  ", "HETATM"):
            res = line[17:20].strip().upper()
            ch = line[21]
            if res == "HOH":
                stats["dropped"] += 1
                continue
            if ch != chain:
                stats["dropped"] += 1
                continue
            if tag == "HETATM" and res not in keep:
                stats["dropped"] += 1
                continue
            stats["ligand" if tag == "HETATM" else "protein"] += 1
            out.append(line)
        elif tag in ("HELIX ", "SHEET ", "CRYST1", "SSBOND"):
            out.append(line)
    out.append("END")
    return "\n".join(out) + "\n", stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdb_id")
    ap.add_argument("--chain", default="A")
    ap.add_argument("--keep", nargs="*", default=["ZN"],
                    help="HETATM residue names to retain, e.g. the ligand and the metal")
    args = ap.parse_args()

    raw = fetch(args.pdb_id)
    trimmed, stats = trim(raw, args.chain, {k.upper() for k in args.keep})

    if stats["protein"] == 0:
        raise SystemExit(f"no protein atoms kept for chain {args.chain} -- wrong chain id?")
    if stats["ligand"] == 0:
        raise SystemExit(f"no ligand atoms kept from {args.keep} -- wrong residue name?")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"{args.pdb_id.upper()}-trimmed.pdb"
    dest.write_text(trimmed, encoding="utf-8")
    print(f"{dest.relative_to(REPO)}: {dest.stat().st_size / 1024:.0f} KB")
    print(f"  protein atoms kept: {stats['protein']}")
    print(f"  ligand/metal atoms kept: {stats['ligand']}")
    print(f"  atoms dropped: {stats['dropped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
