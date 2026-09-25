#include <stdio.h>
#include <string.h>

void scale_all(const double *a, double *b, int n, double scale, double *last_out);
void mark_slots(int *slots, int base);

#define N 100000
static double a[N], b[N];

static int check_scale(int n, int run)
{
    double last = -12345.0;
    for (int i = 0; i < n; i++) { a[i] = i; b[i] = 0.0; }
    scale_all(a, b, n, 2.0, &last);
    for (int i = 0; i < n; i++)
        if (b[i] != 2.0 * i + 1) {
            printf("FAIL scale_all (n=%d, run %d): b[%d] = %g, expected %g\n", n, run, i, b[i], 2.0 * i + 1);
            return 1;
        }
    if (last != 2.0 * (n - 1) + 1) {
        printf("FAIL scale_all (n=%d, run %d): last = %g, expected b[n-1] = %g\n", n, run, last, 2.0 * (n - 1) + 1);
        return 1;
    }
    return 0;
}

static int check_slots(int base, int run)
{
    int slots[64];
    memset(slots, 0, sizeof slots);
    mark_slots(slots, base);
    for (int k = 0; k < 64; k++) {
        int want = (k >= base && k < base + 4);
        if (slots[k] != want) {
            printf("FAIL mark_slots (base=%d, run %d): slots[%d] = %d, expected %d\n", base, run, k, slots[k], want);
            return 1;
        }
    }
    return 0;
}

int main(void)
{
    for (int run = 0; run < 200; run++) {
        if (check_scale(N, run) || check_scale(1, run)) return 1;
        if (check_slots(10, run) || check_slots(0, run)) return 1;
    }
    printf("PASS: scale_all (n=%d and n=1) and mark_slots (base 10 and 0), 200 runs each on 8 threads\n", N);
    return 0;
}
