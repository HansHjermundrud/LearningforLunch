#include <omp.h>
#include <stddef.h>

/* Reference: one indivisible update per element; different bins proceed concurrently. */
void histogram(const int *x, size_t n, int *hist, int bins)
{
    #pragma omp parallel for
    for (size_t i = 0; i < n; i++) {
        int b = x[i] % bins;
        #pragma omp atomic
        hist[b]++;
    }
}
