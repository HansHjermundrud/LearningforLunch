#include <omp.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

/* Wrong: the private copies start from the ORIGINAL's contents instead of the identity, so
   prior counts are added once per thread. Deterministic FAIL whenever hist is non-zero and threads > 1. */
void histogram(const int *x, size_t n, int *hist, int bins)
{
    #pragma omp parallel
    {
        int *local = malloc(bins * sizeof *local);
        memcpy(local, hist, bins * sizeof *local);
        #pragma omp for
        for (size_t i = 0; i < n; i++)
            local[x[i] % bins]++;
        #pragma omp barrier
        #pragma omp critical
        for (int b = 0; b < bins; b++) hist[b] += local[b];
        free(local);
    }
}
