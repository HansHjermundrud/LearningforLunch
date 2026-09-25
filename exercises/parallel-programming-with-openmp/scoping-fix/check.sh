#!/usr/bin/env bash
# Checks: only #pragma lines changed, tmp is privatized, it compiles, and 200 runs on 8 threads pass.
set -u
cd "$(dirname "$0")"
file="${1:-solution.c}"

if ! diff -q <(grep -v '#pragma' .starter.c) <(grep -v '#pragma' "$file") >/dev/null; then
    echo "FAIL: only the #pragma lines may change (no moved or removed declarations)."
    diff <(grep -v '#pragma' .starter.c) <(grep -v '#pragma' "$file")
    exit 1
fi
if ! grep '#pragma' "$file" | grep -Eq 'private\([^)]*\btmp\b'; then
    echo "FAIL: tmp is still shared. Every iteration writes it, so that is a race (a test run cannot reliably catch it)."
    exit 1
fi
if ! gcc -O2 -Wall -fopenmp "$file" test_main.c -o .test_bin 2>.build.log; then
    echo "FAIL: does not compile:"
    grep -E 'error' .build.log
    exit 1
fi
OMP_NUM_THREADS=8 ./.test_bin
