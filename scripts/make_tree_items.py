"""Assemble the GitHub tree payload from the blob upload manifest.

Reads dist/changed.txt (paths) and dist/blobs.txt ("sha path" lines), writes
dist/tree-items.json. Deleted files (present in changed.txt, absent from
blobs.txt) are emitted with sha=null so the tree API removes them.
Pure file I/O, fixed repo-relative paths only.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"

blobs = {}
for line in (DIST / "blobs.txt").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    sha, _, path = line.partition(" ")
    blobs[path.strip()] = sha.strip()

items = []
for line in (DIST / "changed.txt").read_text(encoding="utf-8").splitlines():
    path = line.strip()
    if not path:
        continue
    if path in blobs:
        items.append({"path": path, "mode": "100644", "type": "blob", "sha": blobs[path]})
    else:
        items.append({"path": path, "mode": "100644", "type": "blob", "sha": None})

(DIST / "tree-items.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
print(f"tree items: {len(items)} ({sum(1 for i in items if i['sha'] is None)} deletions)")
