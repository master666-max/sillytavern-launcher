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

    def add_tree(self, src_dir, prefix, prune_dev_meta=True, bin_exec=False):
        """Add a real directory tree (used for the ST checkout + node_modules).

        prune_dev_meta drops *.md/*.markdown/*.map files and test* dirs: dead
        weight on a production device image.
        bin_exec forces mode 0755 on files under a bin/ directory — Windows
        hosts cannot represent the Unix exec bit in stat(), so staging a
        runtime tree there would otherwise arrive non-executable.
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
                    force = None
                    if bin_exec and "/bin/" in "/" + arcname:
                        force = 0o755
                    self.add_file(_norm(arcname), full, force_mode=force)
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]

    def add_file(self, arcname, src_path, force_mode=None):
        st = os.stat(src_path)
        ti = tarfile.TarInfo(arcname)
        ti.size = st.st_size
        if force_mode is not None:
            ti.mode = force_mode
        else:
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
    ap.add_argument("--bionic", help="termux-node runtime tree to embed at /opt/bionic")
    ap.add_argument("--bionic-only", action="store_true",
                    help="bionic payload only: drop the Debian base + glibc node")
    args = ap.parse_args()
    raise SystemExit(build(args.abi, args.out, args.assets_src, args.bionic, args.bionic_only))


def _st_version(assets_src):
    """Read the SillyTavern version from its package.json (single source of truth)."""
    with open(os.path.join(assets_src, "SillyTavern", "package.json"), "r", encoding="utf-8") as f:
        return json.load(f).get("version", "0.0.0")


def _payload_version(assets_src, bionic_dir=None):
    """ST version + payload fingerprint covering the config template and the
    runtime kind/size. Any user-visible payload change then forces
    re-extraction on devices; without it an unchanged ST version would keep
    a stale config/extensions tree alive forever."""
    import hashlib
    h = hashlib.sha256()
    h.update(_st_version(assets_src).encode())
    h.update(_st_config().encode())
    # ST files that patches rewrite: content hash captures any patch change
    for rel in ("public/scripts/i18n.js", "public/script.js", "src/server-main.js"):
        fp = os.path.join(assets_src, "SillyTavern", *rel.split("/"))
        if os.path.isfile(fp):
            with open(fp, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
    # patch/localization logic itself: updating a translation table must
    # refresh devices even when ST and the runtime are untouched
    scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
    for fn in ("patch_st.py", "localize_extensions.py", "fetch_extensions.sh"):
        fp = os.path.join(scripts_dir, fn)
        if os.path.isfile(fp):
            with open(fp, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
    # bundled extension manifests (names/flags/localization markers)
    ext_root = os.path.join(assets_src, "extensions")
    if os.path.isdir(ext_root):
        for entry in sorted(os.listdir(ext_root)):
            fp = os.path.join(ext_root, entry, "manifest.json")
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    h.update(entry.encode())
                    h.update(hashlib.sha256(f.read()).digest())
    if bionic_dir and os.path.isdir(bionic_dir):
        h.update(b"bionic")
        # hash every runtime file (name+size): any stub/binary change must
        # force re-extraction on devices. npm's tree under node_modules is
        # skipped - it only moves when the node package itself does (which
        # changes bin/node's size).
        for root, dirs, files in os.walk(bionic_dir):
            dirs[:] = [d for d in dirs if d != "node_modules"]
            for fn in sorted(files):
                fp = os.path.join(root, fn)
                h.update(os.path.relpath(fp, bionic_dir).encode())
                try:
                    h.update(str(os.path.getsize(fp)).encode())
                except OSError:
                    pass
    return f"{_st_version(assets_src)}-{h.hexdigest()[:10]}"


def build(abi, out_path, assets_src, bionic_dir=None, bionic_only=False):
    try:
        from pipeline.sources import source_paths
    except ImportError:  # run as a plain script: pipeline/ is on sys.path
        from sources import source_paths

    s = source_paths(abi)
    payload_version = _payload_version(assets_src, bionic_dir)
    # Runtime source of truth: RootfsInstaller compares this against the
    # marker inside the extracted rootfs to decide on re-extraction.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo_root, "app", "src", "main", "assets",
                           "st-version.txt"), "w") as f:
        f.write(payload_version)
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

    merger.add_tarball(s["rootfs"], skip=skip_debian) if not bionic_only else None
    # DNS: on the x86_64 emulator only 10.0.2.3 (its built-in proxy) resolves;
    # on real phones public resolvers are reachable but 10.0.2.3 doesn't exist.
    if abi == "x86_64":
        resolv = "nameserver 10.0.2.3\nnameserver 223.5.5.5\nnameserver 119.29.29.29\n"
    else:
        resolv = "nameserver 223.5.5.5\nnameserver 119.29.29.29\nnameserver 10.0.2.3\n"
    if not bionic_only:
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
    merger.add_bytes("opt/st/.st-version", (payload_version + "\n").encode(), mode=0o644)
    # Experimental bionic runtime (v1.2 track): embed a termux-node runtime
    # tree (bin/ + lib/) at /opt/bionic for no-proot experiments.
    if bionic_dir and os.path.isdir(bionic_dir):
        merger.add_tree(bionic_dir, "opt/bionic", prune_dev_meta=False, bin_exec=True)
        # ST spawns xdg-open whenever browserLaunch is enabled; Android has no
        # such binary and the unhandled ENOENT kills node. A no-op stub makes
        # ANY user config safe, including ones that drop our browserLaunch
        # override entirely.
        merger.add_bytes(
            "opt/bionic/bin/xdg-open",
            b"#!/system/bin/sh\n# no-op: Android has no desktop browser to open\nexit 0\n",
            mode=0o755,
        )
        print(f"embedded bionic runtime from {bionic_dir}")
    merger.close()
    return 0


def _st_config():
    return """# Generated by stlauncher pipeline - factory defaults.
# NOTE: an editable copy lands at
# Android/data/io.github.master666max.sillytavern/files/config.yaml on first
# run; if present it wins on every start (your edits are never overwritten).
port: 8000
listen: false
whitelistMode: true
basicSecurityMode: false
enableCorsProxy: false
protocolAllowedHosts: ["127.0.0.1", "localhost"]
# Android adaptation: there is no desktop browser to auto-open.
browserLaunch:
  enabled: false
# Android adaptation: no system git in the bundled runtime (same behavior as
# PC users without git installed): always use the isomorphic-git backend.
git:
  backend: builtin
"""


if __name__ == "__main__":
    main()
