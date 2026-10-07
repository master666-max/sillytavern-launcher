#!/bin/bash
# Long-run soak test for the on-device SillyTavern:
#  - probes HTTP health every PROBE_S seconds
#  - posts a growing chat to /api/chats/save every SAVE_S seconds (the
#    identified hot I/O path) and records latency + response
#  - samples node/proot/app RSS
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
SAVE_S=90
ROUNDS="${ROUNDS:-60}"   # 60 rounds * 20s = 20 min

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

curl -s -c cookies.txt -o /dev/null --max-time 10 "$BASE/"
TOKEN=$(curl -s -b cookies.txt -c cookies.txt --max-time 10 "$BASE/csrf-token" 2>/dev/null | python -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
log "csrf token: ${TOKEN:0:8}..."

dev() { "$ADB" shell "$1" 2>/dev/null | tr -d '\r'; }
rss_kb() { [ -n "$1" ] && dev "cat /proc/$1/status" | awk '/VmRSS/{print $2}'; }

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

save_round=0
for i in $(seq 1 "$ROUNDS"); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$BASE/" 2>/dev/null)

    NP=$(dev "ps -A" | grep -w node | awk '{print $2}' | head -1)
    PP=$(dev "ps -A" | grep -w proot | awk '{print $2}' | head -1)
    AP=$(dev "pidof io.github.master666max.sillytavern" | awk '{print $1}')
    NRSS=$(rss_kb "$NP"); PRSS=$(rss_kb "$PP"); ARSS=$(rss_kb "$AP")

    SAVE_MS="-"
    if [ $((i % (SAVE_S / PROBE_S))) -eq 0 ] && [ -n "$TOKEN" ]; then
        save_round=$((save_round + 1))
        N=$((60 + save_round * 40))
        make_chat "$N"
        SAVE_OUT=$(curl -s -b cookies.txt -c cookies.txt -o save-resp.txt \
            -w "%{http_code} %{time_total}" --max-time 60 -X POST \
            -H "x-csrf-token: $TOKEN" -H "Content-Type: application/json" \
            -d @body.json "$BASE/api/chats/save" 2>/dev/null)
        SAVE_HTTP=$(echo "$SAVE_OUT" | awk '{print $1}')
        SAVE_MS="n=$N http=$SAVE_HTTP $(echo "$SAVE_OUT" | awk '{printf "%dms", $2*1000}')"
    fi

    log "http=$CODE node=${NRSS:-?}KB proot=${PRSS:-?}KB app=${ARSS:-?}KB save=${SAVE_MS}"
    sleep "$PROBE_S"
done
log "soak done"
