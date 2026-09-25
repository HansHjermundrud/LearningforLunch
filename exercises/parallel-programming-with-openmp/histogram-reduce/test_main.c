#include <omp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void histogram(const int *x, size_t n, int *hist, int bins);

/* Serial oracle. */
static void oracle(const int *x, size_t n, int *hist, int bins)
{
    for (size_t i = 0; i < n; i++) hist[x[i] % bins]++;
}

static int check(size_t n, int bins, int threads, int run)
{
    int *x = malloc((n ? n : 1) * sizeof *x);
    int *want = calloc(bins, sizeof *want), *got = calloc(bins, sizeof *got);
    if (!x || !want || !got) { printf("FAIL: malloc\n"); return 1; }
    unsigned s = 12345u + (unsigned)run;
    for (size_t i = 0; i < n; i++) { s = s * 1103515245u + 12345u; x[i] = (int)((s >> 8) % 100003u); }
    /* prior counts: the function must ADD to them, like the serial loop */
    for (int b = 0; b < bins; b++) want[b] = got[b] = (b * 7) % 5;
    oracle(x, n, want, bins);
    omp_set_num_threads(threads);
    histogram(x, n, got, bins);
    int bad = 0;
    for (int b = 0; b < bins; b++)
        if (got[b] != want[b]) {
            if (!bad) printf("FAIL n=%zu bins=%d threads=%d run=%d: hist[%d] = %d, expected %d\n", n, bins, threads, run, b, got[b], want[b]);
            bad = 1;
        }
    free(x); free(want); free(got);
    return bad;
}

int main(void)
{
    const size_t sizes[] = {0, 1, 1000, 1000000, 4000000};
    const int binsv[] = {1, 7, 64};
    const int threads[] = {1, 2, 3, 8};
    int fails = 0, runs = 0;
    for (size_t a = 0; a < sizeof sizes / sizeof *sizes; a++)
        for (size_t b = 0; b < sizeof binsv / sizeof *binsv; b++)
            for (size_t t = 0; t < sizeof threads / sizeof *threads; t++)
                for (int run = 0; run < 3; run++) {
                    runs++;
                    if (check(sizes[a], binsv[b], threads[t], run)) { fails++; if (fails >= 3) goto done; }
                }
done:
    if (fails) { printf("FAIL: %d of %d runs failed\n", fails, runs); return 1; }
    printf("PASS: %d runs over %zu sizes, %zu bin counts and %zu thread counts (exact integer match, prior counts preserved)\n",
           runs, sizeof sizes / sizeof *sizes, sizeof binsv / sizeof *binsv, sizeof threads / sizeof *threads);
    printf("NOTE: passing runs do not prove the absence of a data race; explain which accesses your construct orders.\n");
    return 0;
}
