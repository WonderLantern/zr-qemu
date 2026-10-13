# SPDX-License-Identifier: GPL-2.0-or-later
"""ZR C1.11 instruction bindings; wire semantics remain explicit lab inputs.

32-word unique normalized windows: evidence/zr-code-match-001.json. Native
RX execution is checked by probe_zr_mcu.py. Shared serial object base is
independently encoded at ZR 40e1466c and RX ISR 40e15478.
"""
BINDINGS = dict(
    gpio_tx_isr=0x40e16740, gpio_rx_isr=0x40e16758,
    rx_request=0x40e9aa50, rx_accepted=0x40e9ab64,
    # ab88/ab94 clear the previous RX flags; ab9c/aba0 write its ACK.
    # Announcing a following frame at ab64 can lose that notification.
    rx_after_flag_clear=0x40e9aba4,
    serial_before_enable=0x40e14fc8, serial_prefill=0x40e14ff4,
    serial_drain=0x40e15038, serial_rx_isr=0x40e15478,
    tx_request=0x40e9a688, tx_return=0x40e9a68c,
    tx_ack_read=0x40e9a774, tx_finished=0x40e9a7dc,
    power_event_consumer=0x40f7cb30,
    mode_reply_consumer=0x41378de0, lens_status_consumer=0x4137d340,
    config_reply_consumer=0x41378d9c, serial_objects=0xa02808780,
    tx_state=0xa0304f718, config_callback=0xa057b7658,
)
