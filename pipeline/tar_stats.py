"""Print top-level size distribution of a .tar.gz to guide slimming."""
import argparse
import gzip
import sys
import tarfile
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("--top", type=int, default=14)
    args = ap.parse_args()

    sizes = defaultdict(int)
    with tarfile.open(args.archive, "r|gz") as tf:
        for m in tf:
            top = "/".join(m.name.replace("\\", "/").lstrip("./").split("/")[:2])
            sizes[top] += m.size

    total = sum(sizes.values())
    for top, size in sorted(sizes.items(), key=lambda kv: -kv[1])[:args.top]:
        print(f"{size/1048576:9.1f} MB  {top}")
    print(f"{total/1048576:9.1f} MB  TOTAL")


if __name__ == "__main__":
    sys.exit(main())
