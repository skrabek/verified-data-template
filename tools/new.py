"""Print the next free ID and the path to write it to.

    python tools/new.py claim | conclusion | hypothesis | proposal
"""
from __future__ import annotations

import sys

import common as c


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) == 2 else ""
    if kind == "proposal":
        identity = c.next_id(c.ROOT, "PRO")
        print(f"{identity} proposals/{identity}.json")
    elif kind in c.PREFIX and kind != "source":
        identity = c.next_id(c.ROOT, c.PREFIX[kind])
        print(f"{identity} records/{kind}/{identity}/r1.json")
    else:
        print(__doc__ + "\nSources are created only by tools/ingest.py.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
