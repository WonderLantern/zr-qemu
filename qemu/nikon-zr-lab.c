/* SPDX-License-Identifier: GPL-2.0-or-later */
/* ZR C1.11: share the EXPEED7 candidate hardware without duplicating it.
 * The 0x40160000 entry and first 0x1600 bytes match the pinned Z9 boot code.
 * Device reuse beyond that is experimental and checked by native ZR runs.
 * No Z9 task address, firmware patch or application state is installed here.
 */
#include "qemu/osdep.h"
#include "hw/boards.h"
#include "qemu/module.h"

static void nikon_zr_class_init(ObjectClass *oc, const void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);
    mc->desc = "Nikon ZR C1.11 experimental EXPEED7 bring-up";
    mc->default_ram_id = "zr.work-ram";
}

static const TypeInfo nikon_zr_type = {
    .name = MACHINE_TYPE_NAME("nikon-zr-lab"),
    .parent = MACHINE_TYPE_NAME("nikon-z9-lab"),
    .class_init = nikon_zr_class_init,
};

static void nikon_zr_register_types(void)
{
    type_register_static(&nikon_zr_type);
}
type_init(nikon_zr_register_types)
