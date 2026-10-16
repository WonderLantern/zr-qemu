/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Read-only context-field provenance. Private bindings and traces are inputs
 * and outputs, never embedded firmware. A bounded lookback also observes
 * writes made before the original reader first identifies its context. */
#include <glib.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <qemu-plugin.h>

QEMU_PLUGIN_EXPORT int qemu_plugin_version = QEMU_PLUGIN_VERSION;
#define HISTORY 65536
#define CONTEXTS 512
#define MAX_RECORDS 65536
#define CALL_HISTORY 4096
typedef struct {
    uint64_t sequence, pc, address, physical;
    gint64 host_us;
    unsigned cpu, bytes;
    uint8_t value[16];
} Write;
typedef struct { struct qemu_plugin_register *reg, *argument[4]; GByteArray *buffer; } CPU;
typedef struct { uint64_t sequence,pc,destination,arg1,bytes,lr;gint64 host_us;unsigned cpu; } Call;
static CPU cpus[4];
static Write history[HISTORY];
static Call calls[CALL_HISTORY];
static uint64_t contexts[CONTEXTS], heap_low, heap_high, reader_pc;
static uint64_t helper_pc[2], helper_calls, helper_matches;
static uint64_t globals[3], global_stores;
static unsigned context_count, reader_register;
static uint64_t heap_writes, records, dropped, context_overflow;
static uint64_t prior_matches, subsequent_matches;
static FILE *out;
static GMutex lock;

static uint64_t register_value(CPU *c, struct qemu_plugin_register *reg)
{
    uint64_t value=0;g_byte_array_set_size(c->buffer,0);
    if(reg && qemu_plugin_read_register(reg,c->buffer)==8) memcpy(&value,c->buffer->data,8);
    return GUINT64_FROM_LE(value);
}
static void emit_call(const Call *c, uint64_t context, bool prior)
{
    if(records>=MAX_RECORDS) { dropped++;return; }
    fprintf(out,"{\"index\":%"PRIu64",\"kind\":\"%s\",\"cpu\":%u,"
        "\"call_sequence\":%"PRIu64",\"pc\":\"0x%"PRIx64"\","
        "\"host_us\":%"G_GINT64_FORMAT",\"context\":\"0x%"PRIx64"\",\"destination\":\"0x%"PRIx64"\","
        "\"arg1\":\"0x%"PRIx64"\",\"bytes\":%"PRIu64",\"caller_lr\":\"0x%"PRIx64"\"}\n",
        records++,prior?"lookback_helper_enter":"helper_enter",c->cpu,c->sequence,c->pc,
        c->host_us,context,c->destination,c->arg1,c->bytes,c->lr);
    helper_matches++;
}
static void helper(unsigned cpu, void *opaque)
{
    if(cpu>=G_N_ELEMENTS(cpus)) return;
    CPU *c=&cpus[cpu];Call call={.pc=(uintptr_t)opaque,.cpu=cpu,.host_us=g_get_monotonic_time()};
    call.destination=register_value(c,c->argument[0]);
    if(call.destination<heap_low || call.destination>=heap_high) return;
    call.arg1=register_value(c,c->argument[1]);call.bytes=register_value(c,c->argument[2]);
    call.lr=register_value(c,c->argument[3]);
    if(!call.bytes || call.bytes>heap_high-call.destination) return;
    g_mutex_lock(&lock);call.sequence=helper_calls++;
    calls[call.sequence%CALL_HISTORY]=call;
    for(unsigned i=0;i<context_count;i++) {
        uint64_t field=contexts[i]+0x20;
        if(call.destination<=field && field-call.destination<call.bytes) emit_call(&call,contexts[i],false);
    }
    g_mutex_unlock(&lock);
}

