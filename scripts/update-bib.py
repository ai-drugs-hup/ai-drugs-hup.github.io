#!/usr/bin/env python3
"""Turn publications.txt into references.bib and publications.yml.

Citations on this site are never typed by hand. This script is the only writer of
both output files: it sends each identifier to the lab's citation resolver,
accepts the entry only if the resolver confirms it as published, and records
everything it refused so the refusal is visible rather than silent.

The resolver endpoint is read from CITATION_RESOLVER_URL and is deliberately NOT
hardcoded -- this repository is public.

    export CITATION_RESOLVER_URL=http://<host>:<port>
    python3 scripts/update-bib.py

Input  : publications.txt        one DOI per line, optional "role=" annotation
Output : references.bib          BibTeX, for anyone who wants to cite the lab
         publications.yml        what publications.qmd renders
         scripts/rejected.json   what was refused, and why

ORDERING, which is the point of publications.yml:
  Papers where Dr. Dung is first or corresponding author are the lead set,
  sorted most recent first and, within a year, most cited first. The remaining
  co-authored papers follow. The featured cards are the first FEATURED_COUNT of
  the lead set that are also international -- a decision by Dr. Dung, so that the
  cards a journal editor sees first are the international work; domestic papers
  still appear in full in the list below. Citation counts come from the resolver
  at build time, so they age -- rerun this script to refresh them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO / "publications.txt"
BIB_OUT = REPO / "references.bib"
YML_OUT = REPO / "publications.yml"
REJECTED = REPO / "scripts" / "rejected.json"

TIMEOUT_S = 90
RETRIES = 3
WORKERS = 4
FEATURED_COUNT = 6
LEAD_ROLES = ("first", "corresponding")


class ResolverError(RuntimeError):
    """The resolver could not be reached -- a transport fault, not a citation fault."""


class Unresolvable(RuntimeError):
    """The resolver was reached and declined to identify this entry."""


def post(endpoint: str, path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    last = ""
    for attempt in range(RETRIES):
        req = urllib.request.Request(
            endpoint.rstrip("/") + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")[:300]
            try:
                detail = json.loads(raw).get("detail", raw)
            except json.JSONDecodeError:
                detail = raw
            if exc.code in (404, 422):
                raise Unresolvable(str(detail)) from exc
            last = f"HTTP {exc.code} from {path}: {detail}"
        except (urllib.error.URLError, TimeoutError) as exc:
            last = f"cannot reach resolver at {endpoint}: {exc}"
        except json.JSONDecodeError as exc:
            last = f"resolver returned non-JSON from {path}: {exc}"
    raise ResolverError(last)


def read_entries(path: Path) -> list[dict]:
    """Each line: <doi or title>  [role=...] [scope=international|domestic]"""
    if not path.exists():
        raise SystemExit(f"{path.name} does not exist.")
    entries: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        role, scope = "co-author", "international"
        for token in parts[1:]:
            if token.startswith("role="):
                role = token.split("=", 1)[1]
            elif token.startswith("scope="):
                scope = token.split("=", 1)[1]
        entries.append({"ident": parts[0], "role": role, "scope": scope})
    return entries


def as_payload(identifier: str) -> dict:
    ident = identifier.removeprefix("https://doi.org/").removeprefix("doi:").strip()
    key = "doi" if ident.startswith("10.") and "/" in ident else "title"
    return {key: ident}


def fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    ).lower()


def find_her(authors: list[str]) -> str:
    """Which author string is Dr. Dung, so the page can mark her name.

    Deliberately strict: the co-author lists also contain a different person
    named Phan Thi Phuong Dung, so "Dung" alone must never be enough.
    """
    for author in authors:
        tokens = set(fold(author).replace(".", " ").replace("-", " ").split())
        if "dung" in tokens and ("do" in tokens or "mai" in tokens):
            if {"do", "t", "thi", "mai"} & tokens:
                return author
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--allow-preprints", action="store_true",
                        help="also accept entries the resolver does not call published")
    args = parser.parse_args()

    endpoint = os.environ.get("CITATION_RESOLVER_URL", "").strip()
    if not endpoint:
        raise SystemExit(
            "CITATION_RESOLVER_URL is not set. The resolver address is not stored in this "
            "public repository -- export it in your shell before running."
        )

    entries = read_entries(args.input)
    if not entries:
        raise SystemExit(f"{args.input.name} contains no identifiers.")
    print(f"Resolving {len(entries)} identifiers through the resolver...")

    def resolve_one(entry: dict) -> dict:
        payload = as_payload(entry["ident"])
        try:
            meta = post(endpoint, "/v1/resolve", dict(payload))
            cite = post(endpoint, "/v1/cite", dict(payload, style="bibtex"))
        except Unresolvable as exc:
            return dict(entry, refused=str(exc), status="unresolved")
        return dict(entry, meta=meta, cite=cite)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        try:
            results = list(pool.map(resolve_one, entries))
        except ResolverError as exc:
            print(f"FATAL: {exc}", file=sys.stderr)
            print("No file was written -- a partial bibliography would look complete.",
                  file=sys.stderr)
            return 2

    bib: list[str] = []
    records: list[dict] = []
    rejected: list[dict] = []

    for res in results:
        ident = res["ident"]
        if "refused" in res:
            rejected.append({"input": ident, "reason": res["refused"], "status": "unresolved"})
            print(f"REJECT {ident}: {res['refused']}")
            continue

        meta, cite = res["meta"], res["cite"]
        status = cite.get("status", "unknown")
        bibtex = (cite.get("bibtex") or "").strip()

        if not bibtex:
            rejected.append({"input": ident, "reason": "no bibtex returned", "status": status})
            print(f"REJECT {ident}: no bibtex returned")
            continue
        if status != "published" and not args.allow_preprints:
            rejected.append({"input": ident, "reason": f"status={status}",
                             "venue": meta.get("venue", "")})
            print(f"REJECT {ident}: resolver status is '{status}', not 'published'")
            continue

        authors = meta.get("authors") or []
        bib.append(bibtex)
        records.append({
            "title": meta.get("title") or "",
            "authors": authors,
            "her_name": find_her(authors),
            "venue": meta.get("published_venue") or meta.get("venue") or "",
            "year": meta.get("year") or meta.get("issue_year"),
            "doi": meta.get("doi") or ident,
            "citations": meta.get("cited_by") or 0,
            "role": res["role"],
            "scope": res["scope"],
            "n_authors": len(authors),
        })

    if not records:
        print("\nNothing resolved to a published entry; no file written.", file=sys.stderr)
        return 1

    # Lead set first: most recent, then most cited within a year.
    def sort_key(rec: dict) -> tuple:
        return (
            0 if rec["role"] in LEAD_ROLES else 1,
            -(rec["year"] or 0),
            -rec["citations"],
        )

    records.sort(key=sort_key)
    featured_seen = 0
    for rec in records:
        rec["featured"] = False
        if (rec["role"] in LEAD_ROLES
                and rec["scope"] == "international"
                and featured_seen < FEATURED_COUNT):
            rec["featured"] = True
            featured_seen += 1

    header = (
        "% Generated by scripts/update-bib.py from the lab's citation resolver.\n"
        "% DO NOT HAND-EDIT: the next run overwrites this file wholesale.\n"
        f"% Entries: {len(bib)}   Refused: {len(rejected)}\n\n"
    )
    BIB_OUT.write_text(header + "\n\n".join(bib) + "\n", encoding="utf-8")

    # JSON is valid YAML, so this needs no YAML library and cannot mis-escape a
    # title containing a colon or a quote.
    YML_OUT.write_text(
        "# Generated by scripts/update-bib.py. DO NOT HAND-EDIT.\n"
        + json.dumps(records, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    REJECTED.write_text(json.dumps(rejected, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    lead = sum(1 for r in records if r["role"] in LEAD_ROLES)
    print(f"\nWrote references.bib and publications.yml: {len(records)} entries "
          f"({lead} first/corresponding), {len(rejected)} refused.")
    unmarked = [r["doi"] for r in records if not r["her_name"]]
    if unmarked:
        print(f"WARNING: no matching author name found on {len(unmarked)} entries: "
              f"{', '.join(unmarked[:5])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
