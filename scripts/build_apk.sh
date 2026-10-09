#!/bin/bash
# Build the SillyTavern launcher APK for one ABI.
# usage: scripts/build_apk.sh <arm64-v8a|x86_64> <debug|release>
set -euo pipefail

ABI="${1:?usage: build_apk.sh <arm64-v8a|x86_64> <debug|release>}"
TYPE="${2:?usage: build_apk.sh <arm64-v8a|x86_64> <debug|release>}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
# Raw artifacts (rootfs parts, extracted proot runtime) live in a download
# cache; override with STL_DOWNLOADS. Needs JDK 17 (JAVA_HOME) and Gradle 8.9.
DL="${STL_DOWNLOADS:-$REPO/downloads}"
JDK="${JAVA_HOME:?set JAVA_HOME to a JDK 17 install}"
GRADLE_CMD="${STL_GRADLE:-gradle}"

case "$ABI" in
  arm64-v8a)
    ROOTFS_TGZ="$REPO/dist/rootfs-arm64-v8a.tar.gz"
    P="proot-arm64"; L="proot-arm64-loader"; L32="proot-arm64-loader32"; T="talloc-libtalloc.so.2.5.0"; S="shmem-arm64-libandroid-shmem.so" ;;
  x86_64)
    ROOTFS_TGZ="$REPO/dist/rootfs-x86_64.tar.gz"
    P="proot-x64"; L="proot-x64-loader"; L32="proot-x64-loader32"; T="talloc-x64-libtalloc.so.2"; S="shmem-x64-libandroid-shmem.so" ;;
  *) echo "unknown abi: $ABI" >&2; exit 2 ;;
esac

for f in "$ROOTFS_TGZ" "$DL/$P" "$DL/$L" "$DL/$L32" "$DL/$T" "$DL/$S"; do
  [ -f "$f" ] || { echo "missing source: $f" >&2; exit 1; }
done

ASSETS="$REPO/app/src/main/assets"
mkdir -p "$ASSETS/runtime"
# sanity: v1.2+ payloads must carry the bionic runtime, otherwise the app
# can only fall back to proot (which the bionic-only payloads omit)
tar tzf "$ROOTFS_TGZ" 2>/dev/null | grep -q "opt/bionic/bin/node" || {
  echo "rootfs lacks opt/bionic payload - assemble with --bionic/--bionic-only" >&2; exit 1; }
# .stgz instead of .tar.gz: aapt2 mangles ".gz"-suffixed assets (renames +
# decompresses), so ship the archive under a custom extension.
cp "$ROOTFS_TGZ" "$ASSETS/rootfs.stgz"
cp "$DL/$P"  "$ASSETS/runtime/proot"
cp "$DL/$L"  "$ASSETS/runtime/loader"
cp "$DL/$L32" "$ASSETS/runtime/loader32"
cp "$DL/$T"  "$ASSETS/runtime/libtalloc.so.2"
cp "$DL/$S"  "$ASSETS/runtime/libandroid-shmem.so"

export JAVA_HOME="$JDK"
cd "$REPO"
# Gradle's incremental packaging can silently keep a stale rootfs.stgz /
# st-version.txt inside the APK (seen twice in practice). Deleting the APK
# first forces a full repackage.
rm -f "$REPO/app/build/outputs/apk/$TYPE"/*.apk
"$GRADLE_CMD" "assemble${TYPE^}" --console=plain --no-daemon

echo "=== APK ==="
ls -lh "$REPO/app/build/outputs/apk/$TYPE/"*.apk
