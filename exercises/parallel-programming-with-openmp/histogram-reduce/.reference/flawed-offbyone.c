#include <omp.h>
#include <stddef.h>

/* Deliberately wrong: skips the last element. Must FAIL deterministically. */
double solve(const double *a, size_t n)
{
    double s = 0.0;
    if (n == 0) return 0.0;
    #pragma omp parallel for reduction(+:s)
    for (size_t i = 0; i + 1 < n; i++) s += a[i];
    return s;
}
