`bash check.sh` (or `bash check.sh retry-YYYY-MM-DD.c` for a retry file) does four things:

1. Checks that only `#pragma` lines differ from the starter (declarations stay where they are).
2. Checks that `tmp` appears in a `private`, `firstprivate` or `lastprivate` clause. A race on `tmp` is real but often invisible in a test run, so it is checked by reading the pragma.
3. Compiles with `gcc -O2 -Wall -fopenmp` together with `test_main.c`.
4. Runs 200 rounds on 8 threads:
   - `scale_all` with `a[i] = i`, `scale = 2`, n = 100000 and the edge case n = 1: every `b[i] == 2i + 1` and `last == b[n-1]`.
   - `mark_slots` with base 10 and the edge case base 0: exactly `slots[base..base+3]` are 1, everything else 0.
