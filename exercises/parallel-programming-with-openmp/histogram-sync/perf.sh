#!/usr/bin/env bash
# Optional performance experiment. NOT part of the grade: timings are noisy and a
# correct solution is not "wrong" because a run was slow. Compare threads=1 vs more.
set -u
cd "$(dirname "$0")"
file="${1:-solution.c}"
gcc -std=c11 -O2 -Wall -fopenmp "$file" test_main.c -lm -o .perf_bin || exit 1
for t in 1 2 4 8; do
    printf "threads=%d  " "$t"
    OMP_NUM_THREADS=$t /usr/bin/env time -f "%es elapsed" ./.perf_bin >/dev/null 2>.perf_time; tail -1 .perf_time
done
