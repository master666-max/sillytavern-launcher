#!/bin/bash
# ── 酒馆盒子"编译器"：把 SillyTavern 官方最新 release 自动耦合进安卓包 ──
# 用法： scripts/update_st.sh [--staging] [--version X.Y.Z]
#   默认跟踪官方 release 分支最新版；--staging 跟踪开发分支。
# 流程：拉取官方源码 → 重装依赖 → PC 预编译前端 → 重组装 rootfs → 出双 ABI 签名包。
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="release"
ST_VERSION=""
[[ "${1:-}" == "--staging" ]] && { BRANCH="staging"; shift; }
[[ "${1:-}" == "--version" ]] && { ST_VERSION="$2"; shift 2; }

export JAVA_HOME="${JAVA_HOME:?set JAVA_HOME to a JDK 17 install}"
GRADLE_CMD="${STL_GRADLE:-gradle}"

echo "═══ 1/7 拉取 SillyTavern ($BRANCH${ST_VERSION:+ @$ST_VERSION}) ═══"
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

echo "═══ 2/7 安装依赖（npmmirror）═══"
cd SillyTavern-new
npm install --omit=dev --no-audit --no-fund --registry=https://registry.npmmirror.com
cd "$REPO"
python pipeline/clean_node_modules.py assets-src/SillyTavern-new/node_modules --prune

echo "═══ 2.5/7 应用性能补丁（流式渲染节流）═══"
STL_ST_DIR="$REPO/assets-src/SillyTavern-new" python "$REPO/scripts/patch_st.py"

echo "═══ 3/7 预编译前端 ═══"
echo "注意: webpack cache 含绝对路径，仅在 Linux 且位于 /opt/st 编译才能让手机端命中。"
echo "Windows 本机编译仅为语法验证（手机首启仍会冷编译）；路径精确预烘焙请用: gh workflow run auto-build.yml -f force=true"
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

echo "═══ 4/7 接管目录 ═══"
cd "$REPO/assets-src"
rm -rf SillyTavern
mv SillyTavern-new SillyTavern

echo "═══ 5/7 重组装双 ABI rootfs ═══"
cd "$REPO"
python pipeline/build_rootfs.py --abi arm64-v8a --out dist/rootfs-arm64-v8a.tar.gz
python pipeline/build_rootfs.py --abi x86_64 --out dist/rootfs-x86_64.tar.gz

echo "═══ 6/7 构建签名包（arm64 release）═══"
cp dist/rootfs-arm64-v8a.tar.gz app/src/main/assets/rootfs.stgz
cp downloads/proot-arm64 app/src/main/assets/runtime/proot
cp downloads/proot-arm64-loader app/src/main/assets/runtime/loader
cp downloads/proot-arm64-loader32 app/src/main/assets/runtime/loader32
cp downloads/talloc-libtalloc.so.2.5.0 app/src/main/assets/runtime/libtalloc.so.2
cp downloads/shmem-arm64-libandroid-shmem.so app/src/main/assets/runtime/libandroid-shmem.so
cd "$REPO"
"$GRADLE_CMD" assembleRelease --console=plain --no-daemon

NEW_VER=$(node -p "require('./assets-src/SillyTavern/package.json').version")
OUT="$REPO/app/build/outputs/apk/release/app-release.apk"
cp "$OUT" "$REPO/dist/SillyTavern-Launcher-st$NEW_VER-arm64.apk"
echo "═══ 7/7 完成 ═══"
echo "产物: dist/SillyTavern-Launcher-st$NEW_VER-arm64.apk"
echo "发布: gh release create v1.x-st$NEW_VER -R master666-max/sillytavern-launcher dist/SillyTavern-Launcher-st$NEW_VER-arm64.apk"
