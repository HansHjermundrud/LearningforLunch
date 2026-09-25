#include <omp.h>
#include <stddef.h>

/* The starter as handed out: a data race on hist[b]. Usually FAILS with 2+ threads and 4M elements, but not guaranteed to. */
void histogram(const int *x, size_t n, int *hist, int bins)
{
    #pragma omp parallel for
    for (size_t i = 0; i < n; i++) {
        int b = x[i] % bins;
        hist[b]++;
    }
}
