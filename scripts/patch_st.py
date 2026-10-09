"""Apply stlauncher performance patches to the SillyTavern checkout.

Idempotent: re-running is a no-op. Run after every ST update (update_st.sh
calls it). Each patch asserts its anchor exists, so an upstream refactor
fails loudly instead of silently skipping.

Patch 1 — streaming render throttle (发热归因报告 §5.2):
onProgressStreaming re-runs the full markdown pipeline and replaces the whole
message innerHTML on every SSE chunk: O(n^2) over one reply. Throttle the
expensive tail (format + DOM) to ~150ms; chat state still updates on every
chunk, and isFinal always renders fully.

Patch 2 — skip startup webpack revalidation when the bundle was prebuilt
(server-main.js runs runWebpackCompiler on every boot; with the bundle and
cache shipped in the rootfs the ~3s + CPU spike per start is pure waste).
Gated by env ST_SKIP_WEBPACK=1 and an existence check on the compiled bundle,
so a missing/cleaned data dir still falls back to compiling.
"""
import os
import sys
from pathlib import Path

MARKER1 = "__stlLastRenderAt"
ANCHOR1 = "            const formattedText = messageFormatting(\n"
INJECT1 = (
    "            // stlauncher-perf: throttle streaming markdown re-render (150ms);\n"
    "            // state updates above stay per-chunk, isFinal always renders fully.\n"
    "            if (!isFinal) {\n"
    "                const __stlNow = Date.now();\n"
    "                if (this.__stlLastRenderAt && (__stlNow - this.__stlLastRenderAt) < 150) {\n"
    "                    return;\n"
    "                }\n"
    "                this.__stlLastRenderAt = __stlNow;\n"
    "            }\n"
)

MARKER2 = "__stlPrebuiltMissing"
ANCHOR2 = (
    "    // Wait for frontend libs to compile\n"
    "    await webpackMiddleware.runWebpackCompiler({ pruneCache: true });\n"
)
INJECT2 = (
    "    // stlauncher-perf: skip the startup webpack run when the prebuilt bundle\n"
    "    // ships with the app; compile only when the bundle is actually missing.\n"
    "    let __stlPrebuiltMissing = true;\n"
    "    if (process.env.ST_SKIP_WEBPACK === '1') {\n"
    "        try {\n"
    "            const __stlConfig = (await import('../webpack.config.js')).default({});\n"
    "            const __stlOut = path.join(__stlConfig.output.path, __stlConfig.output.filename);\n"
    "            __stlPrebuiltMissing = !fs.existsSync(__stlOut);\n"
    "        } catch {\n"
    "            __stlPrebuiltMissing = true;\n"
    "        }\n"
    "    }\n"
    "    if (__stlPrebuiltMissing) {\n"
    "        // Wait for frontend libs to compile\n"
    "        await webpackMiddleware.runWebpackCompiler({ pruneCache: true });\n"
    "    }\n"
)

# Patch 3 - default UI language to Simplified Chinese. The stock chain is
# override(localStorage) || navigator.language || 'en'; on this Android port
# we drop navigator.language so the default is zh-cn regardless of the
# device locale, while an explicit user choice in UI settings (localStorage
# override) still wins.
MARKER3 = "stlauncher: default locale zh-cn"
ANCHOR3 = "const localeFile = String(overrideLanguage || navigator.language || navigator.userLanguage || 'en').toLowerCase();\n"
INJECT3 = (
    "// stlauncher: default locale zh-cn (user override still wins)\n"
    "const localeFile = String(overrideLanguage || 'zh-cn').toLowerCase();\n"
)


def apply_patch(target: Path, marker: str, anchor: str, replacement: str) -> int:
    if not target.is_file():
        print(f"skip: {target} not found")
        return 0
    text = target.read_text(encoding="utf-8")
    if marker in text:
        print(f"already patched: {target.name}")
        return 0
    if text.count(anchor) != 1:
        print(f"ERROR: anchor found {text.count(anchor)} times in {target.name}, "
              "expected 1 — ST source changed upstream; update patch_st.py",
              file=sys.stderr)
        return 1
    target.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")
    print(f"patched: {target.name}")
    return 0


def main():
    repo = Path(__file__).resolve().parent.parent
    # update_st.sh targets the freshly fetched checkout via STL_ST_DIR
    st_dir = Path(os.environ.get("STL_ST_DIR", repo / "assets-src" / "SillyTavern"))
    rc = 0
    rc |= apply_patch(st_dir / "public" / "script.js", MARKER1, ANCHOR1, INJECT1 + ANCHOR1)
    rc |= apply_patch(st_dir / "src" / "server-main.js", MARKER2, ANCHOR2, INJECT2)
    rc |= apply_patch(st_dir / "public" / "scripts" / "i18n.js", MARKER3, ANCHOR3, INJECT3)
    return rc


if __name__ == "__main__":
    sys.exit(main())
