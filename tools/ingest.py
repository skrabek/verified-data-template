"""Preserve an original file and register it as a source.

The file is copied (never moved or altered) to raw/objects/sha256/, verified, made read-only,
and described by a new SRC record. A file already preserved is not ingested twice.

    python tools/ingest.py path/to/file.pdf --title "..." --class contract --provenance "Emailed by J. Smith, 2026-10-01"
    python tools/ingest.py notes.md --title "..." --class ai_generated --use context --use-reason "AI summary; leads only"
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import common as c


def ingest(root: Path, file: Path, title: str, cls: str, provenance: str,
           use: str = "eligible", use_reason: str = "") -> str:
    file = Path(file)
    digest = c.sha256_file(file)
    for identity, revisions in c.load_records(root).items():
        doc = revisions[-1]["doc"]
        if doc.get("type") == "source" and doc["data"].get("sha256") == digest:
            raise SystemExit(f"Already preserved as {identity}; cite that source instead.")
    target = root / "raw" / "objects" / "sha256" / digest[:2] / f"{digest}{file.suffix.lower()}"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
        if c.sha256_file(target) != digest:
            target.unlink()
            raise SystemExit("The copy did not verify; nothing was ingested.")
        c.make_readonly(target)
    identity = c.next_id(root, "SRC")
    c.write_new(root / "records" / "source" / identity / "r1.json", {
        "id": identity, "type": "source", "revision": 1,
        "created_at": c.now(), "created_by": "tools/ingest.py", "applied_from": None,
        "data": {
            "title": title, "class": cls, "use": use, "use_reason": use_reason,
            "provenance": provenance, "original_filename": file.name,
            "object": c.rel(root, target), "sha256": digest, "ingested_at": c.now(),
        },
    })
    return identity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--class", dest="cls", required=True, help="kind of document, e.g. contract, invoice, ai_generated")
    parser.add_argument("--provenance", required=True, help="where the file came from and when")
    parser.add_argument("--use", choices=sorted({"eligible", "context", "excluded"}), default="eligible")
    parser.add_argument("--use-reason", default="")
    args = parser.parse_args()
    identity = ingest(c.ROOT, args.file, args.title, args.cls, args.provenance, args.use, args.use_reason)
    print(f"{identity} records/source/{identity}/r1.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
