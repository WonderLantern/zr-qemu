/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Bounded, read-only AArch64 system-emulation observations. Bindings and
 * logs belong to a fingerprinted private run, not to this reusable plugin. */
#include <glib.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <qemu-plugin.h>

QEMU_PLUGIN_EXPORT int qemu_plugin_version = QEMU_PLUGIN_VERSION;
typedef struct { uint64_t pc, skip_x0; bool filtered, flush; uint64_t skipped; char name[64]; } Point;
typedef struct { uint64_t address; unsigned bytes; bool from_register; char name[64]; } Region;
typedef struct {
    struct qemu_plugin_register *reg[32];
    GByteArray *buffer;
} CPU;
static CPU cpus[4];
static Point points[128];
static Region regions[10];
static unsigned point_count, region_count;
static FILE *out;
static GMutex lock;
static uint64_t records, dropped;
static uint64_t maximum_records = 8192;
static bool label_ok(const char *s)
{
    if (!*s) return false;
    for (; *s; s++) if (!g_ascii_isalnum(*s) && *s != '_') return false;
    return true;
}
static uint64_t reg_value(CPU *cpu, unsigned index)
{
    uint64_t value = 0;
    g_byte_array_set_size(cpu->buffer, 0);
    if (cpu->reg[index] && qemu_plugin_read_register(cpu->reg[index], cpu->buffer) == 8)
        memcpy(&value, cpu->buffer->data, 8);
    return GUINT64_FROM_LE(value);
}
static void executed(unsigned int index, void *opaque)
{
    if (index >= G_N_ELEMENTS(cpus)) return;
    CPU *cpu = &cpus[index];
    Point *point = opaque;
    g_mutex_lock(&lock);
    /* Explicit profile-selected periodic events need no RAM snapshots.
     * Count them separately; they are filtered observations, not dropped
     * frame work. CPU/register/memory execution is unchanged. */
    if (point->filtered && reg_value(cpu, 0) == point->skip_x0) {
        point->skipped++; g_mutex_unlock(&lock); return;
    }
    if (records >= maximum_records) { dropped++; g_mutex_unlock(&lock); return; }
    fprintf(out, "{\"index\":%"PRIu64",\"host_us\":%"G_GINT64_FORMAT
            ",\"cpu\":%u,\"pc\":\"0x%"PRIx64"\",\"name\":\"%s\",\"registers\":[",
            records++, g_get_monotonic_time(), index, point->pc, point->name);
    for (unsigned i = 0; i < 32; i++)
        fprintf(out, "%s\"0x%"PRIx64"\"", i ? "," : "", reg_value(cpu, i));
    fputs("],\"memory\":{", out);
    for (unsigned i = 0; i < region_count; i++) {
        Region *region = &regions[i];
        uint64_t address = region->from_register ? reg_value(cpu, region->address) : region->address;
        fprintf(out, "%s\"%s\":", i ? "," : "", region->name);
        g_byte_array_set_size(cpu->buffer, 0);
        /* Native MMU aliases include the image descriptor pool. Read the
         * original virtual address through QEMU; never reinterpret it as a
         * physical address or manufacture a snapshot after a failed read. */
        bool readable = (address >= UINT64_C(0xa00000000) &&
                         address <= UINT64_C(0xa40000000) - region->bytes) ||
                        (address >= UINT64_C(0xc00000000) &&
                         address <= UINT64_C(0xc40000000) - region->bytes) ||
                        (address >= UINT64_C(0xe00000000) &&
                         address <= UINT64_C(0xe40000000) - region->bytes);
        if (!readable ||
                !qemu_plugin_read_memory_vaddr(address, cpu->buffer, region->bytes)) {
            fputs("null", out);
            continue;
        }
        static const char digits[] = "0123456789abcdef";
        char hex[8194];
        hex[0] = '"';
        for (unsigned j = 0; j < region->bytes; j++) {
            unsigned value = cpu->buffer->data[j];
            hex[1 + j * 2] = digits[value >> 4];
            hex[2 + j * 2] = digits[value & 15];
        }
        hex[1 + region->bytes * 2] = '"';
        fwrite(hex, 1, region->bytes * 2 + 2, out);
    }
    fputs("}}\n", out);
    /* Host input pacing must see a terminal callback even if no later
     * event fills the stdio buffer. Other observations retain batching. */
    if (point->flush || !(records % 64)) fflush(out);
    g_mutex_unlock(&lock);
}
static void translated(qemu_plugin_id_t id, struct qemu_plugin_tb *tb)
{
    (void)id;
    for (size_t i = 0; i < qemu_plugin_tb_n_insns(tb); i++) {
        struct qemu_plugin_insn *insn = qemu_plugin_tb_get_insn(tb, i);
        uint64_t pc = qemu_plugin_insn_vaddr(insn);
        for (unsigned j = 0; j < point_count; j++) if (pc == points[j].pc)
            qemu_plugin_register_vcpu_insn_exec_cb(insn, executed, QEMU_PLUGIN_CB_R_REGS, &points[j]);
    }
}
static void initialized(qemu_plugin_id_t id, unsigned int index)
{
    (void)id;
    if (index >= G_N_ELEMENTS(cpus)) return;
    CPU *cpu = &cpus[index];
    cpu->buffer = g_byte_array_new();
    GArray *registers = qemu_plugin_get_registers();
    for (unsigned i = 0; i < registers->len; i++) {
        qemu_plugin_reg_descriptor *r = &g_array_index(registers, qemu_plugin_reg_descriptor, i);
        for (unsigned j = 0; j < 32; j++) {
            char name[12];
            if (j == 31) g_strlcpy(name, "sp", sizeof(name));
            else g_snprintf(name, sizeof(name), "x%u", j);
            if (!strcmp(r->name, name)) cpu->reg[j] = r->handle;
        }
    }
    g_array_free(registers, TRUE);
}
static void finished(qemu_plugin_id_t id, void *opaque)
{
    (void)id; (void)opaque;
    fprintf(out, "{\"finished\":true,\"records\":%"PRIu64",\"dropped\":%"PRIu64
            ",\"maximum_records\":%"PRIu64",\"filtered\":{", records, dropped, maximum_records);
    bool first = true;
    for (unsigned i = 0; i < point_count; i++) if (points[i].filtered) {
        fprintf(out, "%s\"%s\":%"PRIu64, first ? "" : ",", points[i].name, points[i].skipped);
        first = false;
    }
    fputs("}}\n", out);
    fclose(out);
}
QEMU_PLUGIN_EXPORT int qemu_plugin_install(qemu_plugin_id_t id,
        const qemu_info_t *info, int argc, char **argv)
{
    if (strcmp(info->target_name, "aarch64") || !info->system_emulation || argc != 2 ||
            !g_str_has_prefix(argv[0], "bindings=") || !g_str_has_prefix(argv[1], "out=")) return -1;
    FILE *input = fopen(argv[0] + 9, "r");
    if (!input) return -1;
    char line[256], type, name[64], extra;
    uint64_t address;
    unsigned bytes;
    bool valid = true;
    bool limit_set = false;
    while (fgets(line, sizeof(line), input)) {
        int fields = sscanf(line, " %c %63s %"SCNx64" %u %c", &type, name, &address, &bytes, &extra);
        if (fields != 4 || !label_ok(name)) { valid = false; break; }
        if (type == 'P' && bytes == 0 && point_count < G_N_ELEMENTS(points) &&
                address >= 0x40160000 && address < 0x45000000 && !(address & 3)) {
            Point *p = &points[point_count++]; p->pc = address; g_strlcpy(p->name, name, sizeof(p->name));
        } else if (type == 'L' && !strcmp(name, "maximum_records") && bytes == 0 &&
                   !limit_set && address >= 64 && address <= 262144) {
            maximum_records = address; limit_set = true;
        } else if (type == 'F' && address == 0 && bytes == 0) {
            Point *selected = NULL;
            for (unsigned i = 0; i < point_count; i++) if (!strcmp(points[i].name, name)) selected = &points[i];
            if (!selected || selected->flush) { valid = false; break; }
            selected->flush = true;
        } else if (type == 'S' && bytes == 0) {
            Point *selected = NULL;
            for (unsigned i = 0; i < point_count; i++) if (!strcmp(points[i].name, name)) selected = &points[i];
            if (!selected || selected->filtered) { valid = false; break; }
            selected->filtered = true; selected->skip_x0 = address;
        } else if (region_count < G_N_ELEMENTS(regions) && bytes && bytes <= 4096 &&
                ((type == 'M' && address >= UINT64_C(0xa00000000) &&
                  address <= UINT64_C(0xa40000000) - bytes) || (type == 'D' && address < 32))) {
            Region *r = &regions[region_count++]; r->address = address; r->bytes = bytes;
            r->from_register = type == 'D';
            g_strlcpy(r->name, name, sizeof(r->name));
        } else { valid = false; break; }
    }
    fclose(input);
    if (!valid || !point_count) return -1;
    out = fopen(argv[1] + 4, "wx");
    if (!out) return -1;
    qemu_plugin_register_vcpu_init_cb(id, initialized);
    qemu_plugin_register_vcpu_tb_trans_cb(id, translated);
    qemu_plugin_register_atexit_cb(id, finished, NULL);
    return 0;
}
