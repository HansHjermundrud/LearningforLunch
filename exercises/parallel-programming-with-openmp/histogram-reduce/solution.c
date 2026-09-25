#include <omp.h>
#include <stddef.h>

/*
 * Same histogram as histogram-sync (bin = x[i] % bins, x[i] >= 0, hist may hold
 * prior counts that must be added to). This version is race-free with atomic,
 * but every element contends for shared memory.
 *
 * Rewrite it so that no atomic or critical runs inside the loop: use a
 * reduction over the array section hist[0:bins], or an explicit per-thread
 * histogram combined once at the end. The result must stay identical.
 */
void histogram(const int *x, size_t n, int *hist, int bins)
{
    #pragma omp parallel for
    for (size_t i = 0; i < n; i++) {
        int b = x[i] % bins;
        #pragma omp atomic
        hist[b]++;
    }
}
