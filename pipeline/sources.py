"""Source artifact path mapping per target ABI.

All artifacts live outside the repo (a PC download cache + staging); only the
assembled rootfs tarball ever enters the APK assets.

Override the cache location with the STL_DOWNLOADS environment variable.
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOWNLOADS = Path(os.environ.get(
    "STL_DOWNLOADS", REPO / "downloads"))
ASSETS_SRC = REPO / "assets-src"

# APK asset file names for the proot runtime pieces
RUNTIME_FILES = ["proot", "loader", "loader32", "libtalloc.so.2", "libandroid-shmem.so"]

_NODE_VERSION = "v22.20.0"

_SOURCES = {
    "arm64-v8a": {
        "rootfs": DOWNLOADS / "debian-arm64-rootfs.tar.xz",
        "node": DOWNLOADS / "node-v22-arm64.tar.gz",
        "proot_deb": DOWNLOADS / "proot-arm64",
        "loader": DOWNLOADS / "proot-arm64-loader",
        "loader32": DOWNLOADS / "proot-arm64-loader32",
        "talloc": DOWNLOADS / "talloc-libtalloc.so.2.5.0",
        "shmem": DOWNLOADS / "shmem-arm64-libandroid-shmem.so",
    },
    "x86_64": {
        "rootfs": DOWNLOADS / "debian-x64-rootfs.tar.xz",
        "node": DOWNLOADS / "node-v22-x64.tar.gz",
        "proot_deb": DOWNLOADS / "proot-x64",
        "loader": DOWNLOADS / "proot-x64-loader",
        "loader32": DOWNLOADS / "proot-x64-loader32",
        "talloc": DOWNLOADS / "talloc-x64-libtalloc.so.2",
        "shmem": DOWNLOADS / "shmem-x64-libandroid-shmem.so",
    },
}


def source_paths(abi):
    if abi not in _SOURCES:
        raise ValueError(f"unknown abi {abi!r}; expected one of {sorted(_SOURCES)}")
    return dict(_SOURCES[abi])


def st_dir():
    return ASSETS_SRC / "SillyTavern"


def check_sources(abi):
    missing = [k for k, p in source_paths(abi).items() if not Path(p).exists()]
    if missing or not st_dir().exists():
        raise FileNotFoundError(
            f"missing sources for {abi}: {missing}"
            + ("" if st_dir().exists() else f" + {st_dir()}")
        )
