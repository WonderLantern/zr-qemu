/* SPDX-License-Identifier: GPL-2.0-or-later
 * Explicit functional FAST-9 and integer SAD translation, not Nikon KRAN.
 * Original messages19/1a/1b name initialization/KLT-RANSAC/FAST. The static
 * output view has32 header bytes,128x16 point records and20 trailer bytes.
 * Arithmetic, threshold, age word and translation classification below are
 * declared functional conventions; no CEVA instruction is executed.
 */
#define WL_MOTION_POINTS 128
#define WL_MOTION_RESULT_BYTES 0x834
typedef struct WlMotionPoint { uint16_t x, y, age; } WlMotionPoint;
typedef struct WlMotionHistory {
    uint8_t *previous;
    unsigned width, height, stride, count;
    WlMotionPoint points[WL_MOTION_POINTS];
} WlMotionHistory;
typedef struct WlMotionJob {
    QEMUTimer *timer;
    uint8_t *input;
    uint64_t config, source, result, workspace;
    unsigned width, height, stride, input_bytes, result_bytes, opcode, group;
    bool scheduled, ready, rx;
    WlMotionHistory history[2];
    uint64_t requests, completed, replies, acks, cancelled, bytes_read, bytes_written;
    uint32_t input_crc, result_crc, features, tracks, inliers, reject;
    int32_t dx, dy;
} WlMotionJob;

static void motion_history_clear(WlMotionHistory *h)
{ g_free(h->previous); memset(h, 0, sizeof(*h)); }

static void motion_job_reset(WlMotionJob *m)
{
    if (m->scheduled || m->ready || m->rx) { m->cancelled++; }
    if (m->timer) { timer_del(m->timer); }
    g_free(m->input); m->input = NULL;
    m->scheduled = m->ready = m->rx = false;
    for (unsigned i = 0; i < 2; i++) { motion_history_clear(&m->history[i]); }
}

static unsigned motion_corner_score(const uint8_t *input, unsigned stride,
                                     unsigned x, unsigned y)
{
    static const int ring[16][2] = {
        {0,-3},{1,-3},{2,-2},{3,-1},{3,0},{3,1},{2,2},{1,3},
        {0,3},{-1,3},{-2,2},{-3,1},{-3,0},{-3,-1},{-2,-2},{-1,-3}
    };
    int center = input[(size_t)y * stride + x], values[16];
    for (unsigned i = 0; i < 16; i++) {
        values[i] = (int)input[(size_t)((int)y + ring[i][1]) * stride + (int)x + ring[i][0]] - center;
    }
    unsigned best = 0;
    for (unsigned start = 0; start < 16; start++) {
        int bright = 255, dark = 255;
        for (unsigned n = 0; n < 9; n++) {
            int difference = values[(start + n) & 15];
            bright = MIN(bright, difference); dark = MIN(dark, -difference);
        }
        best = MAX(best, MAX(0, MAX(bright, dark)));
    }
    return best;
}

/* One strong candidate per16x16 cell followed by score order and8px
 * spacing keeps the pool bounded and spread over the actual image. */
static unsigned motion_seed(WlMotionHistory *h, const uint8_t *input)
{
    typedef struct { unsigned x, y, score; } Candidate;
    unsigned nx = (h->width + 15) / 16, ny = (h->height + 15) / 16;
    Candidate *cells = g_new0(Candidate, (size_t)nx * ny);
    for (unsigned y = 7; y + 7 < h->height; y++) {
        for (unsigned x = 7; x + 7 < h->width; x++) {
            unsigned score = motion_corner_score(input, h->stride, x, y);
            Candidate *cell = &cells[(y / 16) * nx + x / 16];
            if (score > 16 && score > cell->score) { *cell = (Candidate){x, y, score}; }
        }
    }
    unsigned added = 0;
    while (h->count < WL_MOTION_POINTS) {
        Candidate best = {0}; unsigned index = 0;
        for (unsigned i = 0; i < nx * ny; i++) {
            if (cells[i].score > best.score) { best = cells[i]; index = i; }
        }
        if (!best.score) { break; }
        cells[index].score = 0;
        bool near = false;
        for (unsigned i = 0; i < h->count; i++) {
            int dx = (int)h->points[i].x - (int)best.x, dy = (int)h->points[i].y - (int)best.y;
            if (dx * dx + dy * dy < 64) { near = true; break; }
        }
        if (!near) { h->points[h->count++] = (WlMotionPoint){best.x, best.y, 1}; added++; }
    }
    g_free(cells);
    return added;
}

