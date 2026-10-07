"""Streaming tar merger for building the SillyTavern Android rootfs.

Reads arbitrary compressed tarballs, rewrites member paths/metadata, and
writes a single GNU-format tar that the Android shell can stream-extract.
"""
import argparse
import copy
import io
import json
import os
import tarfile

SKIP_TYPES = (tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE)


def _norm(name):
    return "/".join(c for c in name.replace("\\", "/").split("/") if c not in ("", ".", ".."))


class TarMerger:
    def __init__(self, out_path):
        self._tf = tarfile.open(out_path, "w|gz", format=tarfile.GNU_FORMAT)

    def _rewrite(self, name, strip_components, prefix):
        parts = _norm(name).split("/")
        parts = parts[strip_components:]
        if not parts:
            return None
        if prefix:
            parts = prefix.split("/") + parts
        return "/".join(parts)

    def _emit(self, ti, fileobj=None):
        self._tf.addfile(ti, fileobj)

    def _normalize(self, ti):
        ti.uid = 0
        ti.gid = 0
        ti.uname = ""
        ti.gname = ""
        ti.mtime = 0

    def add_tarball(self, src_path, strip_components=0, prefix="", skip=None):
        with tarfile.open(src_path, "r|*") as src:
            for ti in src:
                if ti.type in SKIP_TYPES:
                    continue
                if skip is not None and skip(ti):
                    continue
                new_name = self._rewrite(ti.name, strip_components, prefix)
                if new_name is None:
                    continue
                out = copy.copy(ti)
                out.name = new_name
                if ti.type == tarfile.LNKTYPE:
                    new_link = self._rewrite(ti.linkname, strip_components, prefix)
                    if new_link is None:
                        continue
                    out.linkname = new_link
                # symlink linkname stays as-is: relative targets survive prefix moves
                self._normalize(out)
                if ti.isfile():
                    self._emit(out, src.extractfile(ti))
                else:
                    self._emit(out)

    def add_tree(self, src_dir, prefix, prune_dev_meta=True):
        """Add a real directory tree (used for the ST checkout + node_modules).

        prune_dev_meta drops *.md/*.markdown/*.map files and test* dirs: dead
        weight on a production device image.
        """
        src_dir = os.path.abspath(src_dir)
        base = _norm(prefix)
        self.add_dir(base)
        skip_dirs = {"test", "tests", "__tests__", ".github", "docs"} if prune_dev_meta else set()
        for root, dirs, files in os.walk(src_dir, followlinks=False):
            rel = os.path.relpath(root, src_dir).replace("\\", "/")
            rel = "" if rel == "." else rel
            if root != src_dir:
                self.add_dir("/".join([base, rel] if rel else base).strip("/"))
            if prune_dev_meta:
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                files = [f for f in files if not f.endswith((".md", ".markdown", ".map"))]
            for name in files + [d for d in dirs if os.path.islink(os.path.join(root, d))]:
                full = os.path.join(root, name)
                arcname = "/".join([base, rel, name] if rel else [base, name])
                if os.path.islink(full):
                    self.add_symlink(_norm(arcname), os.readlink(full))
                else:
                    self.add_file(_norm(arcname), full)
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]

    def add_file(self, arcname, src_path):
        st = os.stat(src_path)
        ti = tarfile.TarInfo(arcname)
        ti.size = st.st_size
        ti.mode = 0o755 if st.st_mode & 0o111 else 0o644
        ti.type = tarfile.REGTYPE
        self._normalize(ti)
        with open(src_path, "rb") as f:
            self._emit(ti, f)

    def add_bytes(self, name, data, mode=0o644):
        ti = tarfile.TarInfo(name)
        ti.size = len(data)
        ti.mode = mode
        ti.type = tarfile.REGTYPE
        self._normalize(ti)
        self._emit(ti, io.BytesIO(data))

    def add_symlink(self, name, target):
        ti = tarfile.TarInfo(name)
        ti.type = tarfile.SYMTYPE
        ti.linkname = target
        ti.mode = 0o777
        self._normalize(ti)
        self._emit(ti)

    def add_dir(self, name, mode=0o755):
        ti = tarfile.TarInfo(name)
        ti.type = tarfile.DIRTYPE
        ti.mode = mode
        self._normalize(ti)
        self._emit(ti)

    def close(self):
        self._tf.close()


