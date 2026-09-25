#include <omp.h>
#include <stddef.h>

/* Race-free but skips the last element: must FAIL deterministically for n >= 1. */
void histogram(const int *x, size_t n, int *hist, int bins)
{
    if (n == 0) return;
    #pragma omp parallel for
    for (size_t i = 0; i + 1 < n; i++) {
        int b = x[i] % bins;
        #pragma omp atomic
        hist[b]++;
    }
}
