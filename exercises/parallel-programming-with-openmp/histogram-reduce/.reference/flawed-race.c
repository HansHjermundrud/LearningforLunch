#include <omp.h>
#include <stddef.h>

/* No reduction, no atomic: a data race. FAIL-or-unreliable. Also rejected by check.sh's structural test. */
void histogram(const int *x, size_t n, int *hist, int bins)
{
    #pragma omp parallel for
    for (size_t i = 0; i < n; i++)
        hist[x[i] % bins]++;
}
