#include <omp.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

/* Alternative reference: explicit private histogram per thread, one combine at the end. */
void histogram(const int *x, size_t n, int *hist, int bins)
{
    #pragma omp parallel
    {
        int *local = calloc(bins, sizeof *local);
        #pragma omp for
        for (size_t i = 0; i < n; i++)
            local[x[i] % bins]++;
        #pragma omp critical
        for (int b = 0; b < bins; b++) hist[b] += local[b];
        free(local);
    }
}
