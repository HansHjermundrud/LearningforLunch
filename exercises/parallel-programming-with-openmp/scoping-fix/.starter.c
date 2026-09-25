#include <omp.h>

/*
 * Part 1. For every i: b[i] = scale * a[i] + 1.
 * Afterwards *last_out must hold b[n-1], exactly as in a sequential run.
 */
void scale_all(const double *a, double *b, int n, double scale, double *last_out)
{
    double tmp;
    double last = 0.0;
    int i;

    #pragma omp parallel for default(none)
    for (i = 0; i < n; i++) {
        tmp = scale * a[i];
        b[i] = tmp + 1;
        last = b[i];
    }

    *last_out = last;
}

/*
 * Part 2. A team of 4 threads. Thread t must set slots[base + t] = 1,
 * so with base = 10 exactly slots[10], slots[11], slots[12], slots[13] are set.
 */
void mark_slots(int *slots, int base)
{
    #pragma omp parallel num_threads(4) default(none)
    {
        base += omp_get_thread_num();
        slots[base] = 1;
    }
}
