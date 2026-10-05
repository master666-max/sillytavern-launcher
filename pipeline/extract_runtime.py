"""Extract the proot runtime (proot, loader, loader32, libtalloc) from
Termux .deb packages into flat runtime files for the APK assets.

Output file names come exclusively from the --map arguments (never from tar
member names), so archive contents cannot influence where bytes land.
"""
import argparse
import io
import lzma
import sys
import tarfile
from pathlib import Path


def read_ar(path: Path):
    with open(path, "rb") as f:
        if f.read(8) != b"!<arch>\n":
            raise ValueError(f"{path}: not a deb (ar) archive")
        while True:
            hdr = f.read(60)
            if len(hdr) < 60:
                return
            name = hdr[:16].decode().strip().rstrip("/")
            size = int(hdr[48:58].decode().strip())
            yield name, f.read(size)


def extract_member(tar_bytes: bytes, wanted: str) -> bytes:
    tf = tarfile.open(fileobj=io.BytesIO(tar_bytes))
    for m in tf.getmembers():
        if m.isfile() and m.name.lstrip("./") == wanted.lstrip("./"):
            return tf.extractfile(m).read()
    raise KeyError(f"member {wanted!r} not found in data.tar")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deb", action="append", required=True)
    ap.add_argument("--map", action="append", required=True,
                    help="TAR_MEMBER:OUTPUT_NAME, repeatable per --deb group")
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Each --deb consumes maps until the next --deb appears.
    groups = []
    cur = None
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--deb":
            cur = {"deb": argv[i + 1], "maps": []}
            groups.append(cur)
            i += 2
        elif argv[i] == "--map":
            if cur is None:
                ap.error("--map must follow a --deb")
            member, out_name = argv[i + 1].split(":", 1)
            if not out_name or "/" in out_name or "\\" in out_name or out_name in (".", ".."):
                ap.error(f"unsafe output name {out_name!r}")
            cur["maps"].append((member, out_name))
            i += 2
        else:
            i += 1

    for g in groups:
        for member, out_name in g["maps"]:
            data = None
            for ar_name, payload in read_ar(Path(g["deb"])):
                if ar_name.startswith("data.tar"):
                    if ar_name.endswith(".xz"):
                        raw = lzma.decompress(payload)
                    elif ar_name.endswith(".zst"):
                        from compression import zstd
                        raw = zstd.decompress(payload)
                    elif ar_name.endswith(".gz"):
                        import gzip
                        raw = gzip.decompress(payload)
                    else:
                        raw = payload
                    try:
                        data = extract_member(raw, member)
                        break
                    except KeyError:
                        continue
            if data is None:
                raise SystemExit(f"{g['deb']}: member {member!r} not found")
            (out_dir / out_name).write_bytes(data)
            print(f"{out_name}: {len(data)//1024} KB")


if __name__ == "__main__":
    main()
