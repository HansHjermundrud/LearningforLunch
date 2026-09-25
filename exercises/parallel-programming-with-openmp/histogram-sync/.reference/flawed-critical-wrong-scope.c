#include <omp.h>
#include <stddef.h>

/* Race-free and correct, but serializes the whole body (bin computation too): PASSES; kept as the
   'correct but wasteful' comparison for perf.sh, not as a failing variant. */
void histogram(const int *x, size_t n, int *hist, int bins)
{
    #pragma omp parallel for
    for (size_t i = 0; i < n; i++) {
        #pragma omp critical
        {
            int b = x[i] % bins;
            hist[b]++;
        }
    }
}
