#!/usr/bin/env bash
# Smoke test for the learning system. Runs in a temp copy with ITS OWN config, so
# every writable directory (notes, viz, reviews, exercises, state) lives under the
# temp root: the user's vault and live state are never touched, whatever
# learn.config.json in the repo points at. The regression suite runs at the end.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/scripts"
cp "$SRC"/scripts/*.py "$TMP/scripts/"
cat > "$TMP/learn.config.json" <<CFG
{"notesDir": "$TMP/vault/notes", "vizDir": "$TMP/vault/viz", "reviewsDir": "$TMP/vault/reviews",
 "exercisesDir": "$TMP/exercises", "stateDir": "$TMP/state", "timezone": "Europe/Oslo", "checkpointMinutes": 12}
CFG
export CLAUDE_PROJECT_DIR="$TMP"
unset LEARN_NOW
cd "$TMP"
S="python3 scripts/state.py"; R="python3 scripts/srs.py"; E="python3 scripts/exercise.py"

echo "== state"
$S show
$S start "TCP reliability" --goal "understand why TCP is reliable"
$S edge "packets: floor=knows loss; ceiling=thinks routers retransmit"
$S plan-set <<'PLAN'
{"nodes":[{"id":"n1","label":"All communication is packets","depends":[]},{"id":"n2","label":"Packets get lost","depends":["n1"]},{"id":"n3","label":"Reliability built on top","depends":["n2"]}]}
PLAN
$S plan-approve
$S prep-topic <<'PREP'
{"capability":"explain why TCP is reliable","chunks":[{"id":"s1","label":"basics","nodes":["n1","n2","n3"]}],
 "exit_criteria":[{"id":"x1","text":"explain loss recovery","nodes":["n3"],"checks":[{"id":"xq1","type":"short","role":"exit","variants":[{"id":"v1","question":"How does TCP recover a lost segment?","answer":"Sender retransmits after missing ack / timeout","required":["sender retransmits","detects via ack or timeout"]}]}]}],
 "sources":[{"id":"rfc9293","url":"https://www.rfc-editor.org/rfc/rfc9293","title":"TCP"}]}
PREP
$S prep-node n1 <<'PREP'
{"objective":"explain that all transfer is packets","checks":[{"id":"q1","type":"short","variants":[{"id":"v1","question":"Why can bytes arrive out of order?","answer":"different packets, different paths","required":["different packets"]}],"hints":["what does the network forward?"]}],"status":"ready"}
PREP
$S prep-status
$S ask n1
$S pending
$S answer "they were separate packets"
$S record <<'REC'
{"result":"pass","quality":5}
REC
$S node-shaky n2 "confuses loss with corruption"
$S next-node
$S ask n2 --kind repair --adhoc <<'Q'
{"type":"short","question":"Why is a packet lost (not corrupted)?","answer":"finite buffers overflow","required":["buffers overflow"]}
Q
$S record <<'REC'
{"result":"pass","quality":4,"readiness":"provisional","reason":"repaired after the buffer example; revisit in n3"}
REC
$S ask n3 --adhoc <<'Q'
{"type":"short","question":"What is built on top?","answer":"acks and retransmission","required":["retransmission"]}
Q
$S record <<'REC'
{"result":"pass","quality":5}
REC
$S ask n3 --exit x1
$S record <<'REC'
{"result":"pass","quality":5}
REC
$S checkpoint "midway"
$S show --full
$S validate
$S history
test -f state/progress.md && echo "progress.md ok"
NOTE=$(python3 -c "import json;print(json.load(open('state/state.json'))['topics']['tcp-reliability']['note'])")
test -f "$NOTE" && echo "note ok: $NOTE"
case "$NOTE" in "$TMP"/*) echo "note is inside the temp root: ok";; *) echo "FAIL: note escaped the temp root"; exit 1;; esac

echo "== srs"
ID=$($R add --topic tcp-reliability --node n2 --type short --q "Why can a packet be lost?" --a "Finite buffers overflow; links drop frames" --points "buffers;links")
$R add --topic tcp-reliability --type mcq --q "Who retransmits?" --a "The sender" --options "The sender|The router|The receiver" >/dev/null
$R due
$R stats
$R grade "$ID" 4 --kind initial
$R grade "$ID" 5 --kind practice
$R history "$ID"
$R forecast --days 3
$R list

echo "== exercise"
$E env
$E new --topic tcp-reliability --name checksum --lang python --title "Compute a checksum"
$E new --topic tcp-reliability --name checksum-js --lang js --title "Checksum in JS" >/dev/null
$E new --topic tcp-reliability --name sum-c --lang c --title "Parallel sum" >/dev/null
$E list
set +e; $E check exercises/tcp-reliability/checksum; echo "check exit=$? (expected 1: placeholder test)"; set -e
if command -v gcc >/dev/null 2>&1; then $E validate exercises/tcp-reliability/sum-c; else echo "gcc missing: C validation skipped"; fi

echo "== transcripts"
cat > lesson.jsonl <<'JSONL'
{"type":"user","isSidechain":false,"timestamp":"2026-09-24T08:59:00.000Z","message":{"role":"user","content":"<command-name>/teach</command-name>\n<command-message>teach</command-message>\n<command-args>TCP</command-args>"}}
{"type":"user","isSidechain":false,"timestamp":"2026-09-24T09:00:00.000Z","message":{"role":"user","content":"Teach me TCP"}}
{"type":"assistant","isSidechain":false,"timestamp":"2026-09-24T09:00:05.000Z","message":{"role":"assistant","content":[{"type":"thinking","thinking":"x"},{"type":"text","text":"Let's start from packets. $x^2$"},{"type":"tool_use","id":"toolu_1","name":"AskUserQuestion","input":{"questions":[{"header":"Probe","question":"What is a packet?","options":[{"label":"A unit of data","description":"d1"},{"label":"A cable"}],"multiSelect":false}]}}]}}
{"type":"user","isSidechain":false,"timestamp":"2026-09-24T09:01:00.000Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_1","content":[{"type":"text","text":"User selected: A unit of data"}]}]}}
{"type":"user","isSidechain":true,"timestamp":"2026-09-24T09:01:00.000Z","message":{"role":"user","content":"sidechain noise"}}
{"type":"user","isSidechain":false,"timestamp":"2026-09-24T09:02:00.000Z","message":{"role":"user","content":[{"type":"text","text":"<command-name>/teach</command-name>"}]}}
{"type":"assistant","isSidechain":false,"timestamp":"2026-09-24T09:02:05.000Z","message":{"role":"assistant","content":[{"type":"text","text":"Correct. Next node."}]}}
JSONL
cat > build.jsonl <<'JSONL'
{"type":"user","isSidechain":false,"timestamp":"2026-09-24T10:00:00.000Z","message":{"role":"user","content":"Improve the scripts please"}}
{"type":"assistant","isSidechain":false,"timestamp":"2026-09-24T10:00:05.000Z","message":{"role":"assistant","content":[{"type":"text","text":"Editing state.py now."},{"type":"tool_use","id":"toolu_9","name":"Write","input":{"file_path":"x.md","content":"run python3 scripts/state.py start \"T\" then resume"}}]}}
JSONL

echo "== hooks"
echo '{"source":"startup"}' | python3 scripts/hook_session_start.py | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['hookSpecificOutput']['additionalContext'])"
python3 - <<'PY'
import json,datetime
p='state/state.json'; s=json.load(open(p)); t=s['topics'][s['active_topic']]
t['updated']=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=30)).isoformat()
json.dump(s,open(p,'w'))
PY
LESSON="{\"session_id\":\"t1\",\"transcript_path\":\"$TMP/lesson.jsonl\"}"
BUILD="{\"session_id\":\"t2\",\"transcript_path\":\"$TMP/build.jsonl\"}"
if echo "$LESSON" | python3 scripts/hook_stop_checkpoint.py | grep -q .; then echo "FAIL: blocked a lesson that just started"; exit 1; else echo "stop hook gives a fresh lesson session grace: ok"; fi
python3 - <<'PY'
import json,datetime
p='state/.cursors/t1.lesson'; d=json.load(open(p))
d['found']=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=30)).isoformat()
json.dump(d,open(p,'w'))
PY
echo "$LESSON" | python3 scripts/hook_stop_checkpoint.py | grep -q '"block"' && echo "stop hook blocks when stale in a lesson session: ok"
if echo "$BUILD" | python3 scripts/hook_stop_checkpoint.py | grep -q .; then echo "FAIL: blocked a non-lesson session"; exit 1; else echo "stop hook ignores a non-lesson session: ok"; fi
if echo "{\"stop_hook_active\":true,\"session_id\":\"t1\",\"transcript_path\":\"$TMP/lesson.jsonl\"}" | python3 scripts/hook_stop_checkpoint.py | grep -q .; then echo "FAIL: should not block on second stop"; exit 1; else echo "stop hook passes on second stop: ok"; fi
$S checkpoint "fresh"
if echo "$LESSON" | python3 scripts/hook_stop_checkpoint.py | grep -q .; then echo "FAIL: should not block when fresh"; exit 1; else echo "stop hook passes when fresh: ok"; fi
echo "{\"trigger\":\"auto\",\"session_id\":\"t1\",\"transcript_path\":\"$TMP/lesson.jsonl\"}" | python3 scripts/hook_precompact.py
test -f state/.cursors/t1.lesson && echo "lesson flag cached: ok"
test ! -f state/.cursors/t2.lesson && echo "no flag for build session: ok"

echo "== session log"
before=$(wc -c < "$NOTE")
echo "$BUILD" | python3 scripts/session_log.py
test "$(wc -c < "$NOTE")" -eq "$before" && echo "build session not mirrored: ok" || { echo "FAIL: build session leaked into the note"; exit 1; }
echo "$LESSON" | python3 scripts/session_log.py
echo "$LESSON" | python3 scripts/session_log.py
n=$(grep -c "TEACHER" "$NOTE"); test "$n" -eq 2 && echo "teacher blocks: 2 ok" || { echo "FAIL teacher blocks $n"; exit 1; }
grep -q "sidechain noise" "$NOTE" && { echo "FAIL sidechain logged"; exit 1; } || echo "sidechain skipped ok"
grep -q "command-name" "$NOTE" && { echo "FAIL command logged"; exit 1; } || echo "command skipped ok"
grep -q "Answer" "$NOTE" && echo "answer logged ok"

echo "== finish"
$S finish --summary "done"
$S show; $S topics
$S log-target "$TMP/vault/reviews/x.md"; $S log-target --clear
$S backup; $S restore --list

if [ -z "${LEARN_SELFTEST_NO_SUITE:-}" ] && [ -d "$SRC/scripts/tests" ]; then
  echo "== regression suite"
  LEARN_SELFTEST_NO_SUITE=1 python3 -m unittest discover -s "$SRC/scripts/tests" -p 'test_*.py' 2>&1 | tail -5
fi
echo "ALL OK"
