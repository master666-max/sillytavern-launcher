"""Apply stlauncher performance patches to the SillyTavern checkout.

Idempotent: re-running is a no-op. Run after every ST update (update_st.sh
calls it). Each patch asserts its anchor exists, so an upstream refactor
fails loudly instead of silently skipping.

Patch 1 — streaming render throttle (发热归因报告 §5.2):
onProgressStreaming re-runs the full markdown pipeline and replaces the whole
message innerHTML on every SSE chunk: O(n^2) over one reply. Throttle the
expensive tail (format + DOM) to ~150ms; chat state still updates on every
chunk, and isFinal always renders fully.
"""
import os
import sys
from pathlib import Path

MARKER = "__stlLastRenderAt"
ANCHOR = "            const formattedText = messageFormatting(\n"
INJECT = (
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


def main():
    repo = Path(__file__).resolve().parent.parent
    # update_st.sh targets the freshly fetched checkout via STL_ST_DIR
    st_dir = Path(os.environ.get("STL_ST_DIR", repo / "assets-src" / "SillyTavern"))
    target = st_dir / "public" / "script.js"
    if not target.is_file():
        print(f"skip: {target} not found (no ST checkout)")
        return 0
    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print("already patched (idempotent skip)")
        return 0
    if text.count(ANCHOR) != 1:
        print(f"ERROR: anchor found {text.count(ANCHOR)} times, expected 1 — "
              "ST source changed upstream; update patch_st.py against the new code",
              file=sys.stderr)
        return 1
    target.write_text(text.replace(ANCHOR, INJECT + ANCHOR, 1), encoding="utf-8")
    print(f"patched: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
