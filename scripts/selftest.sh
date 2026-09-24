#!/usr/bin/env bash
# Smoke test for the learning system. Runs in a temp copy so real state is untouched.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/scripts"
cp "$SRC"/scripts/*.py "$TMP/scripts/"
cp "$SRC/learn.config.json" "$TMP/"
export CLAUDE_PROJECT_DIR="$TMP"
cd "$TMP"
S="python3 scripts/state.py"; R="python3 scripts/srs.py"; E="python3 scripts/exercise.py"

echo "== state"
$S show
$S start "TCP reliability" --goal "understand why TCP is reliable"
$S edge "packets: floor=knows loss; ceiling=thinks routers retransmit"
$S plan-set <<'EOF'
{"mermaid":"graph TD\n A[all comm is packets]-->B[packets get lost]\n B-->C[reliability on top]","nodes":[{"id":"n1","label":"All communication is packets","depends":[]},{"id":"n2","label":"Packets get lost","depends":["n1"]},{"id":"n3","label":"Reliability built on top","depends":["n2"]}]}
EOF
$S plan-approve
$S node-done n1 "accepted as unconditional truth" --check mcq
$S node-shaky n2 "confuses loss with corruption"
$S node-done n2 "derived loss from finite buffers" --check short
$S checkpoint "midway"
$S next "teach n3"
$S show
test -f state/progress.md && echo "progress.md ok"
NOTE=$(python3 -c "import json;print(json.load(open('state/state.json'))['topics']['tcp-reliability']['note'])")
test -f "$NOTE" && echo "note ok: $NOTE"

echo "== srs"
ID=$($R add --topic tcp-reliability --node n2 --type short --q "Why can a packet be lost?" --a "Finite buffers overflow; links drop frames" --points "buffers;links")
$R add --topic tcp-reliability --type mcq --q "Who retransmits?" --a "The sender" --options "The sender|The router|The receiver" >/dev/null
$R due
$R stats
$R grade "$ID" 4
$R grade "$ID" 5
$R show "$ID"
$R forecast --days 3
$R list

echo "== exercise"
$E new --topic tcp-reliability --name checksum --lang python --title "Compute a checksum"
$E new --topic tcp-reliability --name checksum-js --lang js --title "Checksum in JS" >/dev/null
$E list
set +e; $E check exercises/tcp-reliability/checksum; echo "check exit=$? (expected 1: placeholder test)"; set -e

echo "== hooks"
echo '{"source":"startup"}' | python3 scripts/hook_session_start.py | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['hookSpecificOutput']['additionalContext'])"
python3 - <<'EOF'
import json,datetime
p='state/state.json'; s=json.load(open(p)); t=s['topics'][s['active_topic']]
t['updated']=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=30)).isoformat()
json.dump(s,open(p,'w'))
EOF
echo '{"stop_hook_active":false}' | python3 scripts/hook_stop_checkpoint.py | grep -q '"block"' && echo "stop hook blocks when stale: ok"
if echo '{"stop_hook_active":true}' | python3 scripts/hook_stop_checkpoint.py | grep -q .; then echo "FAIL: should not block on second stop"; exit 1; else echo "stop hook passes on second stop: ok"; fi
$S checkpoint "fresh"
if echo '{}' | python3 scripts/hook_stop_checkpoint.py | grep -q .; then echo "FAIL: should not block when fresh"; exit 1; else echo "stop hook passes when fresh: ok"; fi
echo '{"trigger":"auto"}' | python3 scripts/hook_precompact.py

echo "== session log"
cat > transcript.jsonl <<'EOF'
{"type":"user","isSidechain":false,"timestamp":"2026-09-24T09:00:00.000Z","message":{"role":"user","content":"Teach me TCP"}}
{"type":"assistant","isSidechain":false,"timestamp":"2026-09-24T09:00:05.000Z","message":{"role":"assistant","content":[{"type":"thinking","thinking":"x"},{"type":"text","text":"Let's start from packets. $x^2$"},{"type":"tool_use","id":"toolu_1","name":"AskUserQuestion","input":{"questions":[{"header":"Probe","question":"What is a packet?","options":[{"label":"A unit of data","description":"d1"},{"label":"A cable"}],"multiSelect":false}]}}]}}
{"type":"user","isSidechain":false,"timestamp":"2026-09-24T09:01:00.000Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_1","content":[{"type":"text","text":"User selected: A unit of data"}]}]}}
{"type":"user","isSidechain":true,"timestamp":"2026-09-24T09:01:00.000Z","message":{"role":"user","content":"sidechain noise"}}
{"type":"user","isSidechain":false,"timestamp":"2026-09-24T09:02:00.000Z","message":{"role":"user","content":[{"type":"text","text":"<command-name>/teach</command-name>"}]}}
{"type":"assistant","isSidechain":false,"timestamp":"2026-09-24T09:02:05.000Z","message":{"role":"assistant","content":[{"type":"text","text":"Correct. Next node."}]}}
EOF
echo "{\"session_id\":\"t1\",\"transcript_path\":\"$TMP/transcript.jsonl\"}" | python3 scripts/session_log.py
echo "{\"session_id\":\"t1\",\"transcript_path\":\"$TMP/transcript.jsonl\"}" | python3 scripts/session_log.py
echo "--- note content:"; cat "$NOTE"
n=$(grep -c "TEACHER" "$NOTE"); test "$n" -eq 2 && echo "teacher blocks: 2 ok" || { echo "FAIL teacher blocks $n"; exit 1; }
grep -q "sidechain noise" "$NOTE" && { echo "FAIL sidechain logged"; exit 1; } || echo "sidechain skipped ok"
grep -q "command-name" "$NOTE" && { echo "FAIL command logged"; exit 1; } || echo "command skipped ok"
grep -q "Answer" "$NOTE" && echo "answer logged ok"

echo "== finish"
$S finish --summary "done"
$S show; $S topics
$S log-target notes/reviews/x.md; $S log-target --clear
echo "ALL OK"
