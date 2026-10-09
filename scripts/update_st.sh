#!/bin/bash
# ── 酒馆盒子"编译器"（v1.2+ bionic 流程）──
# 把 SillyTavern 官方最新 release 自动耦合进安卓包。
# 用法： scripts/update_st.sh [--staging] [--version X.Y.Z]
# 流程：官方源码 → 预装扩展 → 依赖 → 性能补丁 → 前端预编译 →
#       termux node 闭包（双 ABI）→ 组装 bionic 载荷 → 出 arm64 签名包。
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="release"
ST_VERSION=""
[[ "${1:-}" == "--staging" ]] && { BRANCH="staging"; shift; }
[[ "${1:-}" == "--version" ]] && { ST_VERSION="$2"; shift 2; }

export JAVA_HOME="${JAVA_HOME:?set JAVA_HOME to a JDK 17 install}"
GRADLE_CMD="${STL_GRADLE:-gradle}"
DL="${STL_DOWNLOADS:-$REPO/downloads}"
TMPL_URL="${STL_TERMUX_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/termux/apt/termux-main}"

echo "═══ 1/8 拉取 SillyTavern ($BRANCH${ST_VERSION:+ @$ST_VERSION}) ═══"
cd "$REPO/assets-src"
rm -rf SillyTavern SillyTavern-new
if [ -n "$ST_VERSION" ]; then
  curl -sfL --retry 3 -o st.zip "https://codeload.github.com/SillyTavern/SillyTavern/zip/refs/tags/$ST_VERSION"
else
  curl -sfL --retry 3 -o st.zip "https://codeload.github.com/SillyTavern/SillyTavern/zip/refs/heads/$BRANCH"
fi
unzip -q st.zip && rm st.zip
mv SillyTavern-* SillyTavern-new
echo "官方版本: $(node -p "require('./SillyTavern-new/package.json').version")"

echo "═══ 2/8 确保预装扩展（最新 zip + auto_update=false）═══"
bash "$REPO/scripts/fetch_extensions.sh"

echo "═══ 3/8 安装依赖（npmmirror）═══"
cd SillyTavern-new
npm install --omit=dev --no-audit --no-fund --registry=https://registry.npmmirror.com
cd "$REPO"
python pipeline/clean_node_modules.py assets-src/SillyTavern-new/node_modules --prune

echo "═══ 4/8 应用性能补丁（可重放的幂等 patch）═══"
STL_ST_DIR="$REPO/assets-src/SillyTavern-new" python "$REPO/scripts/patch_st.py"

echo "═══ 5/8 预编译前端（生成 output/lib.js；设备端由 ST_SKIP_WEBPACK 直接复用）═══"
cd assets-src/SillyTavern-new
node server.js > /tmp/st-precompile.log 2>&1 &
ST_PID=$!
for i in $(seq 1 60); do
  grep -q "compiled successfully" /tmp/st-precompile.log 2>/dev/null && break
  kill -0 $ST_PID 2>/dev/null || break
  sleep 5
done
grep -q "compiled successfully" /tmp/st-precompile.log || { echo "预编译失败，见 /tmp/st-precompile.log"; exit 1; }
kill $ST_PID 2>/dev/null || true
sleep 2
rm -rf data/default-user data/backups data/_errors data/cookie-secret.txt
echo "预编译完成: $(du -sh data/_webpack | cut -f1)"

echo "═══ 6/8 接管目录 ═══"
cd "$REPO/assets-src"
rm -rf SillyTavern
mv SillyTavern-new SillyTavern

echo "═══ 7/8 拉取 termux node 闭包（双 ABI）并组装载荷 ═══"
mkdir -p "$DL"
curl -sfL -o "$DL/termux-Packages-arm64" "$TMPL_URL/dists/stable/main/binary-aarch64/Packages"
curl -sfL -o "$DL/termux-Packages-x64" "$TMPL_URL/dists/stable/main/binary-x86_64/Packages"
python pipeline/termux_node.py --index "$DL/termux-Packages-arm64" --root npm --out dist/bionic-aarch64
python pipeline/termux_node.py --index "$DL/termux-Packages-x64"  --root npm --out dist/bionic-x86_64
python pipeline/build_rootfs.py --abi arm64-v8a --out dist/rootfs-arm64-v8a.tar.gz --bionic dist/bionic-aarch64 --bionic-only
python pipeline/build_rootfs.py --abi x86_64    --out dist/rootfs-x86_64.tar.gz    --bionic dist/bionic-x86_64    --bionic-only

echo "═══ 8/8 构建签名包（arm64 release）═══"
cp dist/rootfs-arm64-v8a.tar.gz app/src/main/assets/rootfs.stgz
[ -f "$DL/proot-arm64" ] && cp "$DL/proot-arm64" app/src/main/assets/runtime/proot || true
[ -f "$DL/proot-arm64-loader" ] && cp "$DL/proot-arm64-loader" app/src/main/assets/runtime/loader || true
[ -f "$DL/proot-arm64-loader32" ] && cp "$DL/proot-arm64-loader32" app/src/main/assets/runtime/loader32 || true
[ -f "$DL/talloc-libtalloc.so.2.5.0" ] && cp "$DL/talloc-libtalloc.so.2.5.0" app/src/main/assets/runtime/libtalloc.so.2 || true
[ -f "$DL/shmem-arm64-libandroid-shmem.so" ] && cp "$DL/shmem-arm64-libandroid-shmem.so" app/src/main/assets/runtime/libandroid-shmem.so || true
"$GRADLE_CMD" assembleRelease --console=plain --no-daemon

NEW_VER=$(node -p "require('./assets-src/SillyTavern/package.json').version")
cp app/build/outputs/apk/release/app-release.apk "dist/SillyTavern-Launcher-st$NEW_VER-arm64.apk"
echo "═══ 完成 ═══"
echo "产物: dist/SillyTavern-Launcher-st$NEW_VER-arm64.apk"
echo "发布: gh release create v1.x-st$NEW_VER -R master666-max/sillytavern-launcher dist/SillyTavern-Launcher-st$NEW_VER-arm64.apk"