static unsigned motion_patch_sad(const WlMotionHistory *h, const uint8_t *current,
                                  unsigned x, unsigned y, int dx, int dy)
{
    unsigned sad = 0;
    for (int row = -3; row <= 3; row++) {
        for (int col = -3; col <= 3; col++) {
            int a = h->previous[(size_t)((int)y + row) * h->stride + (int)x + col];
            int b = current[(size_t)((int)y + row + dy) * h->stride + (int)x + col + dx];
            sad += abs(a - b);
        }
    }
    return sad;
}

static int motion_median(int *values, unsigned count)
{
    for (unsigned i = 1; i < count; i++) {
        int value = values[i]; unsigned j = i;
        while (j && values[j - 1] > value) { values[j] = values[j - 1]; j--; }
        values[j] = value;
    }
    return count ? values[count / 2] : 0;
}

static void motion_track(WlMotionJob *m, WlMotionHistory *h, uint8_t *result)
{
    int vx[WL_MOTION_POINTS], vy[WL_MOTION_POINTS];
    WlMotionPoint kept[WL_MOTION_POINTS];
    unsigned count = 0;
    for (unsigned i = 0; h->previous && i < h->count; i++) {
        WlMotionPoint point = h->points[i]; unsigned x = point.x, y = point.y;
        if (x < 7 || y < 7 || x + 7 >= h->width || y + 7 >= h->height) { continue; }
        int best_x = 0, best_y = 0;
        unsigned best = motion_patch_sad(h, m->input, x, y, 0, 0);
        if (best) {
            for (int dy = -4; dy <= 4; dy++) {
                for (int dx = -4; dx <= 4; dx++) {
                    unsigned sad = motion_patch_sad(h, m->input, x, y, dx, dy);
                    if (sad < best) { best = sad; best_x = dx; best_y = dy; }
                }
            }
        }
        if (best > 49 * 32) { continue; }
        uint8_t *record = result + 32 + count * 16;
        stw_le_p(record, x); stw_le_p(record + 2, y);
        stw_le_p(record + 4, x + best_x); stw_le_p(record + 6, y + best_y);
        stw_le_p(record + 8, point.age); /* Explicit functional age convention. */
        stl_le_p(record + 12, 65536 - (uint64_t)best * 65536 / (49 * 255));
        vx[count] = best_x; vy[count] = best_y;
        kept[count] = (WlMotionPoint){x + best_x, y + best_y, MIN(65535, point.age + 1)};
        count++;
    }
    int sorted_x[WL_MOTION_POINTS], sorted_y[WL_MOTION_POINTS];
    memcpy(sorted_x, vx, count * sizeof(int)); memcpy(sorted_y, vy, count * sizeof(int));
    m->dx = motion_median(sorted_x, count); m->dy = motion_median(sorted_y, count);
    unsigned inliers = 0;
    for (unsigned i = 0; i < count; i++) {
        inliers += abs(vx[i] - m->dx) <= 1 && abs(vy[i] - m->dy) <= 1;
    }
    m->tracks = count; m->inliers = inliers;
    if (count >= 3 && inliers * 2 >= count) {
        stl_le_p(result, 2); /* Functional valid translation, not original KRAN classification. */
        stl_le_p(result + 20, m->dx); stl_le_p(result + 24, m->dy);
        stl_le_p(result + 28, inliers * 128 / count);
    }
    stl_le_p(result + 16, count); stl_le_p(result + 0x820, count);
    memcpy(h->points, kept, count * sizeof(WlMotionPoint)); h->count = count;
}

static void motion_compute(WlMotionJob *m, uint8_t *result)
{
    WlMotionHistory *h = &m->history[m->group];
    if (h->width != m->width || h->height != m->height || h->stride != m->stride) {
        motion_history_clear(h); h->width = m->width; h->height = m->height; h->stride = m->stride;
    }
    m->features = m->tracks = m->inliers = 0; m->dx = m->dy = 0;
    if (m->opcode == 0x1b) { m->features = motion_seed(h, m->input); stl_le_p(result, m->features); }
    else { motion_track(m, h, result); }
    g_free(h->previous); h->previous = m->input; m->input = NULL;
}