static void bytes_json(const uint8_t *data, unsigned bytes)
{
    fputc('"',out);
    for (unsigned i=0;i<bytes;i++) fprintf(out,"%02x",data[i]);
    fputc('"',out);
}
static bool overlaps(const Write *w, uint64_t field)
{ return w->address <= field && field-w->address < w->bytes; }
static void emit_write(const Write *w, uint64_t context, bool prior)
{
    if (records >= MAX_RECORDS) { dropped++;return; }
    fprintf(out,"{\"index\":%"PRIu64",\"kind\":\"%s\",\"cpu\":%u,"
        "\"store_sequence\":%"PRIu64",\"pc\":\"0x%"PRIx64"\","
        "\"host_us\":%"G_GINT64_FORMAT",\"context\":\"0x%"PRIx64"\",\"address\":\"0x%"PRIx64"\","
        "\"physical\":\"0x%"PRIx64"\",\"bytes\":%u,\"value\":",
        records++,prior?"lookback_store":"field_store",w->cpu,w->sequence,w->pc,
        w->host_us,context,w->address,w->physical,w->bytes);
    bytes_json(w->value,w->bytes);
    fprintf(out,",\"field_byte\":%u}\n",w->value[context+0x20-w->address]);
    if (prior) prior_matches++;else subsequent_matches++;
}
static void observed_store(unsigned cpu, qemu_plugin_meminfo_t info,
                           uint64_t address, void *opaque)
{
    unsigned shift=qemu_plugin_mem_size_shift(info);
    if (shift>4 || qemu_plugin_mem_is_big_endian(info)) return;
    unsigned bytes=1u<<shift;
    bool heap=address>=heap_low && address<heap_high;
    bool global=false;
    for(unsigned i=0;i<3;i++) if(address<=globals[i] && globals[i]-address<bytes) global=true;
    if(!heap && !global) return;
    struct qemu_plugin_hwaddr *hw=qemu_plugin_get_hwaddr(info,address);
    if (!hw || qemu_plugin_hwaddr_is_io(hw)) return;
    Write w={ .pc=(uintptr_t)opaque,.address=address,
        .physical=qemu_plugin_hwaddr_phys_addr(hw),.cpu=cpu,.bytes=bytes,
        .host_us=g_get_monotonic_time() };
    qemu_plugin_mem_value v=qemu_plugin_mem_get_value(info);
    uint64_t lo=0,hi=0;
    switch(v.type) {
    case QEMU_PLUGIN_MEM_VALUE_U8:lo=v.data.u8;break;
    case QEMU_PLUGIN_MEM_VALUE_U16:lo=v.data.u16;break;
    case QEMU_PLUGIN_MEM_VALUE_U32:lo=v.data.u32;break;
    case QEMU_PLUGIN_MEM_VALUE_U64:lo=v.data.u64;break;
    case QEMU_PLUGIN_MEM_VALUE_U128:lo=v.data.u128.low;hi=v.data.u128.high;break;
    default:return;
    }
    for(unsigned i=0;i<w.bytes;i++) w.value[i]=(i<8?lo>>(i*8):hi>>((i-8)*8))&255;
    g_mutex_lock(&lock);
    if(global) {
        global_stores++;
        if(records>=MAX_RECORDS) dropped++;
        else {
            fprintf(out,"{\"index\":%"PRIu64",\"kind\":\"global_store\",\"cpu\":%u,"
                "\"host_us\":%"G_GINT64_FORMAT",\"pc\":\"0x%"PRIx64"\","
                "\"address\":\"0x%"PRIx64"\",\"physical\":\"0x%"PRIx64"\",\"bytes\":%u,\"value\":",
                records++,cpu,w.host_us,w.pc,address,w.physical,bytes);
            bytes_json(w.value,bytes);fputs("}\n",out);fflush(out);
        }
    }
    if(heap) {
        w.sequence=heap_writes++;
        history[w.sequence%HISTORY]=w;
        for(unsigned i=0;i<context_count;i++) if(overlaps(&w,contexts[i]+0x20))
            emit_write(&w,contexts[i],false);
    }
    g_mutex_unlock(&lock);
}
static void reader(unsigned cpu, void *opaque)
{
    (void)opaque;
    if(cpu>=G_N_ELEMENTS(cpus)) return;
    CPU *c=&cpus[cpu];uint64_t context=0;
    g_byte_array_set_size(c->buffer,0);
    if(!c->reg || qemu_plugin_read_register(c->reg,c->buffer)!=8) return;
    memcpy(&context,c->buffer->data,8);context=GUINT64_FROM_LE(context);
    if(context<heap_low || context>heap_high-0xa60) return;
    g_mutex_lock(&lock);
    for(unsigned i=0;i<context_count;i++) if(contexts[i]==context) {
        g_mutex_unlock(&lock);return;
    }
    if(context_count==CONTEXTS || records>=MAX_RECORDS) {
        context_overflow++;g_mutex_unlock(&lock);return;
    }
    contexts[context_count++]=context;
    fprintf(out,"{\"index\":%"PRIu64",\"kind\":\"context_discovered\","
        "\"cpu\":%u,\"host_us\":%"G_GINT64_FORMAT",\"pc\":\"0x%"PRIx64"\",\"context\":\"0x%"PRIx64"\","
        "\"history_start\":%"PRIu64",\"history_end\":%"PRIu64",\"header\":",
        records++,cpu,g_get_monotonic_time(),reader_pc,context,heap_writes>HISTORY?heap_writes-HISTORY:0,heap_writes);
    g_byte_array_set_size(c->buffer,0);
    if(qemu_plugin_read_memory_vaddr(context,c->buffer,64)) bytes_json(c->buffer->data,64);
    else fputs("null",out);
    fputs(",\"parameter_pointer\":",out);
    g_byte_array_set_size(c->buffer,0);
    if(qemu_plugin_read_memory_vaddr(context+0xa58,c->buffer,8)) bytes_json(c->buffer->data,8);
    else fputs("null",out);
    fputs("}\n",out);
    uint64_t first=heap_writes>HISTORY?heap_writes-HISTORY:0;
    for(uint64_t i=first;i<heap_writes;i++) {
        Write *w=&history[i%HISTORY];
        if(overlaps(w,context+0x20)) emit_write(w,context,true);
    }
    first=helper_calls>CALL_HISTORY?helper_calls-CALL_HISTORY:0;
    for(uint64_t i=first;i<helper_calls;i++) {
        Call *call=&calls[i%CALL_HISTORY];uint64_t field=context+0x20;
        if(call->destination<=field && field-call->destination<call->bytes) emit_call(call,context,true);
    }
    fflush(out);g_mutex_unlock(&lock);
}
static void translated(qemu_plugin_id_t id, struct qemu_plugin_tb *tb)
{
    (void)id;
    for(size_t i=0;i<qemu_plugin_tb_n_insns(tb);i++) {
        struct qemu_plugin_insn *insn=qemu_plugin_tb_get_insn(tb,i);
        uint64_t pc=qemu_plugin_insn_vaddr(insn);
        if(pc>=0x40160000 && pc<0x45000000)
            qemu_plugin_register_vcpu_mem_cb(insn,observed_store,QEMU_PLUGIN_CB_NO_REGS,
                QEMU_PLUGIN_MEM_W,(void *)(uintptr_t)pc);
        if(pc==reader_pc) qemu_plugin_register_vcpu_insn_exec_cb(insn,reader,QEMU_PLUGIN_CB_R_REGS,NULL);
        for(unsigned j=0;j<2;j++) if(pc==helper_pc[j])
            qemu_plugin_register_vcpu_insn_exec_cb(insn,helper,QEMU_PLUGIN_CB_R_REGS,(void *)(uintptr_t)pc);
    }
}
static void initialized(qemu_plugin_id_t id, unsigned cpu)
{
    (void)id;
    if(cpu>=G_N_ELEMENTS(cpus)) return;
    cpus[cpu].buffer=g_byte_array_new();GArray *regs=qemu_plugin_get_registers();
    char wanted[12];g_snprintf(wanted,sizeof(wanted),"x%u",reader_register);
    for(unsigned i=0;i<regs->len;i++) {
        qemu_plugin_reg_descriptor *r=&g_array_index(regs,qemu_plugin_reg_descriptor,i);
        if(!strcmp(r->name,wanted)) cpus[cpu].reg=r->handle;
        const char *names[]={"x0","x1","x2","x30"};
        for(unsigned j=0;j<4;j++) if(!strcmp(r->name,names[j])) cpus[cpu].argument[j]=r->handle;
    }
    g_array_free(regs,TRUE);
}
static void finished(qemu_plugin_id_t id, void *opaque)
{
    (void)id;(void)opaque;
    fprintf(out,"{\"finished\":true,\"records\":%"PRIu64",\"dropped\":%"PRIu64
        ",\"contexts\":%u,\"context_overflow\":%"PRIu64",\"heap_writes\":%"PRIu64
        ",\"history_capacity\":%u,\"lookback_matches\":%"PRIu64
        ",\"subsequent_matches\":%"PRIu64",\"helper_calls\":%"PRIu64
        ",\"helper_matches\":%"PRIu64",\"helper_history_capacity\":%u,\"global_stores\":%"PRIu64"}\n",
        records,dropped,context_count,context_overflow,heap_writes,HISTORY,prior_matches,
        subsequent_matches,helper_calls,helper_matches,CALL_HISTORY,global_stores);
    fclose(out);
}
QEMU_PLUGIN_EXPORT int qemu_plugin_install(qemu_plugin_id_t id,const qemu_info_t *info,
                                         int argc,char **argv)
{
    if(strcmp(info->target_name,"aarch64") || !info->system_emulation || argc!=2 ||
        !g_str_has_prefix(argv[0],"bindings=") || !g_str_has_prefix(argv[1],"out=")) return -1;
    FILE *input=fopen(argv[0]+9,"r");if(!input) return -1;
    int matched=fscanf(input,"%"SCNx64" %u %"SCNx64" %"SCNx64" %"SCNx64" %"SCNx64
        " %"SCNx64" %"SCNx64" %"SCNx64,
        &reader_pc,&reader_register,&heap_low,&heap_high,&helper_pc[0],&helper_pc[1],
        &globals[0],&globals[1],&globals[2]);
    int trailing=fgetc(input);while(trailing==' ' || trailing=='\n' || trailing=='\r') trailing=fgetc(input);
    fclose(input);
    if(matched!=9 || trailing!=EOF || reader_register>=31 || reader_pc<0x40160000 ||
        reader_pc>=0x45000000 || (reader_pc&3) || heap_low<UINT64_C(0xa00000000) ||
        heap_high>UINT64_C(0xa40000000) || heap_low>=heap_high || heap_high-heap_low>0x2000000) return -1;
    for(unsigned j=0;j<2;j++) if(helper_pc[j]<0x40160000 || helper_pc[j]>=0x45000000 ||
        (helper_pc[j]&3) || helper_pc[j]==reader_pc) return -1;
    for(unsigned j=0;j<3;j++) if(globals[j]<UINT64_C(0xa00000000) ||
        globals[j]>=UINT64_C(0xa40000000) || (globals[j]>=heap_low && globals[j]<heap_high)) return -1;
    out=fopen(argv[1]+4,"wx");if(!out) return -1;
    qemu_plugin_register_vcpu_init_cb(id,initialized);
    qemu_plugin_register_vcpu_tb_trans_cb(id,translated);
    qemu_plugin_register_atexit_cb(id,finished,NULL);
    return 0;
}
