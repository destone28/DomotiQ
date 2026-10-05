/* SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
   SPDX-License-Identifier: MIT */
/* Check the dot products of the CPU backend against a reference in double precision on the dequantized values:
   q5_0, q8_0 (with q8_0), q4_K, q6_K (with q8_K), one row by one column and, where the backend does it, two
   rows by two columns. vdtest [trials] */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ggml.h"
#include "ggml-cpu.h"

static uint64_t rng = 0x9E3779B97F4A7C15ull;
static float frand(void) {
    rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
    return (float)((rng >> 11) * (1.0 / 9007199254740992.0)) * 2.0f - 1.0f;
}

typedef struct { float d; int8_t qs[256]; int16_t bsums[16]; } q8_K_block;   /* as in ggml-common.h */

static void to_float(enum ggml_type t, const void *v, float *out, int n) {
    if (t == GGML_TYPE_Q8_K) {                    /* ggml has no dequantization for it: d * q */
        const q8_K_block *b = v;
        for (int i = 0; i < n; i++) out[i] = b[i / 256].d * b[i / 256].qs[i % 256];
        return;
    }
    ggml_get_type_traits(t)->to_float(v, out, n);
}

static double ref_dot(enum ggml_type tx, const void *x, enum ggml_type ty, const void *y, int n) {
    float *a = malloc(sizeof(float) * n), *b = malloc(sizeof(float) * n);
    to_float(tx, x, a, n);
    to_float(ty, y, b, n);
    double s = 0;
    for (int i = 0; i < n; i++) s += (double)a[i] * b[i];
    free(a); free(b);
    return s;
}

int main(int argc, char **argv) {
    const int trials = argc > 1 ? atoi(argv[1]) : 200;
    setvbuf(stdout, NULL, _IONBF, 0);
    ggml_cpu_init();
    const enum ggml_type types[] = { GGML_TYPE_Q5_0, GGML_TYPE_Q8_0, GGML_TYPE_Q4_K, GGML_TYPE_Q6_K };
    int failed = 0;
    for (size_t t = 0; t < sizeof(types) / sizeof(types[0]); t++) {
        const enum ggml_type tx = types[t];
        const struct ggml_type_traits_cpu *cpu = ggml_get_type_traits_cpu(tx);
        const enum ggml_type ty = cpu->vec_dot_type;
        const int n = ggml_blck_size(tx) == 256 ? 4864 : 896;              /* the row lengths of the model */
        const size_t rx = ggml_row_size(tx, n), ry = ggml_row_size(ty, n);
        uint8_t *x = malloc(2 * rx), *y = malloc(2 * ry);
        float *f = malloc(sizeof(float) * 2 * n);
        double worst1 = 0, worst2 = 0;
        for (int k = 0; k < trials; k++) {
            /* rows of varied scale, sometimes with large outliers, as real weights and activations */
            const float scale = 0.01f + 3.0f * fabsf(frand());
            for (int i = 0; i < 2 * n; i++) f[i] = frand() * scale * (frand() > 0.98f ? 8.0f : 1.0f);
            ggml_quantize_chunk(tx, f, x, 0, 2, n, NULL);
            for (int i = 0; i < 2 * n; i++) f[i] = frand() * scale;
            ggml_get_type_traits_cpu(ty)->from_float(f, y, n);
            ggml_get_type_traits_cpu(ty)->from_float(f + n, y + ry, n);
            double norm = 0;
            for (int r = 0; r < 2; r++) for (int c = 0; c < 2; c++) {
                const double e = ref_dot(tx, x + r * rx, ty, y + c * ry, n);
                norm = fmax(norm, fabs(e));
            }
            float s1;
            cpu->vec_dot(n, &s1, 0, x, 0, y, 0, 1);
            const double e1 = ref_dot(tx, x, ty, y, n);
            worst1 = fmax(worst1, fabs(s1 - e1) / fmax(norm, 1e-6));
            if (cpu->nrows == 2) {
                float s2[4];                                        /* s[0], s[1] | s[2], s[3]: bs = 2 */
                cpu->vec_dot(n, s2, 2, x, rx, y, ry, 2);
                const double e[4] = { ref_dot(tx, x, ty, y, n), ref_dot(tx, x + rx, ty, y, n),
                                      ref_dot(tx, x, ty, y + ry, n), ref_dot(tx, x + rx, ty, y + ry, n) };
                for (int q = 0; q < 4; q++) worst2 = fmax(worst2, fabs(s2[q] - e[q]) / fmax(norm, 1e-6));
            }
        }
        const int bad = worst1 > 1e-5 || worst2 > 1e-5;
        failed |= bad;
        printf("%-5s x %-5s n=%d  rows at a time %ld  worst relative error: 1x1 %.2e  2x2 %.2e  %s\n",
               ggml_type_name(tx), ggml_type_name(ty), n, (long)cpu->nrows, worst1, worst2, bad ? "FAILED" : "ok");
        free(x); free(y); free(f);
    }
    return failed;
}
