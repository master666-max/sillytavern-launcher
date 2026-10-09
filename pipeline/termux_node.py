"""Fetch and analyze the termux nodejs runtime closure (bionic migration spike).

Given a termux Packages index, resolves the dependency closure of a root
package, downloads the debs, extracts bin/ and lib/ members into a flat
runtime tree, and reports:
  - the DT_NEEDED closure of the main binary (missing libs = broken plan)
  - LOAD segment alignment per binary (Android 15+/16KB page devices need
    p_align >= 0x4000 for native code)
  - shebangs that hardcode the termux prefix (must be rewritten on device)

Pure stdlib. Writes into an output directory; never touches the APK.
"""
import argparse
import io
import lzma
import re
import struct
import subprocess
import sys
import urllib.request
from pathlib import Path

MIRROR = "https://mirrors.tuna.tsinghua.edu.cn/termux/apt/termux-main"


def parse_index(index_path):
    stanzas = {}
    cur = {}
    for line in Path(index_path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            if cur.get("Package"):
                stanzas[cur["Package"]] = cur
            cur = {}
            continue
        if line[0].isspace() or ":" not in line:
            continue
        k, _, v = line.partition(":")
        cur[k.strip()] = v.strip()
    if cur.get("Package"):
        stanzas[cur["Package"]] = cur
    return stanzas


def parse_depends(value):
    out = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        alt = part.split("|")[0].strip()
        name = re.split(r"[\s(]", alt)[0]
        if name:
            out.append(name)
    return out


def closure(stanzas, root):
    seen = {}
    stack = [root]
    while stack:
        pkg = stack.pop()
        if pkg in seen:
            continue
        meta = stanzas.get(pkg)
        if not meta:
            print(f"WARN: {pkg} not in index", file=sys.stderr)
            continue
        seen[pkg] = meta
        for dep in parse_depends(meta.get("Depends", "")):
            if dep not in seen:
                stack.append(dep)
    return seen


def download(mirror, filename, dest_dir):
    name = filename.split("/")[-1]
    dest = dest_dir / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    url = f"{mirror}/{filename}"
    print(f"download {url}")
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest


def read_ar_members(deb_path):
    with open(deb_path, "rb") as f:
        assert f.read(8) == b"!<arch>\n"
        while True:
            hdr = f.read(60)
            if len(hdr) < 60:
                return
            name = hdr[:16].decode().strip().rstrip("/")
            size = int(hdr[48:58].decode().strip())
            yield name, f.read(size)
            if size % 2:
                f.read(1)  # ar members are 2-byte aligned


def extract_deb(deb_path, out_dir):
    """Extract bin/ and lib/ members, flattening the termux prefix."""
    import tarfile
    pfx = "data/data/com.termux/files/usr/"
    wrote = 0
    for name, payload in read_ar_members(deb_path):
        if not name.startswith("data.tar"):
            continue
        if name.endswith(".xz"):
            raw = lzma.decompress(payload)
        elif name.endswith(".zst"):
            from compression import zstd
            raw = zstd.decompress(payload)
        elif name.endswith(".gz"):
            import gzip
            raw = gzip.decompress(payload)
        else:
            raw = payload
        tf = tarfile.open(fileobj=io.BytesIO(raw))
        out_root = out_dir.resolve()
        for m in tf.getmembers():
            rel = m.name.lstrip("./")
            if not rel.startswith(pfx):
                continue
            rest = rel[len(pfx):]
            top = rest.split("/")[0]
            # Keep bin/, lib/ and the openssl config assets. Termux's openssl
            # bakes its default cnf path to $PREFIX/etc/tls/openssl.cnf; when
            # another Termux install exists on the device that path is EACCES
            # (not ENOENT) and node dies at startup — ship our own copy and
            # point OPENSSL_CONF at it.
            if top not in ("bin", "lib") and rest not in (
                    "etc/tls/openssl.cnf", "etc/tls/cert.pem"):
                continue
            # tar-slip guard: the member must stay inside out_dir
            target = (out_dir / rest).resolve()
            if out_root not in target.parents:
                print(f"WARN: skipping escaping member {m.name}", file=sys.stderr)
                continue
            if m.issym():
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    target.unlink()
                target.symlink_to(m.linkname)
                continue
            if not m.isfile():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as o:
                o.write(tf.extractfile(m).read())
            wrote += 1
    return wrote


# ---- minimal ELF reader: DT_NEEDED + LOAD alignment ----
def elf_info(path):
    data = Path(path).read_bytes()
    if data[:4] != b"\x7fELF":
        return None
    is64 = data[4] == 2
    if not is64:
        return None
    e_shoff, e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<QHQH", data, 0x28)[0], \
        struct.unpack_from("<H", data, 0x3A)[0], struct.unpack_from("<H", data, 0x3C)[0], \
        struct.unpack_from("<H", data, 0x3E)[0]
    if e_shoff == 0:
        return {"needed": [], "align": 0, "interp": None}
    # section headers
    shdrs = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        sh = struct.unpack_from("<IIQQQQIIQQ", data, off)
        shdrs.append(sh)
    shstr = shdrs[e_shstrndx]
    shstrtab = data[shstr[4]:shstr[4] + shstr[5]]
    def secname(sh):
        end = shstrtab.find(b"\0", sh[0])
        return shstrtab[sh[0]:end].decode(errors="replace")
    needed, align, interp = [], 0, None
    for sh in shdrs:
        n = secname(sh)
        if n == ".dynamic":
            off, size = sh[4], sh[5]
            for j in range(0, size, 16):
                tag, val = struct.unpack_from("<qQ", data, off + j)
                if tag == 0:
                    break
                if tag == 1:  # DT_NEEDED
                    strtab_sh = next(s for s in shdrs if secname(s) == ".dynstr")
                    st = data[strtab_sh[4]:strtab_sh[4] + strtab_sh[5]]
                    end = st.find(b"\0", val)
                    needed.append(st[val:end].decode(errors="replace"))
        elif n == ".interp":
            interp = data[sh[4]:sh[4] + sh[5]].split(b"\0")[0].decode(errors="replace")
    # program headers for LOAD alignment
    e_phoff = struct.unpack_from("<Q", data, 0x20)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x36)[0]
    e_phnum = struct.unpack_from("<H", data, 0x38)[0]
    for i in range(e_phnum):
        ph = struct.unpack_from("<IIQQQQQQ", data, e_phoff + i * e_phentsize)
        if ph[0] == 1:  # PT_LOAD
            align = max(align, ph[6])
    return {"needed": needed, "align": align, "interp": interp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--root", default="nodejs")
    ap.add_argument("--out", required=True, help="output dir for runtime tree")
    ap.add_argument("--debs", help="dir to cache debs (default: out/_debs)")
    args = ap.parse_args()

    out = Path(args.out)
    debs = Path(args.debs) if args.debs else out / "_debs"
    debs.mkdir(parents=True, exist_ok=True)

    stanzas = parse_index(args.index)
    pkgs = closure(stanzas, args.root)
    print(f"closure: {len(pkgs)} packages: {', '.join(sorted(pkgs))}")

    for name, meta in sorted(pkgs.items()):
        deb = download(MIRROR, meta["Filename"], debs)
        wrote = extract_deb(deb, out)
        print(f"  {name} {meta['Version']}: {wrote} files")

    # analyze
    print("\n=== ELF analysis ===")
    bin_dir = out / "bin"
    libs = {p.name for p in (out / "lib").glob("*.so*")}
    problems = []
    for exe in sorted(bin_dir.iterdir()):
        if not exe.is_file() or exe.is_symlink():
            continue
        try:
            info = elf_info(exe)
        except Exception as e:
            print(f"  {exe.name}: not ELF ({e})")
            continue
        if not info:
            continue
        missing = [n for n in info["needed"] if n not in libs and not n.startswith("libc.so")]
        align_ok = info["align"] >= 0x4000
        print(f"  {exe.name}: needed={info['needed']} align=0x{info['align']:x} "
              f"{'16K-OK' if align_ok else '4K-ONLY!'} interp={info['interp']}")
        if missing:
            problems.append(f"{exe.name} missing libs: {missing}")
        if not align_ok:
            problems.append(f"{exe.name} is 4KB-page aligned (fails on 16KB devices)")
    for so in sorted((out / "lib").glob("*.so*")):
        info = elf_info(so)
        if info and info["align"] < 0x4000:
            problems.append(f"{so.name} is 4KB-page aligned")

    # shebang scan
    print("\n=== shebang scan (hardcoded termux prefix) ===")
    bad_shebang = 0
    for p in list(bin_dir.iterdir()) + list((out / "lib" / "node_modules").rglob("*.js")) if (out / "lib" / "node_modules").exists() else list(bin_dir.iterdir()):
        try:
            if p.is_symlink() or not p.is_file():
                continue
            head = p.read_bytes()[:120]
            if head.startswith(b"#!"):
                line = head.split(b"\n", 1)[0].decode(errors="replace")
                if "com.termux" in line:
                    print(f"  {p.relative_to(out)}: {line}")
                    bad_shebang += 1
        except OSError:
            pass
    print(f"\nshebang needing rewrite: {bad_shebang}")
    print(f"\nproblems: {len(problems)}")
    for p in problems:
        print("  -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
