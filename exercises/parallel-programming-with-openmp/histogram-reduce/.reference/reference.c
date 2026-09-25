#include <omp.h>
#include <stddef.h>

/* Reference: array-section reduction. Private copies start at 0 and are combined into hist at the end,
   so hist's prior contents are preserved. */
void histogram(const int *x, size_t n, int *hist, int bins)
{
    #pragma omp parallel for reduction(+:hist[0:bins])
    for (size_t i = 0; i < n; i++) {
        int b = x[i] % bins;
        hist[b]++;
    }
}
