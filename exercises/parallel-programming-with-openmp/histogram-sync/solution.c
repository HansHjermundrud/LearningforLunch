#include <omp.h>
#include <stddef.h>

/*
 * Count how many x[i] fall into each of `bins` bins, where the bin of x[i] is
 * x[i] % bins (all x[i] >= 0). hist[0..bins-1] may already hold counts: add to
 * them, exactly as the serial loop would.
 *
 * The loop below has a data race. Make it race-free with the cheapest construct
 * that suffices, keep the parallel for, and keep the result identical to serial.
 */
void histogram(const int *x, size_t n, int *hist, int bins)
{
    #pragma omp parallel for
    for (size_t i = 0; i < n; i++) {
        int b = x[i] % bins;
        hist[b]++;
    }
}
