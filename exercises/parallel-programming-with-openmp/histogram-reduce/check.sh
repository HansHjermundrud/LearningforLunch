#!/usr/bin/env bash
# Usage: bash check.sh [FILE]   (FILE defaults to solution.c; use it for retries, e.g. retry-2026-10-01.c)
set -u
cd "$(dirname "$0")"
file="${1:-solution.c}"
timeout_s="${CHECK_TIMEOUT:-60}"
if [ ! -f "$file" ]; then echo "FAIL: no such file $file"; exit 2; fi
CC="${CC:-gcc}"
if ! command -v "$CC" >/dev/null 2>&1; then
    echo "FAIL: compiler '$CC' not found. Install gcc (Ubuntu: sudo apt install build-essential) or set CC."; exit 3
fi
if ! echo 'int main(void){return 0;}' | "$CC" -fopenmp -x c - -o /dev/null 2>/dev/null; then
    echo "FAIL: '$CC' cannot build with -fopenmp (libgomp missing?). Ubuntu: sudo apt install gcc libgomp1"; exit 3
fi
if grep -q '__SOLUTION_MARKER__' test_main.c 2>/dev/null; then echo "FAIL: test_main.c still has the template marker"; exit 2; fi
# structural check: the task forbids per-element synchronization; the loop body must not contain atomic
if grep -q 'omp atomic' "$file"; then echo "FAIL: the loop still uses atomic; use a reduction or a private histogram combined once"; exit 1; fi
if ! grep -Eq 'reduction\(|critical|omp_(set|unset)_lock' "$file"; then echo "FAIL: no reduction and no single combine step found (reduction(...) clause, or a private histogram merged under critical/a lock)"; exit 1; fi
if ! "$CC" -std=c11 -O2 -Wall -Wextra -fopenmp "$file" test_main.c -lm -o .test_bin 2>.build.log; then
    echo "FAIL: does not compile:"; grep -E 'error|warning' .build.log | head -20; exit 1
fi
if grep -q 'warning' .build.log; then echo "warnings:"; grep -E 'warning' .build.log | head -10; fi
if command -v timeout >/dev/null 2>&1; then
    timeout "$timeout_s" ./.test_bin; rc=$?
    if [ $rc -eq 124 ]; then echo "FAIL: timed out after ${timeout_s}s (deadlock, livelock or far too slow?)"; fi
else
    ./.test_bin; rc=$?
fi
exit $rc
