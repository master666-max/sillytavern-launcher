#!/bin/bash
# Long-run soak v2 for the on-device SillyTavern (bionic runtime):
#  phases: foreground-idle -> save-load -> background-idle -> resumed
#  samples per 20s round: HTTP health, node/app RSS, node/app CPU jiffies
#  (heat proxy: jiffy delta / (interval*HZ) * 100), save-chain latency.
# Usage:  adb forward tcp:18000 tcp:8000
#         BASE_PORT=18000 WORK=./soak-out ROUNDS=60 bash scripts/soak_test.sh
set -uo pipefail

PORT="${BASE_PORT:-18000}"
BASE="http://127.0.0.1:$PORT"
WORK="${WORK:-./soak-out}"
ADB="${ADB:-adb}"
mkdir -p "$WORK"
cd "$WORK" || exit 1
LOG="soak.log"
: > "$LOG"

PROBE_S=20
HZ=100
ROUNDS="${ROUNDS:-60}"
IDLE_ROUNDS=12            # first 4 min: foreground idle
LOAD_ROUNDS=42            # next 10 min: save chain every 90s
BG_ROUNDS=57              # then background idle until round 57
# rounds > BG_ROUNDS: app resumed

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

curl -s -c cookies.txt -o /dev/null --max-time 10 "$BASE/"
TOKEN=$(curl -s -b cookies.txt -c cookies.txt --max-time 10 "$BASE/csrf-token" 2>/dev/null | python -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
log "csrf token: ${TOKEN:0:8}..."

dev() { "$ADB" shell "$1" 2>/dev/null | tr -d '\r'; }
rss_kb() { [ -n "$1" ] && dev "cat /proc/$1/status" | awk '/VmRSS/{print $2}'; }
ticks() { [ -n "$1" ] && dev "cat /proc/$1/stat" | awk '{print $14+$15}'; }

make_chat() {
    python - "$1" "body.json" <<'PYEOF'
import json, sys
n, out = int(sys.argv[1]), sys.argv[2]
chat = [{"name": "Soak", "is_user": i % 2 == 0, "is_system": False,
         "send_date": 1730000000000 + i,
         "mes": ("soak message #%d. " % i) * (6 if i % 3 else 18)}
        for i in range(n)]
json.dump({"avatar_url": "SoakTest.png", "file_name": "soak",
           "chat": chat, "force": False}, open(out, "w", encoding="utf-8"))
PYEOF
}

prev_nt=""; prev_at=""; save_round=0
for i in $(seq 1 "$ROUNDS"); do
    if [ "$i" -eq "$LOAD_ROUNDS" ]; then
        dev "input keyevent KEYCODE_HOME" >/dev/null
        log "=== phase: background idle (KEYCODE_HOME) ==="
    fi
    if [ "$i" -eq "$BG_ROUNDS" ]; then
        dev "am start -n io.github.master666max.sillytavern/.MainActivity" >/dev/null
        log "=== phase: resumed ==="
    fi

    CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$BASE/" 2>/dev/null)
    NP=$(dev "ps -A" | grep -w node | awk '{print $2}' | head -1)
    AP=$(dev "pidof io.github.master666max.sillytavern" | awk '{print $1}')
    NRSS=$(rss_kb "$NP"); ARSS=$(rss_kb "$AP")
    NT=$(ticks "$NP"); AT=$(ticks "$AP")

    NCPU="-"; ACPU="-"
    if [ -n "$NT" ] && [ -n "$prev_nt" ] && [ "$NT" -ge "$prev_nt" ]; then
        NCPU=$(awk -v a="$prev_nt" -v b="$NT" -v hz="$HZ" -v s="$PROBE_S" 'BEGIN{printf "%.1f", (b-a)/(hz*s)*100}')
    fi
    if [ -n "$AT" ] && [ -n "$prev_at" ] && [ "$AT" -ge "$prev_at" ]; then
        ACPU=$(awk -v a="$prev_at" -v b="$AT" -v hz="$HZ" -v s="$PROBE_S" 'BEGIN{printf "%.1f", (b-a)/(hz*s)*100}')
    fi
    prev_nt="$NT"; prev_at="$AT"

    SAVE_MS="-"
    if [ "$i" -le "$LOAD_ROUNDS" ] && [ $((i % 4)) -eq 0 ] && [ -n "$TOKEN" ]; then
        save_round=$((save_round + 1))
        N=$((60 + save_round * 40))
        make_chat "$N"
        SAVE_OUT=$(curl -s -b cookies.txt -c cookies.txt -o save-resp.txt \
            -w "%{http_code} %{time_total}" --max-time 60 -X POST \
            -H "x-csrf-token: $TOKEN" -H "Content-Type: application/json" \
            -d @body.json "$BASE/api/chats/save" 2>/dev/null)
        SAVE_MS="n=$N http=$(echo "$SAVE_OUT" | awk '{print $1}') $(echo "$SAVE_OUT" | awk '{printf "%dms", $2*1000}')"
    fi

    log "http=$CODE nodeRss=${NRSS:-?} appRss=${ARSS:-?} nodeCpu=${NCPU}% appCpu=${ACPU}% save=${SAVE_MS}"
    sleep "$PROBE_S"
done
log "soak done"