def main():
    ap = argparse.ArgumentParser(description="Build SillyTavern Android rootfs tar.gz")
    ap.add_argument("--abi", required=True, choices=["arm64-v8a", "x86_64"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--assets-src", default="assets-src")
    args = ap.parse_args()
    raise SystemExit(build(args.abi, args.out, args.assets_src))


def _st_version(assets_src):
    """Read the SillyTavern version from its package.json (single source of truth)."""
    with open(os.path.join(assets_src, "SillyTavern", "package.json"), "r", encoding="utf-8") as f:
        return json.load(f).get("version", "0.0.0")


def build(abi, out_path, assets_src):
    try:
        from pipeline.sources import source_paths
    except ImportError:  # run as a plain script: pipeline/ is on sys.path
        from sources import source_paths

    s = source_paths(abi)
    st_version = _st_version(assets_src)
    # Runtime source of truth: RootfsInstaller compares this against the
    # marker inside the extracted rootfs to decide on re-extraction.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo_root, "app", "src", "main", "assets",
                           "st-version.txt"), "w") as f:
        f.write(st_version)
    merger = TarMerger(out_path)

    def skip_node(ti):
        n = _norm(ti.name)
        return "/include/" in n or "/share/doc/" in n or "/share/man/" in n or "/systemtest/" in n

    def skip_debian(ti):
        """Docs, locales, tzdata and apt lists: no value on the device."""
        n = _norm(ti.name)
        for dead in ("usr/share/doc/", "usr/share/man/", "usr/share/locale/",
                     "usr/share/zoneinfo/", "usr/share/common-licenses/",
                     "var/lib/apt/lists/", "usr/share/lintian/", "usr/share/bug/"):
            if n.startswith(dead):
                return True
        return False

    merger.add_tarball(s["rootfs"], skip=skip_debian)  # Debian base -> /
    # DNS: on the x86_64 emulator only 10.0.2.3 (its built-in proxy) resolves;
    # on real phones public resolvers are reachable but 10.0.2.3 doesn't exist.
    if abi == "x86_64":
        resolv = "nameserver 10.0.2.3\nnameserver 223.5.5.5\nnameserver 119.29.29.29\n"
    else:
        resolv = "nameserver 223.5.5.5\nnameserver 119.29.29.29\nnameserver 10.0.2.3\n"
    merger.add_bytes("etc/resolv.conf", resolv.encode(), mode=0o644)
    merger.add_tarball(s["node"], strip_components=1, prefix="usr/local", skip=skip_node)
    merger.add_tree(os.path.join(assets_src, "SillyTavern"), "opt/st")
    # Pre-bundled user extensions: ST's data root is /opt/st/data (its cwd),
    # and ensurePublicDirectoriesExist() fills in the rest of default-user on
    # first boot, so a partial tree is fine.
    extensions_src = os.path.join(assets_src, "extensions")
    if os.path.isdir(extensions_src):
        for entry in sorted(os.listdir(extensions_src)):
            ext_dir = os.path.join(extensions_src, entry)
            if os.path.isdir(ext_dir) and os.path.isfile(os.path.join(ext_dir, "manifest.json")):
                name = entry.removesuffix("-main").removesuffix("-master")
                merger.add_tree(ext_dir, "opt/st/data/default-user/extensions/" + name)
                print(f"bundled extension: {name}")
    merger.add_bytes(
        "opt/st/config.yaml",
        _st_config().encode("utf-8"),
        mode=0o644,
    )
    merger.add_bytes("opt/st/.st-version", (_st_version(assets_src) + "\n").encode(), mode=0o644)
    merger.close()
    return 0


def _st_config():
    return """# Generated by stlauncher pipeline - do not edit on device
port: 8000
listen: false
whitelistMode: false
basicSecurityMode: false
enableCorsProxy: false
protocolAllowedHosts: ["127.0.0.1", "localhost"]
browserLaunch:
  enabled: false
# Performance: every chat save triggers a full-file atomic write; the default
# 10s full-chat backup doubles that I/O and is brutal over proot's ptrace tax
# and flash storage. Disabled on purpose - use ST's manual export instead.
backups:
  chat:
    enabled: false
  common:
    numberOfBackups: 10
"""


if __name__ == "__main__":
    main()
