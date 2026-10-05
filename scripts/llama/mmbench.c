/* SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
   SPDX-License-Identifier: MIT */
/* Time one matrix product of ggml (weights of a quantized type times f32 activations), as llama.cpp runs it,
   and write the result to a file so that two builds can be compared.
   mmbench <type> <rows m> <row length k> <columns n> <threads> <runs> [out.bin] */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "ggml.h"
#include "ggml-cpu.h"

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

static uint64_t rng = 88172645463325252ull;
static float frand(void) {  /* xorshift, the same numbers in every build */
    rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
    return (float)((rng >> 11) * (1.0 / 9007199254740992.0)) * 2.0f - 1.0f;
}

int main(int argc, char **argv) {
    if (argc < 7) { fprintf(stderr, "mmbench type m k n threads runs [out]\n"); return 1; }
    enum ggml_type type = GGML_TYPE_COUNT;
    for (int t = 0; t < GGML_TYPE_COUNT; t++) {
        const char *name = ggml_type_name((enum ggml_type)t);
        if (name && strcmp(name, argv[1]) == 0) type = (enum ggml_type)t;
    }
    if (type == GGML_TYPE_COUNT) { fprintf(stderr, "unknown type %s\n", argv[1]); return 1; }
    const int m = atoi(argv[2]), k = atoi(argv[3]), n = atoi(argv[4]), nth = atoi(argv[5]), runs = atoi(argv[6]);
    struct ggml_init_params ip = { (size_t)1 << 30, NULL, false };
    struct ggml_context *ctx = ggml_init(ip);
    struct ggml_tensor *a = ggml_new_tensor_2d(ctx, type, k, m);
    struct ggml_tensor *b = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, k, n);
    float *tmp = malloc(sizeof(float) * (size_t)k * m);
    for (size_t i = 0; i < (size_t)k * m; i++) tmp[i] = frand();
    ggml_quantize_chunk(type, tmp, a->data, 0, m, k, NULL);
    for (size_t i = 0; i < (size_t)k * n; i++) ((float *)b->data)[i] = frand();
    struct ggml_tensor *c = ggml_mul_mat(ctx, a, b);
    struct ggml_cgraph *gf = ggml_new_graph(ctx);
    ggml_build_forward_expand(gf, c);
    struct ggml_cplan plan = ggml_graph_plan(gf, nth, NULL);
    plan.work_data = malloc(plan.work_size + 1);
    ggml_graph_compute(gf, &plan);                     /* warm up */
    double best = 1e9, total = 0;
    for (int r = 0; r < runs; r++) {
        double t0 = now();
        ggml_graph_compute(gf, &plan);
        double dt = now() - t0;
        total += dt;
        if (dt < best) best = dt;
    }
    const double flop = 2.0 * m * n * k;
    printf("%-5s m=%-6d k=%-5d n=%-4d t=%d  best %8.3f ms  mean %8.3f ms  %6.2f GFLOPS\n", argv[1], m, k, n, nth,
           best * 1e3, total / runs * 1e3, flop / best / 1e9);
    if (argc > 7) {
        FILE *f = fopen(argv[7], "wb");
        fwrite(c->data, sizeof(float), (size_t)m * n, f);
        fclose(f);
    }
    return 0;
}
