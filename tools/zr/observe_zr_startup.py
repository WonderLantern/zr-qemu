# SPDX-License-Identifier: GPL-2.0-or-later
"""One-shot original ZR startup candidates; no borrowed Z9 global addresses."""
from pathlib import Path
import hashlib
import re
import struct
from probe import sha
from probe_graphics_image import save as _save

SOURCE_BYTES=Path(__file__).read_bytes()
SOURCE_SHA=hashlib.sha256(SOURCE_BYTES).hexdigest()
EXCEPTION_CONTEXT_BYTES=0x110


def capture_exception_context(g,row,regs,cpu):
    """Read only fields consumed by the pinned original exception printer.

    X0..30, saved SP, and the fields at100/108/10c fit110 bytes. Reading180
    crossed the actual stack guard in464/465 and masked the fault observation.
    Translation failure remains a failure; no physical/MMU bypass is used.
    """
    import json
    address=regs['X19']
    row.update(context_address=hex(address),context_bytes=EXCEPTION_CONTEXT_BYTES)
    try:
        if not 0xa02800000<=address<=0xa08000000-EXCEPTION_CONTEXT_BYTES:
            raise ValueError('original exception context outside bounded work RAM')
        raw=save(g,'zr-original-exception-context',address,EXCEPTION_CONTEXT_BYTES,virtual_cpu=cpu)
        row.update(context_hex=raw.hex(),
            virtual_ns=json.loads(g.qmp.command('qom-get',path='/machine',
                property='runtime-clock-state'))['virtual_ns'],
            original_registers={f'X{i:02d}':hex(struct.unpack_from('<Q',raw,8*i)[0]) for i in range(31)},
            context_tail_words=[hex(x[0]) for x in struct.iter_unpack('<Q',raw[0xf8:])])
    except Exception as error:
        row['context_capture_error']=repr(error)
        g.data.setdefault('fault_capture_failures',[]).append(dict(row))
        try:row['stopped_cpu_registers_text']=g.qmp.hmp('info registers',cpu)
        except Exception as dump_error:row['register_dump_error']=repr(dump_error)
        raise


def save(g,label,address,size,*,virtual_cpu=None):
    """Preserve repeated observations instead of overwriting earlier bytes."""
    # Each guest owns its run directory. Remember the next suffix so repeated
    # captures do not rescan every earlier file across the Windows/WSL mount.
    # Still check for externally created files and preserve them on collision.
    counters=getattr(g,'_zr_capture_suffixes',None)
    if counters is None:
        counters={};g._zr_capture_suffixes=counters
    number=counters.get(label,1)
    unique=label if number==1 else f'{label}-observation-{number:03d}'
    while (g.out/(unique+'.bin')).exists():
        number+=1;unique=f'{label}-observation-{number:03d}'
    if virtual_cpu is None:
        raw=_save(g,unique,address,size)
        counters[label]=number+1
        return raw
    from capture_virtual_ram import read_virtual_ram
    raw=read_virtual_ram(g,address,size,cpu=virtual_cpu)
    path=g.out/(unique+'.bin');path.write_bytes(raw)
    g.data.setdefault('captures',[]).append(dict(label=unique,address=hex(address),
        bytes=size,file=path.name,sha256=sha(path),address_space='virtual',cpu=virtual_cpu))
    counters[label]=number+1
    return raw

POINTS = {0x40f7b608:'lens_battery_command',0x40f7b860:'lens_close_system_callback',
    0x40e07bc4:'device_snapshot_enter',0x40e07d44:'device_snapshot_dispatch',
    0x40e08138:'device_snapshot_export',0x40e08078:'device_snapshot_file',
    0x41202c18:'device_snapshot_status_trigger',
    0x40e033f0:'fault_cpu_exception_context',
    0x40f6a900:'app_boot_notice',0x40f448b4:'key_boot_callback',
    0x41199aec:'capture_ready_event',0x403a20bc:'key_consumer_candidate_a',
    0x40f398f8:'key_consumer_candidate_b',0x402e4374:'dsi_command_argument',
    0x402e1764:'display_parameter_source',0x402d9cd4:'display_parameter_converted',
    0x402e4218:'dsi_orientation_argument',0x402e4108:'dsi_display_on_argument',
    0x402e4134:'dsi_display_on_native_callback',0x402e4138:'dsi_display_on_callback_returned',
    0x4114cb18:'sequence_wait_argument',0x4114cb1c:'sequence_wait_return',
    0x4114cb30:'sequence_wait_failure',0x4114cb74:'sequence_failure_event',
    0x402b9528:'display_isr',0x40ecc150:'panel_on_flag_notify',
    0x403439f0:'ui_display_message',0x40344400:'ui_display_wait',
    0x40344404:'ui_display_wait_return',0x4022b214:'inline_path_producer',
    0x40ed0f7c:'battery_manager_callback',0x40f739d8:'app_state_entry_candidate',
    0x40f6f5a8:'app_original_dispatch',0x40f6a5d0:'app_state_transition',
    0x40f6a7f8:'app_ui_message',0x40f65148:'capture_boot_query_return',
    0x40f697d0:'boot_ui_ready_message',0x40f69764:'boot_capture_ready_message',
    0x40f722c8:'app_entry_ready_comparison',0x4039dcac:'ui_state_notification',
    0x40406034:'ui_popup_request',0x4038f85c:'ui_component_request',
    0x4047b9f4:'ui_view_selector_write',0x4047b938:'ui_view_message',
    0x4047b8f4:'ui_view_activate',0x40458a60:'ui_selected_view_message',
    0x40335e04:'ui_popup_child_call',0x40412530:'ui_initial_request_selector',
    0x404c5968:'ui_fault_list_query_return',0x404c59d0:'ui_update_fault_list_query_return',
    0x404393bc:'ui_collection_select',
    0x4041973c:'ui_alert_property2937_return',
    0x4041f84c:'ui_alert_flag76_store_entry',
    0x4041f868:'ui_alert_flag76_store_return',
    0x404c63c0:'ui_alert_flag76_predicate_return',
    0x40f80ef0:'ui_alert_resource_status_return',
    0x4121a47c:'ui_alert_resource_status_publish',
    0x40f856f0:'ui_alert_resource_check_13_return',
    0x40f85700:'ui_alert_resource_check_09_return',
    0x40f85718:'ui_alert_resource_check_56_return',
    0x40f8572c:'ui_alert_resource_check_64_return',
    0x40f85738:'ui_alert_resource_check_62_return',
    0x40f85748:'ui_alert_resource_check_5a_return',
    0x40f85754:'ui_alert_resource_check_50_return',
    0x410c2efc:'fault_list_append',0x4113cdb8:'fault_handler_entry',
    0x41137634:'fault_event_translate',0x41139678:'fault_notification_producer',
    0x41136e9c:'fault_status_translate',0x411482b8:'fault_bit10_report',
    0x411482a4:'fault_reason9_report',
    0x4135e9f8:'sensor_mode_select',
    0x4135ea7c:'sensor_mode_branch_return',
    0x4135e018:'sensor_mode_wait2000_argument_600',
    0x4135e01c:'sensor_mode_wait2000_return_600',
    0x4135e21c:'sensor_mode_wait2000_argument_100',
    0x4135e220:'sensor_mode_wait2000_return_100',
    0x4135d67c:'sensor_mode_wait2000_argument_105',
    0x4135d680:'sensor_mode_wait2000_return_105',
    0x40e2a1c0:'sensor_mode_aux_isr',
    0x413533d4:'sensor_mode_aux_callback',
    0x41353480:'sensor_mode_notify2000',
    0x40e228a8:'readback150d_getter1_entry',
    0x412ad170:'readback150d_getter1_consumer',
    0x40e2cf7c:'output_group1508_bank1_entry',
    0x41365314:'output_group1508_bank1_return',
    0x40e2bfa8:'command1508_entry',
    0x4136458c:'command1508_return',
    0x40e2b31c:'aux_config1508_control_entry',
    0x41366670:'aux_config1508_control_return',
    0x41353450:'sensor_restart_notify1000',
    0x40e2a260:'sensor_restart_aux1_isr',0x41353f48:'sensor_restart_aux1_callback',
    0x41353fc4:'sensor_restart_notify4000',0x4135321c:'sensor_restart_notify400000',
    0x41353454:'sensor_restart_notify1000_return',
    0x41356228:'sensor_restart_wait_argument',
    0x4135622c:'sensor_restart_wait_return',
    0x41361b90:'sensor_restart_status_cleanup',0x41361c4c:'sensor_restart_status_cleanup_return',
    0x4135ead8:'sensor_restart_followup_entry',
    0x4135eb08:'sensor_restart_followup_query_return',
    0x4135eb84:'sensor_restart_followup_wait80_argument',
    0x4135eb88:'sensor_restart_followup_wait80_return',
    0x4135c9a4:'sensor_restart_followup_wait40_argument',
    0x4135c9a8:'sensor_restart_followup_wait40_return',
    0x4135ec24:'sensor_restart_followup40_return',
    0x41141be8:'sensor_restart_followup_caller_return',
    0x41353170:'sensor_restart_notify40',0x413531a0:'sensor_restart_notify80',
    0x40e302c4:'stream154c_stop_entry',0x40e30320:'stream154c_stop_return',
    0x40eb924c:'stream154c_original_caller_resume',
    0x40e303a4:'stream154c_idle_getter',0x40e30408:'stream154c_idle_getter_return',
    0x41144dc0:'sequence_flow_watchdog_start',
    0x411418d8:'sequence_flow_watchdog_start_initial',
    0x41141e7c:'sequence_flow_watchdog_restart',
    0x41141b84:'sequence_transition_wait_argument',
    0x41141b88:'sequence_transition_wait_return',
    0x41141bcc:'sequence_transition_result_gate',
    0x41141bfc:'sequence_flow_watchdog_stop_a',
    0x41141e30:'sequence_flow_watchdog_stop_b',
    0x4114234c:'sequence_flow_watchdog_stop_c',
    0x40e2b9e0:'global_event_native_isr',
    0x41352f40:'global_event_native_callback',
    0x41352ffc:'global_event_sequence_notification',
    0x41353098:'global_event_bit4_sequence_notification',
    0x40e2b95c:'channel_event_native_isr',
    0x41352c7c:'channel_event_native_callback',
    0x41352e3c:'channel_event_special_notification',
    0x41352e58:'channel_event_sequence_notification',
    0x411456d0:'sequence_flow_watchdog_expired',
    0x41145140:'sequence_flow_wait1000000_argument',
    0x41145144:'sequence_flow_wait1000000_return',
    0x411451d0:'sequence_flow_wait100000_argument',
    0x411451d4:'sequence_flow_wait100000_return',
    0x41145244:'sequence_flow_wait2_argument',
    0x41145248:'sequence_flow_wait2_return',
    0x411452ec:'sequence_flow_wait200000_argument',
    0x411452f0:'sequence_flow_wait200000_return',
    0x41145364:'sequence_flow_wait1000_argument',
    0x41145368:'sequence_flow_wait1000_return',
    0x41145430:'sequence_flow_wait2000_argument',
    0x41145434:'sequence_flow_wait2000_return',
    0x41355b9c:'fault_init_results',0x4136dafc:'fault_parameter_source',
    0x4136db28:'fault_parameter_version',0x40f6d4d0:'ui_ready_producer_gate',
    0x40f6d4e4:'ui_ready_message_producer',0x40458b64:'ui_empty_fault_view_return',
    0x40f6c870:'ui_ready_status_consumer',0x411c3c20:'ready_bitmap_bind',
    0x411c3c38:'ready_bitmap_enable',0x411c4520:'ready_bitmap_clear',
    0x411c463c:'ready_bitmap_set',0x411c4638:'ready_bitmap_clear_notification',
    0x411c4754:'ready_bitmap_set_notification',
    0x410b9b1c:'capture_status_cache_query',0x410b9b98:'capture_status_dependency_return',
    0x410b9bf0:'capture_status_query_return',0x4119b9c8:'capture_status_store',
    0x4119bd08:'capture_status_message_producer',0x4119a42c:'capture_status_listener_query',
    0x40e8f9f0:'orientation_init_parameters',0x40e8fe14:'orientation_init_missing_parameters',
    0x40e92de4:'orientation_bus_write',0x40e8ffa4:'orientation_init_status_return',
    0x40e90594:'orientation_init_failure',0x40e907ec:'orientation_status_bind',
    0x411b11cc:'orientation_capture_completion',0x40e9119c:'orientation_sample_bytes',
    0x40e912a8:'orientation_sample_decoded',0x40e9315c:'orientation_init_completed',
    0x4024b648:'graphics_secondary_geometry',
    0x40f74170:'app_capture_transition_result',
    0x41378e08:'mcu_mode_callback_dispatch',
    0x4119aaa4:'capture_late_property_result',
    0x4119ab30:'capture_late_worker_result',
    0x4119aa58:'capture_late_event_wait_argument',
    0x4119aa5c:'capture_late_event_wait_return',
    0x411a9d90:'capture_controller_enter',
    0x411a9dd8:'capture_controller_decision',
    0x411aa9ec:'capture_controller_exit',
    0x411ab008:'capture_completion_enter',
    0x411ab078:'capture_completion_payload',
    0x41198a20:'capture_begin_completion_schedule',
    0x411a8f0c:'capture_begin_completion_consumer',
    0x411a892c:'capture_begin_timeout',
    0x4115e2b8:'capture_begin_sequence_worker',
    0x4115e3c0:'capture_begin_sequence_restart',
    0x411679a0:'capture_begin_failure_producer',
    0x411811cc:'front_prepare_object_return',
    0x41181320:'front_prepare_capture_return',
    0x41220d48:'front_resource_registration',
    0x41222fb0:'front_resource_callback',
    0x41222fc8:'front_resource_notification',
    0x412249e8:'front_submit_enter',
    0x41224a68:'front_event_wait8_return',
    0x41224a9c:'front_event_wait10_return',
    0x41181734:'front_submit_return',
    0x411817b8:'front_pipeline_result',
    0x4118180c:'front_followup_request',
    0x41050240:'front_followup_queue',
    0x411764f8:'front_followup_callback',
    0x41176c60:'front_followup_completion',
    0x41176c84:'front_followup_completion_gate',
    0x4115ccbc:'front_followup_bit1_schedule',
    0x4115cd28:'front_followup_bit1_submit',
    0x411771a4:'front_followup_bit1_callback',
    0x411771c8:'front_followup_bit1_gate',
    0x4117cdb4:'front_followup_bit1_clear_store',
    0x4117cdb8:'front_followup_bit1_clear_after',
    0x411886a0:'front_followup_complete_dispatch',
    0x41089a5c:'front_followup_event_producer_a',
    0x41089b9c:'front_followup_event_producer_b',
    0x4108a80c:'front_followup_event_producer_c',
    0x4108e8e4:'front_followup_event_producer_d',
    0x4115bacc:'front_followup_other_route_a',
    0x4115d35c:'front_followup_other_route_b',
    0x402f7418:'ui_render_wait_argument',
    0x402f741c:'ui_render_wait_return',
    0x402f05d0:'ui_render_worker_completed',
    0x402f072c:'ui_render_worker_callback',
    0x402f2b08:'ui_render_completion_notify',
    0x41141718:'sequence_sync8_argument_a',
    0x4114171c:'sequence_sync8_return_a',
    0x41141d10:'sequence_sync8_argument_b',
    0x41141d14:'sequence_sync8_return_b',
    0x41231344:'front_channel_sequence_enter',
    0x41231564:'front_channel_start_return_a',
    0x41231628:'front_channel_start_return_b',
    0x41231598:'front_channel_wait4_argument_a',
    0x4123159c:'front_channel_wait4_return_a',
    0x4123165c:'front_channel_wait4_argument_b',
    0x41231660:'front_channel_wait4_return_b',
    0x41231668:'front_channel_sequence_notice',
    0x4122c53c:'front_channel_completion_callback',
    0x412ab21c:'front_channel_driver_enter',
    0x412ab3fc:'front_channel_bus_start_argument',
    0x412ab32c:'front_channel_bus_restart_return',
    0x41148328:'sequence_sync8_producer',
    0x40e1fe3c:'primary_native_isr',
    0x40eb7e68:'primary_native_driver_callback',
    0x412a9cc8:'primary_native_dispatch',
    0x412aa470:'primary_bit6_subscriber_dispatch',
    0x412aa600:'primary_native_bit2_mode_gate',
    0x412aa638:'primary_native_bit2_subscriber',
    0x412aa644:'primary_native_bit2_subscriber_return',
    0x412aa800:'primary_native_bit2_single_subscriber',
    0x412aa80c:'primary_native_bit2_single_subscriber_return',
    0x412aab64:'primary_source_boundary_wait',
    0x412aab68:'primary_source_boundary_wait_return',
    0x412aa7b4:'primary_source_boundary_notify',
    0x412aebd4:'front_channel_bus_completion_callback',
    0x40eb9ce4:'front_channel_worker_wait_argument',
    0x40eb9ce8:'front_channel_worker_wait_return',
    0x40eb9c80:'front_channel_prestart_wait_argument',
    0x40eb9c84:'front_channel_prestart_return_a',
    0x40e1ff78:'primary_bank1_native_isr',
    0x40eb83cc:'primary_bank1_native_driver_callback',
    0x411c6e8c:'shutter_gpio_native_callback',
    0x411cf5f8:'shutter_gpio_native_half_worker',
    0x411caa74:'shutter_gpio_native_full_worker'}


def capture_ready_bitmap(g,label):
    """ZR-native globals described by 411c3b24; never follow guessed pointers."""
    raw=save(g,label,0xa03e461a0,0xa0)
    return dict(address='0xa03e461a0',raw_hex=raw.hex(),
        descriptors={hex(off):dict(bits=struct.unpack_from('<I',raw,off)[0],
            pointer=hex(struct.unpack_from('<Q',raw,off+8)[0]))
            for off in (0x18,0x30,0x48,0x60,0x78)},
        backing_words={hex(off):struct.unpack_from('<I',raw,off)[0]
            for off in (0xc,0x10,0x28,0x2c,0x40,0x44,0x58,0x70)},
        callback=hex(struct.unpack_from('<Q',raw,0x88)[0]),
        notify_mask=struct.unpack_from('<I',raw,0x90)[0],
        empty_flags=dict(group5=raw[0x94],group8=raw[0x98]))


def capture_ready_state(g,label):
    """Bounded original globals; names are working labels, not model enums."""
    locations=dict(property_cache=(0xa03e14a00,8),capture_status=(0xa03e3dd5c,12),
        capture_callback=(0xa03e3d560,8),capture_listener7=(0xa03e3e100,8),
        app_boot_mask=(0xa0282f4b8+0x6cc,4),orientation_status=(0xa03022250,0x18),
        orientation_context=(0xa03022300+0x1b0,0x18))
    return {name:dict(address=hex(address),raw_hex=save(g,label+'-'+name,address,size).hex())
        for name,(address,size) in locations.items()}


class Observer:
    def __init__(self,g,*,early=False,phase=None):
        self.g=g
        self.dsi_calls=0
        self.dispatches=0
        self.ui_notifications=0
        self.bitmap_calls={}
        self.bitmap_returns={}
        self.controller_calls=0
        self.transitions=0
        self.render_waits=0
        self.ui_fault_queries={}
        self.ui_collection_calls=0
        self.ui_popup_calls=0
        self.sequence_resource_calls=0
        self.sequence_resource_returns={}
        self.watchdog_calls=0
        self.watchdog_returns={}
        self.wait_calls=0
        self.wait_pending={}
        self.wait_pairs={p:p+4 for p in (0x4135e018,0x4135d67c,0x4135eb84,0x41356228,
            0x4135c9a4,0x41141718,0x41141d10,0x4114cb18,0x41145140,0x411451d0,
            0x41145244,0x411452ec,0x41145364,0x41145430,0x41141b84)}
        self.source_control_calls=0
        self.source_step11_calls=0
        self.sequence_callback_calls=0
        self.sequence_callback_pending=None
        self.mode_key_calls=0
        self.mode_diff_calls=0
        self.mode_selected_calls=0
        self.mode_ui_calls=0
        self.mode_view_calls=0
        self.mode_menu_calls=0
        self.mode_view_limit=g.data.get('mode_view_call_limit',8)
        from zr_key_sequence import MAX_KEYS
        if not 1<=self.mode_view_limit<=2*MAX_KEYS+8:raise ValueError('bounded view observation limit required')
        self.mode_view_callback=None
        self.capture_phase=phase or ('early' if early else 'post')
        self.points=({p:n for p,n in POINTS.items() if n.startswith(
            ('display_parameter_','fault_','ui_ready_','ui_alert_','ready_bitmap_','capture_status_','orientation_',
             'front_resource_','front_channel_','primary_native_','primary_bank1_',
             'sequence_sync8_producer','sensor_mode_','sensor_restart_','stream154c_','sequence_flow_','global_event_','channel_event_','readback150d_','output_group1508_','command1508_','aux_config1508_','ui_render_'))}
                     if early else dict(POINTS))
        if g.data.get('ui_language_preference'):
            from zr_ui_language_input import POINTS as language_points
            self.points.update(language_points)
        if g.data.get('rtc_status_input'):
            self.points.update({0x40ed5764:'rtc_abstract_consumer',0x40ed51b4:'rtc_native_status',
                0x411b1278:'rtc_capture_state_update',0x411b12c4:'rtc_capture_inhibit_clear'})
        if not early and phase is None and g.data.get('mode_key_sequence')=='keys':
            self.points[0x405284ec]='ui_menu_key_handler'
            if g.data.get('mode_start_gate')=='initial-consumer-lcd':
                self.points[0x40f398f8]='ui_mode_key_consumer'
        if g.data.get('trace_sequence_resources'):
            self.points.update({
                0x41146fd4:'sequence_resource_event',
                0x41147034:'sequence_resource_notify_5a',
                0x411470a4:'sequence_resource_notify_64',
                0x411470d4:'sequence_resource_notify_0c',
                0x411470fc:'sequence_resource_notify_62',
                0x41145874:'sequence_resource_register_64',
                0x41145884:'sequence_resource_register_5a',
                0x41145894:'sequence_resource_register_0c',
                0x411458a4:'sequence_resource_register_62',
                0x411458b4:'sequence_resource_register_0c_type5',
                0x41145878:'sequence_resource_registered_64',
                0x41145888:'sequence_resource_registered_5a',
                0x41145898:'sequence_resource_registered_0c',
                0x411458a8:'sequence_resource_registered_62',
                0x411458b8:'sequence_resource_registered_0c_type5'})
        if g.data.get('trace_sequence_waits'):
            self.points[0x40e2bf00]='source_control_argument'
            self.points[0x40e2bf40]='source_control_return'
            self.points[0x41141b84]=POINTS[0x41141b84]
            self.points[0x41141b88]=POINTS[0x41141b88]
            self.points[0x4135fe54]='source_stop_step11_after_control'
            self.points[0x4135fe74]='source_stop_step11_return'
        self.still_input_calls={}
        self.still_input_returns={}
        self.still_channel_points={0x40e2b95c:'still_frame_channel_isr',
                                   0x41352c7c:'still_frame_channel_callback'}
        if g.data.get('probe_arguments',{}).get('single_frame_input'):
            # Independently disassembled originals after instruction-shape matching.
            self.points.update({0x40e2c364:'still_input_mode',0x40e2c47c:'still_input_mode3',
                                0x40eb8ea4:'still_input_primary_start'})
        if g.data.get('probe_arguments',{}).get('engine153_frame_pass'):
            self.points.update({0x40e281ac:'frame_pass_isr',0x40ec54b0:'frame_pass_callback'})
        if g.data.get('probe_arguments',{}).get('engine151_capture_pixels'):
            # Original1510 branch, after the shared ISR's native W1C. Unlike
            # entry, this address excludes the earlier1514 preview interrupt.
            self.points.update({0x40e0db90:'capture151_isr_after_w1c',
                                0x40e0d800:'capture151_codec_start'})
            if g.data.get('probe_arguments',{}).get('engine151_average_result'):
                self.points.update({0x40e0e8f8:'capture151_average_reader',
                                    0x40eabfb0:'capture151_average_return'})
        if g.data.get('trace_sequence_callbacks'):
            self.points[0x41140de0]='sequence_callback_argument'
        if g.data.get('probe_arguments',{}).get('engine15e2_jpeg'):
            self.points[0x40e0caf8]='capture15e2_isr'
            self.points[0x40ea2694]='capture15e2_prepare_call'
        if not early and 'generic_worker_objects' in g.data:
            worker=g.data['generic_worker_objects']['ui']
            for field in ('0x60','0x68','0x78'):
                callback=int(worker['callbacks'][field],0)
                if not 0x40160000<=callback<0x41490000 or callback&3:
                    raise ValueError('UI worker callback outside original executable prefix')
                if callback not in self.points:self.points[callback]='ui_worker_'+field
        self.record=dict(source_sha256=SOURCE_SHA,
            classification=('original_startup_with_declared_language_cache_input' if g.data.get('ui_language_preference')
                            else 'read_only_original_startup_candidates'),
            caveat='8/12-word windows include weak and ambiguous static candidates; execution recorded separately',
            stops=[],remaining={hex(k):v for k,v in self.points.items()})
        self.record['mode_view_call_limit']=self.mode_view_limit
        g.data[phase+'_startup_observer' if phase else
               ('early_display_observer' if early else 'startup_observer')]=self.record
        (g.out/Path(__file__).name).write_bytes(SOURCE_BYTES)
        for pc in self.points:g.rsp(f'Z1,{pc:x},4')

    def handle(self):
        import json
        hits=[]
        for cpu in range(4):
            raw=self.g.qmp.hmp('info registers',cpu)
            regs={k:int(v,16) for k,v in re.findall(r'\b(X\d\d|PC|SP)=([0-9a-fA-F]+)',raw)}
            pc=regs['PC']
            if pc not in self.points:continue
            row=dict(cpu=cpu,name=self.points[pc],pc=hex(pc),registers=regs)
            if row['name']=='fault_cpu_exception_context':
                try:capture_exception_context(self.g,row,regs,cpu)
                except Exception:
                    self.record['stops'].append(row)
                    raise
            if row['name'].startswith('device_snapshot_'):
                import json
                row.update(caller=hex(regs['X30']),
                    virtual_ns=json.loads(self.g.qmp.command('qom-get',path='/machine',
                        property='runtime-clock-state'))['virtual_ns'],
                    caller_stack_hex=save(self.g,row['name']+'-stack',regs['SP'],0x200,virtual_cpu=cpu).hex(),
                    table_header_hex=save(self.g,row['name']+'-table',0xa02cf8408,0x80,virtual_cpu=cpu).hex())
            if row['name'].startswith('capture15e2_'):
                from capture_engine15e2 import observe
                row['engine15e2_observation']=observe(self.g,
                    driver_address=regs['X00'] if row['name']=='capture15e2_isr' else None)
                item=row['engine15e2_observation']
                if row['name']=='capture15e2_isr' and item['jpeg']['jobs']:
                    if self.g.data.get('probe_arguments',{}).get('capture_pipeline'):
                        from capture_jpeg_completed import dump_completed
                        row['completed_jpeg']=dump_completed(self.g,item,regs)
                    callback=int(item['callback'],0)
                    if not 0x40160000<=callback<0x41490000 or callback&3:
                        raise ValueError('native15e2 callback outside original executable prefix')
                    if callback not in self.points:
                        self.points[callback]='capture15e2_callback'
                        self.g.rsp(f'Z1,{callback:x},4')
                if row['name']=='capture15e2_callback':
                    if (self.g.data.get('probe_arguments',{}).get('capture_pipeline')
                            and len(self.g.data.get('jpeg_completed_native_dumps',[]))<(
                                512 if self.g.data.get('probe_arguments',{}).get('mode_burst_min_frames',0) else 24)
                            and 0x40e0caf8 not in self.points):
                        self.points[0x40e0caf8]='capture15e2_isr'
                        self.g.rsp('Z1,40e0caf8,4')
                    if 0x40ea2694 not in self.points:
                        self.points[0x40ea2694]='capture15e2_prepare_call'
                        self.g.rsp('Z1,40ea2694,4')
                if row['name']=='capture15e2_prepare_call':
                    parameter=regs['X00'];method=regs['X08']
                    if not 0xa00000000<=parameter<=0xa40000000-0x50:
                        raise ValueError('original15e2 prepare argument outside bounded RAM')
                    if not 0x40160000<=method<0x41490000 or method&3:
                        raise ValueError('original15e2 prepare method outside executable prefix')
                    row['prepare_parameter_address']=hex(parameter)
                    row['prepare_parameter_hex']=self.g.read_bytes(parameter,0x50).hex()
                    row['actual_prepare_method']=hex(method)
                    if method not in self.points:
                        self.points[method]='capture15e2_prepare_method'
                        self.g.rsp(f'Z1,{method:x},4')
            if row['name'].startswith('capture151_'):
                from capture_engine151_pixels import observe
                row['engine151_pixels_observation']=observe(self.g)
                if row['name']=='capture151_isr_after_w1c':
                    if self.g.data.get('probe_arguments',{}).get('capture_raw_pipeline'):
                        side=json.loads(self.g.qmp.command('qom-get',path='/machine',property='engine151-raw-output-state'))
                        row['engine151_pixels_observation']['raw_side']=side
                        from capture_repeat_flow import snapshot_raw_producer
                        snapshot_raw_producer(self.g,side,len(self.g.data.get('capture_cycles',[])))
                    callback=regs['X02']
                    if not 0x40160000<=callback<0x41490000 or callback&3:
                        raise ValueError('native1510 callback outside original executable prefix')
                    row['actual_callback']=hex(callback)
                    if callback not in self.points:
                        self.points[callback]='capture151_callback'
                        self.g.rsp(f'Z1,{callback:x},4')
                if (row['name']=='capture151_callback'
                        and self.g.data.get('probe_arguments',{}).get('capture_raw_pipeline')
                        and len(self.g.data.get('raw_side_native_dumps',[]))<64
                        and 0x40e0db90 not in self.points):
                    # Keep the original after-W1C stop for each producer in a
                    # held burst; rearming only at the next button misses all
                    # subsequent frames in the same hold. No guest writes.
                    self.points[0x40e0db90]='capture151_isr_after_w1c'
                    self.g.rsp('Z1,40e0db90,4')
            if row['name'].startswith('frame_pass_'):
                from capture_engine153 import observe
                row['engine153_observation']=observe(self.g,model='zr')
            if row['name'].startswith('still_input_'):
                import json
                getter=lambda name:json.loads(self.g.qmp.command('qom-get',path='/machine',property=name))
                primary=getter('engine150c-state')
                row.update(virtual_ns=getter('runtime-clock-state')['virtual_ns'],
                    primary={k:primary[k] for k in ('active','latched','configured','stop_requested','stop_done')},
                    single=getter('primary-d980-single-frame-state'),
                    front_modes=getter('event1508-front-state')['modes'],
                    source_controls={hex(off):self.g.rd(0x15080000+off) for off in (0x10,0x28)},
                    primary_irq={hex(off):self.g.rd(0x150c0000+off) for off in (0x200,0x20c,0x218)})
                if pc in self.still_input_returns:
                    original,label=self.still_input_returns.pop(pc)
                    if (label=='still_input_primary_start' and primary['active']&0x4000 and
                            self.g.data.get('probe_arguments',{}).get('single_channel_boundary')):
                        for point,name in self.still_channel_points.items():
                            if point not in self.points:
                                self.points[point]=name;self.g.rsp(f'Z1,{point:x},4')
                    if self.still_input_calls[original]<32 and original not in self.points:
                        self.points[original]=label;self.g.rsp(f'Z1,{original:x},4')
                else:
                    self.still_input_calls[pc]=self.still_input_calls.get(pc,0)+1
                    returned=regs['X30'];row['original_return']=hex(returned)
                    if 0x40160000<=returned<0x41490000 and not returned&3 and returned not in self.points:
                        self.still_input_returns[returned]=(pc,row['name'])
                        self.points[returned]='still_input_return';self.g.rsp(f'Z1,{returned:x},4')
                    else:row['return_observation_unavailable']=True
            if row['name'].startswith('still_frame_channel_'):
                import json
                getter=lambda name:json.loads(self.g.qmp.command('qom-get',path='/machine',property=name))
                row.update(virtual_ns=getter('runtime-clock-state')['virtual_ns'],
                    full_dma=getter('primary-d980-state'),
                    channel_state=getter('event1508-channel-state'),
                    channel_boundary=getter('primary-d980-channel-boundary-state'),
                    driver_hex=save(self.g,'zr-still-frame-channel-driver',0xa0280d968,0xa8).hex())
            if row['name']=='rtc_native_status':
                row['rtc_status_hex']=save(self.g,'zr-'+self.capture_phase+'-rtc-status',regs['X00'],20).hex()
            if row['name']=='rtc_capture_state_update':
                row['rtc_capture_state_hex']=save(self.g,'zr-'+self.capture_phase+'-rtc-capture-state',regs['X00'],4).hex()
            if row['name'].startswith('sequence_callback_'):
                import json
                row.update(virtual_ns=json.loads(self.g.qmp.command('qom-get',path='/machine',
                    property='runtime-clock-state'))['virtual_ns'],
                    sequence_state_hex=save(self.g,'sequence-callback-state',0xa03e31700,0x700).hex())
                if pc==0x41140de0:
                    if self.sequence_callback_pending is not None:
                        raise ValueError('overlapping sequence callback observation')
                    self.sequence_callback_calls+=1
                    self.sequence_callback_pending=(regs['SP'],regs['X30'],regs['X00']&0xffffffff)
                    self.points[0x411454fc]='sequence_callback_return';self.g.rsp('Z1,411454fc,4')
                else:
                    if self.sequence_callback_pending is None:
                        raise ValueError('unpaired sequence callback return')
                    expected_sp,expected_lr,event=self.sequence_callback_pending
                    if (regs['SP'],regs['X30'])!=(expected_sp,expected_lr):
                        raise ValueError('sequence callback stack/return mismatch')
                    self.sequence_callback_pending=None
                    row['event_mask']=hex(event)
                    if self.sequence_callback_calls<256:
                        self.points[0x41140de0]='sequence_callback_argument';self.g.rsp('Z1,41140de0,4')
                row['callback_number']=self.sequence_callback_calls
                if pc==0x41140de0:row['event_mask']=hex(regs['X00']&0xffffffff)
            if row['name'].startswith('source_stop_step11_'):
                import json
                row.update(virtual_ns=json.loads(self.g.qmp.command('qom-get',path='/machine',
                    property='runtime-clock-state'))['virtual_ns'],
                    state_hex=save(self.g,'source-stop-step11-state',0xa057b0140,0x200).hex(),
                    stack_hex=save(self.g,'source-stop-step11-stack',regs['SP'],0x40).hex())
                if pc==0x4135fe54:
                    self.source_step11_calls+=1
                    row['original_return']=hex(int.from_bytes(save(self.g,
                        'source-stop-step11-caller',regs['SP']+0x18,8),'little'))
                    if 0x4135fe74 not in self.points:
                        self.points[0x4135fe74]='source_stop_step11_return';self.g.rsp('Z1,4135fe74,4')
                else:
                    row['original_return']=hex(regs['X30'])
                    if self.source_step11_calls<64:
                        self.points[0x4135fe54]='source_stop_step11_after_control';self.g.rsp('Z1,4135fe54,4')
                row['step11_call_number']=self.source_step11_calls
            if row['name'].startswith('source_control_'):
                import json
                row.update(virtual_ns=json.loads(self.g.qmp.command('qom-get',path='/machine',
                    property='runtime-clock-state'))['virtual_ns'],original_caller=hex(regs['X30']),
                    group0_control=self.g.rd(0x15080010),channel_control=self.g.rd(0x15080028))
                if pc==0x40e2bf00:
                    self.source_control_calls+=1
                    row.update(control_mask=hex(regs['X01']&0xffffffff),clear=bool(regs['X02']))
                    if regs['X30'] in (0x41364564,0x41364578):
                        # Both original wrappers save LR at[SP] and tail-call
                        # the MMIO setter through the lower driver.
                        row['wrapper_caller']=hex(int.from_bytes(save(self.g,
                            'source-control-wrapper-caller',regs['SP'],8),'little'))
                    if 0x40e2bf40 not in self.points:
                        self.points[0x40e2bf40]='source_control_return';self.g.rsp('Z1,40e2bf40,4')
                elif self.source_control_calls<64:
                    self.points[0x40e2bf00]='source_control_argument';self.g.rsp('Z1,40e2bf00,4')
                row['source_control_call_number']=self.source_control_calls
            if self.g.data.get('trace_sequence_waits'):
                import json
                if pc in self.wait_pairs:
                    self.wait_calls+=1
                    returned=self.wait_pairs[pc]
                    self.wait_pending[returned]=(pc,self.wait_calls)
                    row.update(wait_call_number=self.wait_calls,original_caller=hex(regs['X30']),
                        virtual_ns=json.loads(self.g.qmp.command('qom-get',path='/machine',
                            property='runtime-clock-state'))['virtual_ns'])
                    if returned not in self.points:
                        self.points[returned]=POINTS[returned];self.g.rsp(f'Z1,{returned:x},4')
                elif pc in self.wait_pending:
                    argument,number=self.wait_pending.pop(pc)
                    row.update(wait_call_number=number,returned_value=regs['X00']&0xffffffff,
                        virtual_ns=json.loads(self.g.qmp.command('qom-get',path='/machine',
                            property='runtime-clock-state'))['virtual_ns'])
                    if self.wait_calls<96:
                        self.points[argument]=POINTS[argument];self.g.rsp(f'Z1,{argument:x},4')
            if self.g.data.get('trace_sequence_watchdog') and row['name'].startswith('sequence_flow_watchdog_'):
                import json
                row['virtual_ns']=json.loads(self.g.qmp.command('qom-get',path='/machine',
                    property='runtime-clock-state'))['virtual_ns']
                if row['name']=='sequence_flow_watchdog_call_return':
                    original_pc,original_name,number=self.watchdog_returns.pop(pc)
                    row.update(call_number=number,original_call=original_name,
                        returned_value=regs['X00'],timer_hex=save(self.g,
                            'watchdog-call-return-timer',0xa03e316c8,0x20).hex())
                    if self.watchdog_calls<64:
                        self.points[original_pc]=original_name;self.g.rsp(f'Z1,{original_pc:x},4')
                elif row['name']!='sequence_flow_watchdog_expired':
                    self.watchdog_calls+=1
                    row.update(call_number=self.watchdog_calls,timer_object=hex(regs['X00']),
                        argument1=regs['X01'],timer_hex=save(self.g,'watchdog-call-timer',0xa03e316c8,0x20).hex())
                    returned=pc+4
                    if returned in self.points:raise ValueError('watchdog call-return breakpoint collision')
                    self.watchdog_returns[returned]=(pc,row['name'],self.watchdog_calls)
                    self.points[returned]='sequence_flow_watchdog_call_return';self.g.rsp(f'Z1,{returned:x},4')
            if row['name'].startswith('sequence_resource_'):
                import json
                row['virtual_ns']=json.loads(self.g.qmp.command('qom-get',path='/machine',
                    property='runtime-clock-state'))['virtual_ns']
                if row['name']=='sequence_resource_event':
                    self.sequence_resource_calls+=1
                    row.update(call_number=self.sequence_resource_calls,event=hex(regs['X00']&0xffffffff),
                        resource_id=hex(regs['X01']),original_return=hex(regs['X30']))
                    returned=regs['X30']
                    known_registration=self.points.get(returned,'').startswith('sequence_resource_registered_')
                    if (not 0x40160000<=returned<0x41490000 or returned&3 or
                            (returned in self.points and not known_registration)):
                        raise ValueError('ambiguous resource callback return observation')
                    self.sequence_resource_returns[returned]=self.sequence_resource_calls
                    if not known_registration:
                        self.points[returned]='sequence_resource_return';self.g.rsp(f'Z1,{returned:x},4')
                elif row['name']=='sequence_resource_return':
                    row['call_number']=self.sequence_resource_returns.pop(pc)
                    if self.sequence_resource_calls<24:
                        self.points[0x41146fd4]='sequence_resource_event';self.g.rsp('Z1,41146fd4,4')
                elif row['name'].startswith('sequence_resource_register_'):
                    row.update(callback=hex(regs['X00']),resource_id=hex(regs['X01']),
                        event_type=regs['X02'])
                elif row['name'].startswith('sequence_resource_registered_'):
                    row['original_returned_value']=regs['X00']
                    if pc in self.sequence_resource_returns:
                        row['callback_call_number']=self.sequence_resource_returns.pop(pc)
                        if self.sequence_resource_calls<24:
                            self.points[0x41146fd4]='sequence_resource_event';self.g.rsp('Z1,41146fd4,4')
                else:
                    row.update(event_object=hex(regs['X00']),notify_mask=hex(regs['X01']&0xffffffff))
            if row['name'] in ('sequence_wait_argument','sequence_wait_return'):
                import json
                row['virtual_ns']=json.loads(self.g.qmp.command('qom-get',path='/machine',
                    property='runtime-clock-state'))['virtual_ns']
                if row['name']=='sequence_wait_argument':
                    row.update(wait_object=hex(regs['X00']),wait_mask=hex(regs['X01']&0xffffffff),
                        timeout_argument=regs['X03']&0xffffffff)
                    if self.g.data.get('trace_sequence_resources'):
                        row['resource_item_metadata']={hex(index):save(self.g,
                            'sequence-wait-resource-'+hex(index),0xa029414a8+index*0x30,0x30).hex()
                            for index in (0x0c,0x5a,0x62,0x64)}
                        row['resource_groups_hex']=save(self.g,'sequence-wait-resource-groups',
                            0xa02942798,0x900).hex()
                else:row['returned_value']=regs['X00']&0xffffffff
            if row['name'].startswith('ui_language_'):
                from zr_ui_language_input import observe
                observe(self.g,row)
            if row['name']=='ui_menu_key_handler':
                self.mode_menu_calls+=1
                row.update(call_number=self.mode_menu_calls,original_caller=hex(regs['X30']),
                    diff_hex=save(self.g,f'zr-menu-key-{self.mode_menu_calls:02d}',regs['X00'],0x190).hex())
                if 0x405285e0 in self.points:raise ValueError('original menu handler return collision')
                self.points[0x405285e0]='ui_menu_key_handler_return';self.g.rsp('Z1,405285e0,4')
            if row['name']=='ui_menu_key_handler_return':
                row.update(call_number=self.mode_menu_calls,
                    property280c_hex=save(self.g,f'zr-menu-property-{self.mode_menu_calls:02d}',0xa03fea6d0,4).hex())
                if self.mode_menu_calls<self.mode_view_limit:
                    self.points[0x405284ec]='ui_menu_key_handler';self.g.rsp('Z1,405284ec,4')
                else:self.record['menu_key_trace_limit_reached']=True
            if row['name']=='ui_mode_view_dispatch':
                self.mode_view_calls+=1
                controller=save(self.g,f'zr-mode-view-controller-{self.mode_view_calls:02d}',regs['X00'],0x120)
                index=struct.unpack_from('<I',controller,0xd0)[0]
                if index>8:raise ValueError('bounded original UI view index required')
                row.update(call_number=self.mode_view_calls,view_index=index,
                    controller_hex=controller.hex(),
                    argument_hex=save(self.g,f'zr-mode-view-argument-{self.mode_view_calls:02d}',regs['X02'],16).hex(),
                    normalized_key_hex=save(self.g,f'zr-mode-view-key-{self.mode_view_calls:02d}',0xa034e3798,0x198).hex())
                for address,name in ((0x4039dc9c,'ui_mode_view_indirect'),(0x40412d60,'ui_mode_view_return')):
                    if address in self.points:raise ValueError('view dispatch observation collision')
                    self.points[address]=name;self.g.rsp(f'Z1,{address:x},4')
            if row['name']=='ui_mode_view_indirect':
                row.update(call_number=self.mode_view_calls,actual_callback=hex(regs['X03']),original_caller=hex(regs['X30']))
                if regs['X00']!=3 or regs['X30']!=0x40412d60:
                    raise ValueError('view callback must follow original kind3 call site')
                callback=regs['X03']
                if not 0x40160000<=callback<0x41490000 or callback in self.points:
                    raise ValueError('bounded distinct original view callback required')
                self.mode_view_callback=callback
                self.points[callback]='ui_mode_view_callback';self.g.rsp(f'Z1,{callback:x},4')
            if row['name']=='ui_mode_view_callback':
                row.update(call_number=self.mode_view_calls,original_caller=hex(regs['X30']),
                    argument_hex=save(self.g,f'zr-mode-view-callback-argument-{self.mode_view_calls:02d}',regs['X01'],16).hex())
                if self.g.data.get('trace_mode_view_controls'):
                    for address,name in ((0x404150f4,'mode_view_controls_argument_gate'),
                                         (0x40415100,'mode_view_controls_queue_gate'),
                                         (0x4041513c,'mode_view_controls_queue_decode_return'),
                                         (0x40415160,'mode_view_controls_remap_predicate'),
                                         (0x40415318,'mode_view_controls_mode_gate'),
                                         (0x40415368,'mode_view_controls_view_state'),
                                         (0x404164c0,'mode_view_controls_action_filter_return'),
                                         (0x404164d8,'mode_view_controls_frame_context'),
                                         (0x40416590,'mode_view_controls_final_action'),
                                         (0x404166a8,'mode_view_controls_context_gate'),
                                         (0x404166b0,'mode_view_controls_context_state'),
                                         (0x40416798,'mode_view_controls_binding_role_entry'),
                                         (0x404167a4,'mode_view_controls_binding_role'),
                                         (0x404c52cc,'mode_view_controls_binding_property'),
                                         (0x404c52d0,'mode_view_controls_binding_value'),
                                         (0x40415280,'mode_view_controls_decoder_return'),
                                         (0x40415170,'mode_view_controls_action')):
                        if address in self.points:raise ValueError('view control observation collision')
                        self.points[address]=name;self.g.rsp(f'Z1,{address:x},4')
            if row['name'].startswith('mode_view_controls_'):
                label=f'zr-mode-view-controls-{self.mode_view_calls:02d}-{row["name"]}'
                row.update(call_number=self.mode_view_calls,returned_value=regs['X00']&0xffffffff,
                    queue_indices_hex=save(self.g,label+'-indices',0xa034e3acc,8).hex(),
                    queue_mode_hex=save(self.g,label+'-mode',0xa034e5458,4).hex(),
                    property2423_hex=save(self.g,label+'-source',0xa03fea274,4).hex())
                row['action_registers']=dict(w20=regs['X20']&0xffffffff,w22=regs['X22']&0xffffffff)
                if row['name'] in ('mode_view_controls_argument_gate','mode_view_controls_queue_gate',
                        'mode_view_controls_queue_decode_return','mode_view_controls_remap_predicate','mode_view_controls_decoder_return'):
                    row['argument_hex']=save(self.g,label+'-argument',regs['X19'],16).hex()
                if row['name']=='mode_view_controls_decoder_return':
                    row['decoded_action_hex']=save(self.g,label+'-action',regs['SP']+0x9c,4).hex()
                if row['name']=='mode_view_controls_queue_decode_return':
                    row['queue_decoded_hex']=save(self.g,label+'-decoded',regs['SP']+0x90,12).hex()
            if row['name']=='ui_mode_view_return':
                row.update(call_number=self.mode_view_calls,
                    property280c_hex=save(self.g,f'zr-mode-view-property-{self.mode_view_calls:02d}',0xa03fea6d0,4).hex())
                if self.g.data.get('trace_mode_view_controls'):
                    for address in (0x404150f4,0x40415100,0x4041513c,0x40415160,0x40415318,
                            0x40415368,0x404164c0,0x404164d8,0x40416590,0x404166a8,0x404166b0,0x40416798,
                            0x404167a4,0x404c52cc,0x404c52d0,0x40415280,0x40415170):
                        if address in self.points:
                            self.g.rsp(f'z1,{address:x},4');del self.points[address]
                if self.mode_view_calls<self.mode_view_limit:
                    self.points[0x40412d5c]='ui_mode_view_dispatch';self.g.rsp('Z1,40412d5c,4')
                else:self.record['mode_view_trace_limit_reached']=True
            if row['name']=='ui_mode_key_handler':
                self.mode_ui_calls+=1
                row.update(call_number=self.mode_ui_calls,original_caller=hex(regs['X30']),
                    diff_hex=save(self.g,f'zr-mode-ui-input-{self.mode_ui_calls:02d}',regs['X00'],0x190).hex())
                for address,name in ((0x40413484,'ui_mode_key_transform_return'),
                                     (0x40413498,'ui_mode_key_filter_return'),
                                     (0x404134dc,'ui_mode_key_handler_done')):
                    if address in self.points:raise ValueError('UI mode handler observation collision')
                    self.points[address]=name;self.g.rsp(f'Z1,{address:x},4')
            if row['name'] in ('ui_mode_key_transform_return','ui_mode_key_filter_return','ui_mode_key_handler_done'):
                row.update(call_number=self.mode_ui_calls,returned_value=regs['X00']&0xffffffff,
                    diff_hex=save(self.g,f'zr-mode-ui-{row["name"]}-{self.mode_ui_calls:02d}',regs['X19'],0x190).hex(),
                    property280c_hex=save(self.g,f'zr-mode-ui-property-{self.mode_ui_calls:02d}',0xa03fea6d0,4).hex())
                if row['name']=='ui_mode_key_handler_done':
                    # Filter is skipped when the original transform returns0.
                    if 0x40413498 in self.points:
                        self.g.rsp('z1,40413498,4');del self.points[0x40413498]
                    if self.mode_ui_calls<self.g.data.get('mode_key_step_count',4):
                        self.points[0x40413418]='ui_mode_key_handler';self.g.rsp('Z1,40413418,4')
            if row['name']=='ui_mode_key_consumer':
                self.mode_key_calls+=1
                row.update(call_number=self.mode_key_calls,
                    parsed_status_hex=save(self.g,f'zr-mode-key-{self.mode_key_calls:02d}',regs['X00'],52).hex(),
                    original_caller=hex(regs['X30']))
                self.points[0x40f39984]='ui_mode_key_consumer_return'
                self.g.rsp('Z1,40f39984,4')
            if row['name']=='ui_mode_key_consumer_return':
                row.update(call_number=self.mode_key_calls,
                    property280c_hex=save(self.g,f'zr-mode-property-{self.mode_key_calls:02d}',0xa03fea6d0,4).hex())
                if self.g.data.get('trace_mode_key_dispatch'):
                    row['dispatch_storage_hex']=save(self.g,f'zr-mode-dispatch-storage-{self.mode_key_calls:02d}',
                        0xa034141d8,0x1c0).hex()
                limit=self.g.data.get('mode_key_step_count',4)+(self.g.data.get('mode_start_gate')=='initial-consumer-lcd')
                if self.mode_key_calls<limit:
                    self.points[0x40f398f8]='ui_mode_key_consumer'
                    self.g.rsp('Z1,40f398f8,4')
            if row['name']=='ui_mode_key_diff_callback':
                self.mode_diff_calls+=1
                row.update(call_number=self.mode_diff_calls,actual_callback=hex(regs['X08']),
                    diff_hex=save(self.g,f'zr-mode-diff-{self.mode_diff_calls:02d}',regs['X00'],0x190).hex(),
                    source_status_hex=save(self.g,f'zr-mode-diff-source-{self.mode_diff_calls:02d}',0xa034141f4,52).hex())
                self.points[0x40f396e4]='ui_mode_key_diff_return'
                self.g.rsp('Z1,40f396e4,4')
            if row['name']=='ui_mode_key_diff_return':
                row.update(call_number=self.mode_diff_calls,
                    property280c_hex=save(self.g,f'zr-mode-diff-property-{self.mode_diff_calls:02d}',0xa03fea6d0,4).hex())
                if self.mode_diff_calls<self.g.data.get('mode_key_step_count',4):
                    self.points[0x40f396e0]='ui_mode_key_diff_callback'
                    self.g.rsp('Z1,40f396e0,4')
            if row['name']=='ui_mode_key_selected_callback':
                self.mode_selected_calls+=1
                row.update(call_number=self.mode_selected_calls,actual_callback=hex(regs['X08']),
                    selected_object=hex(regs['X00']),
                    diff_hex=save(self.g,f'zr-mode-selected-diff-{self.mode_selected_calls:02d}',regs['X01'],0x190).hex())
                state=save(self.g,f'zr-mode-selected-app-state-{self.mode_selected_calls:02d}',0xa0282f780,16)
                row.update(app_selected_state=hex(struct.unpack_from('<Q',state)[0]),
                    app_current_state=struct.unpack_from('<I',state,8)[0])
                row.update(manager_enable_hex=save(self.g,f'zr-mode-manager-enable-{self.mode_selected_calls:02d}',
                        0xa03431860,0x10).hex(),
                    manager_gate_hex=save(self.g,f'zr-mode-manager-gate-{self.mode_selected_calls:02d}',
                        0xa03431be0,0x18).hex(),
                    manager_routes_hex=save(self.g,f'zr-mode-manager-routes-{self.mode_selected_calls:02d}',
                        0xa02824ad0,0x88).hex())
                self.points[0x40f6bff4]='ui_mode_key_selected_return'
                self.g.rsp('Z1,40f6bff4,4')
            if row['name']=='ui_mode_key_selected_return':
                row.update(call_number=self.mode_selected_calls,
                    property280c_hex=save(self.g,f'zr-mode-selected-property-{self.mode_selected_calls:02d}',0xa03fea6d0,4).hex())
                if self.mode_selected_calls<self.g.data.get('mode_key_step_count',4):
                    self.points[0x40f6bff0]='ui_mode_key_selected_callback'
                    self.g.rsp('Z1,40f6bff0,4')
            if row['name'].startswith('sensor_restart_'):
                import json
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row.update(original_caller=hex(regs['X30']),
                    event_wrapper_hex=save(self.g,label+'-event',0xa057afd40,0x40).hex(),
                    aux_state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-aux0-state')),
                    aux1_state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-aux1-state')),
                    polling_status=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-aux-status-state')),
                    global0_state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-global0-state')),
                    group0_control=self.g.rd(0x15080010),channel0_control=self.g.rd(0x15080028))
                if row['name'] in ('sensor_restart_aux1_isr','sensor_restart_aux1_callback'):
                    row['aux1_driver_hex']=save(self.g,label+'-driver',0xa0280d920,0x48).hex()
                if row['name'] in ('sensor_restart_notify1000','sensor_restart_notify4000','sensor_restart_notify400000',
                                   'sensor_restart_notify40','sensor_restart_notify80','sensor_restart_notify80_after_wait'):
                    row.update(status=hex(regs['X19']&0xffffffff),
                        notify_object=hex(regs['X00']),notify_mask=hex(regs['X01']&0xffffffff))
                    if row['name'] not in ('sensor_restart_notify400000','sensor_restart_notify40',
                                           'sensor_restart_notify80','sensor_restart_notify80_after_wait'):
                        row['event']=hex(regs['X20']&0xffffffff)
                    else:
                        # Global callback reuses X20 for the flag object.
                        # It is not the event ID at this later instruction.
                        row['producer_x20']=hex(regs['X20'])
                if row['name']=='sensor_restart_wait_argument':
                    row.update(wait_object=hex(regs['X00']),wait_mask=hex(regs['X01']&0xffffffff),
                        output_address=hex(regs['X02']),timeout_argument=regs['X03']&0xffffffff)
                if row['name']=='sensor_restart_wait_return':
                    row.update(returned_value=regs['X00']&0xffffffff,
                        result_hex=save(self.g,label+'-result',regs['SP']+0xc,4).hex())
                if row['name']=='sensor_restart_followup_entry':
                    row['input_flag']=regs['X00']&0xffffffff
                if row['name']=='sensor_restart_followup_query_return':
                    row.update(query_result=regs['X00']&0xffffffff,input_flag=regs['X19']&0xffffffff)
                if row['name'] in ('sensor_restart_followup_wait40_argument','sensor_restart_followup_wait80_argument'):
                    row.update(wait_object=hex(regs['X00']),wait_mask=hex(regs['X01']&0xffffffff),
                        output_address=hex(regs['X02']),timeout_argument=regs['X03']&0xffffffff)
                    if row['name']=='sensor_restart_followup_wait80_argument':
                        # Capture a producer after the original clear, even if
                        # an earlier periodic notification used the one-shot.
                        self.points[0x413531a0]='sensor_restart_notify80_after_wait'
                        self.g.rsp('Z1,413531a0,4')
                if row['name'] in ('sensor_restart_followup_wait40_return','sensor_restart_followup_wait80_return'):
                    offset=0xc if 'wait40_' in row['name'] else 8
                    row.update(returned_value=regs['X00']&0xffffffff,
                        result_hex=save(self.g,label+'-result',regs['SP']+offset,4).hex())
                if row['name'] in ('sensor_restart_followup40_return','sensor_restart_followup_caller_return'):
                    row['returned_value']=regs['X00']&0xffffffff
            if row['name'].startswith('stream154c_'):
                import json
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row.update(original_caller=hex(regs['X30']),
                    stream_state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='stream154c-state')))
                if row['name'] in ('stream154c_stop_entry','stream154c_idle_getter'):
                    raw=save(self.g,label+'-driver',regs['X00'],0xa0)
                    row.update(driver_address=hex(regs['X00']),driver_channel=struct.unpack_from('<I',raw,4)[0],
                        stop_flag=raw[0x9c],reset_flag=raw[0x8c],driver_hex=raw.hex())
                if row['name'] in ('stream154c_stop_return','stream154c_original_caller_resume'):
                    row['returned_value']=regs['X00']&0xffffffff
                if row['name']=='stream154c_idle_getter':
                    self.stream154c_output=regs['X01']
                    row['output_address']=hex(regs['X01'])
                if row['name']=='stream154c_idle_getter_return' and hasattr(self,'stream154c_output'):
                    raw=save(self.g,label+'-output',self.stream154c_output,0x28)
                    row.update(output_address=hex(self.stream154c_output),output_hex=raw.hex(),
                        idle=struct.unpack_from('<I',raw)[0],bank0=struct.unpack_from('<I',raw,0xc)[0],
                        bank1=struct.unpack_from('<I',raw,0x24)[0])
            if row['name'].startswith('aux_config1508_'):
                import json
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row['aux_config_state']=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-aux-config-state'))
                if row['name'].endswith('_entry'):
                    row.update(selector=regs['X01']&0xffffffff,field0=regs['X02']&0xffffffff,
                        field16=regs['X03']&0xffffffff,original_caller=hex(regs['X30']),
                        driver_hex=save(self.g,label+'-driver',regs['X00'],0x28).hex())
            if row['name'].startswith('command1508_'):
                import json
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row['command_state']=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-command-state'))
                if row['name']=='command1508_entry':
                    row.update(request_mask=hex(regs['X01']&0xffffffff),original_caller=hex(regs['X30']),
                        driver_hex=save(self.g,label+'-driver',regs['X00'],0x18).hex())
            if row['name'].startswith('channel_event_'):
                import json
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row.update(driver_hex=save(self.g,label+'-driver',0xa0280d968,0xa8).hex(),
                    sensor_globals_hex=save(self.g,label+'-sensor',0xa057b0140,0x200).hex(),
                    channel_state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-channel-state')),
                    group0_control=self.g.rd(0x15080010),channel_control=self.g.rd(0x15080028))
                if row['name']=='channel_event_native_callback':
                    row.update(event=hex(regs['X00']&0xffffffff),status=hex(regs['X01']&0xffffffff))
                if row['name'].endswith('_notification'):
                    row.update(event=hex(regs['X00']&0xffffffff),callback=hex(regs['X08']))
            if row['name'].startswith('output_group1508_'):
                import json
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row['group_state']=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-group-state'))
                if row['name']=='output_group1508_bank1_entry':
                    row.update(request_mask=hex(regs['X01']&0xffffffff),original_caller=hex(regs['X30']),
                        driver_hex=save(self.g,label+'-driver',regs['X00'],0x18).hex())
            if row['name'].startswith('readback150d_'):
                import json
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row['readback_state']=json.loads(self.g.qmp.command('qom-get',path='/machine',property='engine150d-readback-state'))
                if row['name']=='readback150d_getter1_entry':
                    row.update(output_address=hex(regs['X01']),original_caller=hex(regs['X30']),
                        driver_hex=save(self.g,label+'-driver',regs['X00'],0x18).hex())
                else:
                    row.update(output_address=hex(regs['X20']),
                        output_hex=save(self.g,label+'-output',regs['X20'],4).hex())
            if row['name'].startswith('sequence_flow_'):
                import json
                label=f'zr-{self.capture_phase}-{row["name"]}'
                if row['name']=='sequence_flow_watchdog_expired' and self.g.data.get('capture_tasks'):
                    from probe_tasks import capture
                    capture(self.g,'zr-watchdog-tasks',bindings=dict(globals=0xa057e2200,
                        task_pointer=0xa057e2300,code_end=0x41490000,
                        thread_wrapper=0x40f42204,resume_pc=0x401898cc))
                row.update(sequence_context_hex=save(self.g,label+'-context',0xa03e31670,0x1d0).hex(),
                    watchdog_flag_hex=save(self.g,label+'-watchdog-flag',0xa03e31d20,1).hex(),
                    driver_hex=save(self.g,label+'-driver',0xa0280d968,0xa8).hex(),
                    aux_state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-aux0-state')),
                    channel_state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-channel-state')),
                    global0_state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-global0-state')))
                if row['name'].endswith('_argument'):
                    row.update(wait_object=hex(regs['X00']),wait_mask=hex(regs['X01']&0xffffffff),
                        word2=hex(regs['X02']&0xffffffff),word3=hex(regs['X03']&0xffffffff),
                        wait_abi='direct wrapper' if 'wait1000_' in row['name'] or 'wait2000_' in row['name'] else 'sequence wrapper: word2 timeout, word3 failure reason')
                if row['name'].endswith('_return'):row['returned_value']=regs['X00']&0xffffffff
                if row['name'].startswith('sequence_flow_watchdog_start') or row['name']=='sequence_flow_watchdog_restart':
                    row.update(timer_object=hex(regs['X00']),period_argument=regs['X01']&0xffffffff)
            if row['name'].startswith('global_event_'):
                import json
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row.update(driver_hex=save(self.g,label+'-driver',0xa0280d968,0xa8).hex(),
                    sensor_globals_hex=save(self.g,label+'-sensor',0xa057b0140,0x200).hex(),
                    sequence_context_hex=save(self.g,label+'-sequence',0xa03e31670,0x1d0).hex(),
                    producer_return=hex(regs['X30']),
                    group0_control=self.g.rd(0x15080010),channel_control=self.g.rd(0x15080028),
                    global0_state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-global0-state')))
                if row['name']=='global_event_native_callback':
                    row.update(event=hex(regs['X00']&0xffffffff),status=hex(regs['X01']&0xffffffff))
                if row['name'] in ('global_event_sequence_notification','global_event_bit4_sequence_notification'):
                    row.update(event=hex(regs['X00']&0xffffffff),callback=hex(regs['X08']))
            if row['name'].startswith('sensor_mode_'):
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row.update(mode_settings_hex=save(self.g,label+'-settings',0xa057b0188,0x80).hex(),
                    mode_context_hex=save(self.g,label+'-context',0xa02b6f4c8,0x180).hex(),
                    event_wrapper_hex=save(self.g,label+'-event',0xa057afd40,0x40).hex(),
                    event_driver_globals_hex=save(self.g,label+'-driver',0xa030f6ee0,0x48).hex())
                row['aux_driver_hex']=save(self.g,label+'-aux-driver',0xa0280d920,0x48).hex()
                if row['name'] in ('sensor_mode_aux_isr','sensor_mode_aux_callback','sensor_mode_notify2000'):
                    import json
                    row['aux_state']=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-aux0-state'))
                if row['name']=='sensor_mode_aux_callback':
                    row.update(event=hex(regs['X00']&0xffffffff),status=hex(regs['X01']&0xffffffff))
                if row['name']=='sensor_mode_notify2000':
                    row.update(event=hex(regs['X20']&0xffffffff),status=hex(regs['X19']&0xffffffff),
                        notify_object=hex(regs['X00']),notify_mask=hex(regs['X01']&0xffffffff))
                if row['name']=='sensor_mode_select':row['mode_selector']=regs['X09']&0xffff
                if 'argument_' in row['name']:
                    row.update(wait_object=hex(regs['X00']),wait_mask=hex(regs['X01']&0xffffffff),
                        timeout_argument=hex(regs['X03']&0xffffffff))
                if 'return' in row['name']:
                    row['returned_value']=regs['X00']&0xffffffff
                    if '_return_' in row['name']:row['result_hex']=save(self.g,label+'-result',regs['SP']+0xc,4).hex()
            if row['name'].startswith('primary_native_'):
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row.update(driver_globals_hex=save(self.g,label+'-driver',0xa030f1160,0x100).hex(),
                    subscribers_hex=save(self.g,label+'-subscribers',0xa055ba500,0x140).hex(),
                    channel_mode_hex=save(self.g,label+'-mode',0xa055ba650,8).hex(),
                    status_globals_hex=save(self.g,label+'-status',0xa055bd640,0x28).hex(),
                    producer_return=hex(regs['X30']))
                if row['name'] in ('primary_native_driver_callback','primary_native_dispatch'):
                    row['event']=hex(regs['X00']&0xffffffff)
                    if 0xa00000000<=regs['X01']<0xa40000000-0x40:
                        row['payload_hex']=save(self.g,label+'-payload',regs['X01'],0x40).hex()
                if row['name'] in ('primary_native_bit2_subscriber','primary_native_bit2_single_subscriber'):
                    row.update(callback=hex(regs['X08']),event=hex(regs['X20']&0xffffffff))
            if row['name'].startswith('front_channel_') or row['name']=='sequence_sync8_producer':
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row.update(front_request_hex=save(self.g,label+'-request',0xa0412e9f8,0x80).hex(),
                    channel_driver_hex=save(self.g,label+'-channel',0xa055ba650,0x180).hex(),
                    event_wrapper_hex=save(self.g,label+'-event',0xa0412e8c8,0x28).hex(),
                    producer_return=hex(regs['X30']))
                if 'wait4_argument' in row['name']:
                    row.update(wait_object=hex(regs['X00']),wait_mask=hex(regs['X01']&0xffffffff),
                        timeout_argument=hex(regs['X03']&0xffffffff))
                if '_return_' in row['name']:row['returned_value']=regs['X00']&0xffffffff
                if row['name'].startswith('front_channel_prestart_'):
                    row['prestart_event_hex']=save(self.g,label+'-prestart-event',0xa030f1160,0x100).hex()
                    row['primary_object_hex']=save(self.g,label+'-primary-object',0xa0280d748,0x38).hex()
                    if row['name']=='front_channel_prestart_wait_argument':
                        row.update(wait_object=hex(regs['X00']),wait_mask=hex(regs['X01']&0xffffffff),
                            timeout_argument=hex(regs['X03']&0xffffffff))
                    else:row['result_hex']=save(self.g,label+'-result',regs['SP']+8,4).hex()
                if row['name']=='front_channel_bus_start_argument':
                    raw=save(self.g,label+'-worker',0xa030f0c00,0x2b0)
                    row['bus_worker_hex']=raw.hex()
                    row['bus_worker_callbacks']={hex(off):hex(struct.unpack_from('<Q',raw,off)[0])
                        for off in (0x48,0x58,0x60,0x68,0x78)}
                    for field,value in row['bus_worker_callbacks'].items():
                        callback=int(value,0)
                        if 0x40160000<=callback<0x41490000 and not callback&3 and callback not in self.points:
                            self.points[callback]='front_channel_native_worker_'+field
                            self.g.rsp(f'Z1,{callback:x},4')
            if row['name']=='primary_bank1_native_driver_callback':
                row.update(event=hex(regs['X00']&0xffffffff),producer_return=hex(regs['X30']))
                if 0xa00000000<=regs['X01']<0xa40000000-0x40:
                    row['payload_hex']=save(self.g,'zr-'+self.capture_phase+'-bank1-payload',regs['X01'],0x40).hex()
            if row['name'].startswith('sequence_sync8_'):
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row['event_wrapper_hex']=save(self.g,label+'-event',0xa03e316e8,0x28).hex()
                row['sequence_globals_hex']=save(self.g,label+'-globals',0xa03e31710,0x110).hex()
                if '_argument_' in row['name']:
                    row.update(wait_object=hex(regs['X00']),wait_mask=hex(regs['X01']&0xffffffff),
                        timeout_argument=hex(regs['X02']&0xffffffff),reason=hex(regs['X03']&0xffffffff))
                else:row['returned_value']=regs['X00']&0xffffffff
            if row['name'].startswith('ui_render_'):
                if row['name']=='ui_render_wait_argument':
                    self.render_waits+=1
                    for candidate in (0x402f741c,0x402f05d0,0x402f072c,0x402f2b08):
                        if candidate not in self.points:
                            self.points[candidate]=POINTS[candidate]
                            self.g.rsp(f'Z1,{candidate:x},4')
                label=f'zr-{self.capture_phase}-{row["name"]}-{self.render_waits:02d}'
                row.update(call_number=self.render_waits,
                    worker_hex=save(self.g,label+'-worker',0xa0305b7c0,0x50).hex(),
                    event_wrapper_hex=save(self.g,label+'-event',0xa0305b870,0x60).hex(),
                    shared_packet_hex=save(self.g,label+'-shared-packet',0xa0305bae0,0x40).hex())
                if row['name']=='ui_render_wait_argument':
                    row.update(wait_object=hex(regs['X00']),wait_mask=hex(regs['X01']&0xffffffff))
                if row['name']=='ui_render_wait_return':
                    row.update(returned_value=regs['X00']&0xffffffff,
                        result_hex=save(self.g,label+'-result',regs['SP']+0x7c,4).hex())
                    if self.render_waits<16:
                        # The next queued job can finish before its caller
                        # reaches wait. Arm producer points at this return,
                        # not only after observing the next wait argument.
                        for candidate in (0x402f7418,0x402f05d0,0x402f072c,0x402f2b08):
                            if candidate not in self.points:
                                self.points[candidate]=POINTS[candidate]
                                self.g.rsp(f'Z1,{candidate:x},4')
                if row['name'] in ('ui_render_worker_completed','ui_render_worker_callback'):
                    row['packet_hex']=save(self.g,label+'-packet',regs['X19'],0x40).hex()
                if row['name']=='ui_render_worker_callback':
                    row['callback']=hex(regs['X08'])
            if row['name']=='app_capture_transition_result':
                row['input_hex']=save(self.g,'zr-capture-transition-result',regs['X01'],4).hex()
                row['object_hex']=save(self.g,'zr-capture-transition-object',regs['X19'],0x258).hex()
            if row['name']=='mcu_mode_callback_dispatch':
                row['callback']=hex(regs['X02'])
                row['payload_hex']=save(self.g,'zr-mode-callback-payload',regs['X01'],4).hex()
                # Code bytes are in the immutable pinned EG. Do not assume
                # CPU0 maps a callback executed by another core identically.
                from probe_zr_boot import MAIN,ENTRY
                if not ENTRY<=regs['X02']<=0x41490000-0x80:
                    raise ValueError('mode callback outside pinned executable prefix')
                with MAIN.open('rb') as f:
                    f.seek(regs['X02']-ENTRY)
                    row['callback_code_hex']=f.read(0x80).hex()
                row['callback_code_scope']='immutable EG file bytes; not an MMU/runtime capture'
            if row['name'].startswith('capture_late_'):
                row['property_hex']=save(self.g,'zr-'+row['name']+'-property',0xa02b8cd3c,4).hex()
                row['update_flag_hex']=save(self.g,'zr-'+row['name']+'-update-flag',0xa03e3dfe8,4).hex()
                row['state']=capture_ready_state(self.g,'zr-'+row['name'])
                if row['name']=='capture_late_event_wait_return':
                    row['wait_result_hex']=save(self.g,'zr-late-wait-result',regs['SP']+0xc,4).hex()
            if row['name'].startswith('capture_controller_'):
                if row['name']=='capture_controller_enter':
                    self.controller_calls+=1
                    for candidate in (0x411a9dd8,0x411aa9ec):
                        if candidate not in self.points:
                            self.points[candidate]=POINTS[candidate]
                            self.g.rsp(f'Z1,{candidate:x},4')
                label=f'zr-{self.capture_phase}-{row["name"]}-{self.controller_calls:02d}'
                raw=save(self.g,label+'-globals',0xa03e3dd90,0x50)
                row.update(call_number=self.controller_calls,globals_hex=raw.hex(),
                           current_state=struct.unpack_from('<I',raw)[0])
                if row['name']=='capture_controller_enter':
                    row.update(operation=regs['X00']&0xffffffff,status=regs['X01']&0xffffffff,
                               parameter=hex(regs['X02']),caller=hex(regs['X30']))
                    if regs['X02']:
                        row['parameter_hex']=save(self.g,label+'-parameter',regs['X02'],4).hex()
                if row['name']=='capture_controller_decision':
                    stack=save(self.g,label+'-stack',regs['SP'],0x30)
                    row.update(operation=regs['X19']&0xffffffff,status=regs['X21']&0xffffffff,
                        changed=bool(regs['X00']&1),reason=struct.unpack_from('<I',stack,4)[0],
                        next_state=struct.unpack_from('<I',stack,0x2c)[0])
                if row['name']=='capture_controller_exit' and self.controller_calls<16:
                    self.points[0x411a9d90]=POINTS[0x411a9d90]
                    self.g.rsp('Z1,411a9d90,4')
            if row['name'].startswith('capture_completion_'):
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row['globals_hex']=save(self.g,label+'-globals',0xa03e3dd90,0x50).hex()
                if row['name']=='capture_completion_enter':
                    row.update(operation=regs['X00']&0xffffffff,status=regs['X01']&0xffffffff,
                               caller=hex(regs['X30']))
                else:row['payload_value']=regs['X19']&0xffffffff
            if row['name'].startswith('capture_begin_'):
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row['capture_globals_hex']=save(self.g,label+'-capture-globals',0xa03e3dd90,0x50).hex()
                row['sequence_globals_hex']=save(self.g,label+'-sequence-globals',0xa03e37fd0,0x30).hex()
                if row['name']=='capture_begin_completion_schedule':
                    row['payload_hex']=save(self.g,label+'-payload',regs['X19'],4).hex()
                if row['name']=='capture_begin_completion_consumer':
                    row['payload_hex']=save(self.g,label+'-payload',regs['X00'],4).hex()
                if row['name']=='capture_begin_timeout':
                    row['timeout_globals_hex']=save(self.g,label+'-timeout-globals',0xa03e3dda0,0x20).hex()
                if row['name']=='capture_begin_failure_producer':
                    row['guard_value']=regs['X09']&0xffffffff
            if row['name'].startswith('front_') and not row['name'].startswith('front_channel_'):
                label=f'zr-{self.capture_phase}-{row["name"]}'
                row['returned_value']=regs['X00']&0xffffffff
                row['front_globals_hex']=save(self.g,label+'-globals',0xa03e387a0,0x48).hex()
                if row['name']=='front_resource_registration':
                    row.update(callback=hex(regs['X00']),item=hex(regs['X01']&0xffffffff),
                               selector=regs['X02']&0xffffffff)
                if row['name'] in ('front_resource_callback','front_resource_notification'):
                    row.update(event=hex(regs['X00']&0xffffffff),item=hex(regs['X01']&0xffffffff),
                               caller=hex(regs['X30']))
                if row['name']=='front_resource_notification':
                    raw=save(self.g,label+'-item22',0xa029414a8+0x22*0x30,0x30)
                    row['item22_hex']=raw.hex()
                    pointer=struct.unpack_from('<Q',raw,0x10)[0]
                    row['item22_pointer']=hex(pointer)
                    if pointer:
                        row['item22_content_hex']=save(self.g,label+'-content',pointer,0x200).hex()
                if row['name']=='front_pipeline_result':
                    row['pipeline_success']=bool(regs['X22']&1)
                    row['configuration_pointer']=hex(regs['X20'])
                    row['configuration_hex']=save(self.g,label+'-configuration',regs['X20'],0x80,
                                                   virtual_cpu=row['cpu']).hex()
                if row['name'].startswith('front_followup_'):
                    row['completion_bits_hex']=save(self.g,label+'-completion-bits',0xa03e3a5f0,4).hex()
                    row['request_state_hex']=save(self.g,label+'-request-state',0xa03b7f264,0x50).hex()
                    if row['name'].startswith('front_followup_event_producer_'):
                        row.update(event=hex(regs['X00']&0xffffffff),target=hex(regs['X08']),
                                   payload_pointer=hex(regs['X01']))
                if row['name']=='front_submit_enter':
                    row['argument_hex']=save(self.g,label+'-argument',regs['X00'],0xc8).hex()
                if row['name'].startswith('front_event_wait'):
                    row['event_wrapper_hex']=save(self.g,label+'-event',0xa0412e8c8,0x60).hex()
                if row['name'].startswith('front_prepare_'):
                    row['configuration_pointer']=hex(regs['X20'])
                    row['configuration_translation']=self.g.qmp.hmp(f'gva2gpa {regs["X20"]:#x}',0)
            if row['name'] in ('sequence_transition_wait_return','sequence_transition_result_gate'):
                row['returned_value']=regs['X00']&0xffffffff
                row['combined_result']=regs['X08']&0xff
                row['branch_flags_hex']=save(self.g,'zr-'+row['name']+'-flags',0xa03e31bec,5).hex()
                row['branch_flags_scope']='two boolean branch inputs; semantic role not established, not proven completion flags'
                row['wait_object_hex']=save(self.g,'zr-'+row['name']+'-wait',0xa03e316e8,0x20).hex()
            if row['name'].startswith('primary_source_boundary_'):
                import json
                if row['name'].endswith('_return'):
                    row['returned_value']=regs['X00']&0xffffffff
                else:
                    row.update(event_object=hex(regs['X00']),mask=hex(regs['X01']&0xffffffff),
                               timeout_argument=regs['X03']&0xffffffff)
                if row['name']=='primary_source_boundary_wait':
                    if 0x412aa7b4 not in self.points:
                        self.points[0x412aa7b4]='primary_source_boundary_notify_after_wait'
                        self.g.rsp('Z1,412aa7b4,4')
                    if self.g.data.get('mode_burst_min_frames') and self.capture_phase=='capture':
                        count=self.g.data.get('capture_source_boundary_waits',0)+1
                        self.g.data['capture_source_boundary_waits']=count
                        row['boundary_wait_number']=count
                        if 0x412aab68 not in self.points:
                            self.points[0x412aab68]='primary_source_boundary_wait_return'
                            self.g.rsp('Z1,412aab68,4')
                elif (row['name']=='primary_source_boundary_wait_return' and
                      self.g.data.get('mode_burst_min_frames') and self.capture_phase=='capture' and
                      self.g.data.get('capture_source_boundary_waits',0)<64 and
                      0x412aab64 not in self.points):
                    self.points[0x412aab64]='primary_source_boundary_wait'
                    self.g.rsp('Z1,412aab64,4')
                if self.g.data.get('mode_burst_min_frames'):
                    row['virtual_ns']=json.loads(self.g.qmp.command('qom-get',path='/machine',property='runtime-clock-state'))['virtual_ns']
                    row['input_owner_states']={k:json.loads(self.g.qmp.command('qom-get',path='/machine',property=k))
                        for k in ('primary-d980-state','primary-d980-single-frame-state',
                                  'primary-d980-prepared-start-state','primary-reset-state',
                                  'engine153-deferred-input-state','engine151-capture-wait-state')}
                row['device_states']={k:json.loads(self.g.qmp.command('qom-get',path='/machine',property=k))
                    for k in ('event1508-channel-state','event1508-group-state','engine150c-state',
                              'engine1543-control-state','engine151-control-state','engine1518-state',
                              'raw-pipeline-state','statistics-state','raw-source-boundary-state')}
                row['primary_masks']={hex(a):self.g.rd(a) for a in (0x150c0200,0x150c020c,0x150c0218)}
            if row['name']=='fault_handler_entry':
                row['fault_event_hex']=save(self.g,'zr-fault-handler-event',regs['X00'],16).hex()
            if row['name']=='fault_event_translate':
                row['input_hex']=save(self.g,'zr-fault-input',regs['X19'],16).hex()
                row['producer_return']=hex(struct.unpack('<Q',save(self.g,'zr-fault-input-return',regs['SP']+0x98,8))[0])
            if row['name']=='fault_status_translate':
                row['input_hex']=save(self.g,'zr-fault-status',regs['X19'],12).hex()
                row['producer_return']=hex(struct.unpack('<Q',save(self.g,'zr-fault-status-return',regs['SP']+0x98,8))[0])
            if row['name']=='fault_bit10_report':
                row['failure_mask']=hex(regs['X19']&0xffffffff)
                row['producer_return']=hex(struct.unpack('<Q',save(self.g,'zr-fault-bit10-return',regs['SP']+0x18,8))[0])
                row['sequence_state_hex']=save(self.g,'zr-fault-sequence-state',0xa03e31710,0x30).hex()
            if row['name']=='fault_reason9_report':
                row['failure_mask']=hex(regs['X19']&0xffffffff)
                row['producer_return']=hex(struct.unpack('<Q',save(self.g,'zr-fault-reason9-return',regs['SP']+0x18,8))[0])
                row['sequence_state_hex']=save(self.g,'zr-fault-reason9-state',0xa03e31710,0x110).hex()
                row['caller_stack_hex']=save(self.g,'zr-fault-reason9-stack',regs['SP']+0x20,0x100).hex()
            if row['name']=='fault_init_results':
                row['results_hex']=save(self.g,'zr-device-init-results',regs['SP'],0x40).hex()
            if row['name']=='fault_parameter_source':
                source=regs['X08']
                row['source_address']=hex(source)
                address=source+0x117ab4
                if 0xa00000000<=address<=0xa40000000-16:
                    row['header_hex']=save(self.g,'zr-device-parameter-version',address,16).hex()
                elif 0x40000000<=address<=0x48000000-16:
                    row['header_hex']=self.g.read_rom_bytes(address,16).hex()
                else:raise ValueError('device parameter version outside modeled RAM/ROM')
            if row['name']=='fault_parameter_version':
                row.update(decoded_version=regs['X19']&0xffffffff,
                           first_version_byte=regs['X20']&0xff)
            if row['name']=='ui_ready_producer_gate':
                row.update(gate_value=regs['X08']&0xffffffff,
                           payload_value=regs['X22']&0xffffffff)
            if row['name']=='ui_ready_status_consumer':
                row['status_hex']=save(self.g,'zr-ui-ready-status',regs['X20'],4).hex()
            if row['name']=='graphics_secondary_geometry':
                from capture_zr_secondary import capture
                row['secondary']=capture(self.g,regs)
            if row['name'].startswith('capture_status_'):
                row['state']=capture_ready_state(self.g,'zr-'+row['name'])
                if row['name'] in ('capture_status_cache_query','capture_status_dependency_return'):
                    row['query_stack_hex']=save(self.g,'zr-'+row['name']+'-stack',regs['SP'],0x20).hex()
                if row['name'] in ('capture_status_query_return','capture_status_store'):
                    row['returned_mask']=regs['X00']&0xffffffff
                if row['name']=='capture_status_message_producer':
                    row.update(message=hex(regs['X00']&0xffffffff),actual_callback=hex(regs['X02']),
                        payload_hex=save(self.g,'zr-capture-status-message',regs['X01'],4).hex())
            if row['name'].startswith('orientation_'):
                row['state']=capture_ready_state(self.g,'zr-'+row['name'])
                if row['name'] in ('orientation_init_parameters','orientation_init_missing_parameters'):
                    row['context_hex']=save(self.g,'zr-'+row['name']+'-context',0xa03022300,0x1c8).hex()
                    if 'orientation_parameter_rom_input' in self.g.data:
                        observed=[]
                        for item in self.g.data['orientation_parameter_rom_input']['items']:
                            block=self.g.read_rom_bytes(int(item['address'],0),item['bytes'])
                            import hashlib
                            digest=hashlib.sha256(block).hexdigest()
                            observed.append(dict(id=item['id'],address=item['address'],sha256=digest))
                            self.g.check('original orientation ROM input '+item['id']+' retained',digest==item['sha256'])
                        row['parameter_rom_observations']=observed
                if row['name']=='orientation_status_bind':
                    row['registered_callback']=hex(regs['X00'])
                if row['name']=='orientation_sample_bytes':
                    row['sample_hex']=save(self.g,'zr-orientation-sample-wire',regs['SP']+0x28,6).hex()
                if row['name']=='orientation_sample_decoded':
                    raw=save(self.g,'zr-orientation-sample-decoded',0xa03022300+0x28,8)
                    row.update(sample_hex=raw.hex(),sample_xyz=struct.unpack_from('<hhh',raw),
                        returned_success=regs['X00']&0xffffffff)
                if row['name']=='orientation_init_completed':
                    row['derived_context_hex']=save(self.g,'zr-orientation-derived-context',0xa03022268,0x98).hex()
                if row['name']=='orientation_bus_write':
                    size=regs['X02']&0xffffffff
                    if not 0<size<=0x100:raise ValueError('bounded original orientation TX required')
                    row.update(register=regs['X00']&0xffffffff,
                        tx_hex=save(self.g,'zr-orientation-tx',regs['X01'],size).hex())
            if row['name'].startswith('ready_bitmap_'):
                row['bitmap']=capture_ready_bitmap(self.g,'zr-'+row['name'])
                if row['name']=='ready_bitmap_bind':
                    row['registered_callback']=hex(regs['X00'])
                if row['name']=='ready_bitmap_enable':
                    row['notification_bit']=regs['X00']&0xffffffff
                if row['name'] in ('ready_bitmap_set','ready_bitmap_clear'):
                    count=self.bitmap_calls.get(pc,0)+1
                    self.bitmap_calls[pc]=count
                    row.update(index=regs['X00']&0xffffffff,call_number=count)
                    return_pc=regs['X30']
                    if count<16:
                        if not 0x40160000<=return_pc<0x41490000 or return_pc&3:
                            raise ValueError('bitmap observation requires bounded original return')
                        if return_pc not in self.points:
                            self.points[return_pc]='ready_bitmap_return'
                            self.bitmap_returns[return_pc]=pc
                            self.g.rsp(f'Z1,{return_pc:x},4')
                        else:row['return_already_observed']=hex(return_pc)
                if row['name']=='ready_bitmap_return':
                    entry=self.bitmap_returns.pop(pc)
                    self.points[entry]=POINTS[entry]
                    self.g.rsp(f'Z1,{entry:x},4')
                if row['name'].endswith('_notification'):
                    row.update(message=hex(regs['X00']&0xffffffff),
                        payload_address=hex(regs['X01']),actual_callback=hex(regs['X02']))
            if row['name']=='fault_notification_producer':
                row['notification_code']=hex(regs['X19']&0xffffffff)
                row['producer_return']=hex(struct.unpack('<Q',save(self.g,'zr-fault-notification-return',regs['SP']+0x378,8))[0])
            if row['name']=='fault_list_append':
                row.update(fault_code=hex(regs['X20']&0xffffffff),
                    urgent=bool(regs['X22']&1),notify=bool(regs['X21']&1),
                    producer_return=hex(struct.unpack('<Q',save(self.g,'zr-fault-producer-return',regs['SP']+0x208,8))[0]),
                    fault_list_hex=save(self.g,'zr-fault-list-append',regs['SP']+8,0x11c).hex())
            if row['name'] in ('ui_fault_list_query_return','ui_update_fault_list_query_return'):
                name=row['name'];n=self.ui_fault_queries.get(name,0)+1
                self.ui_fault_queries[name]=n
                raw=save(self.g,f'zr-{self.capture_phase}-{name}-{n:03d}',regs['SP'],0x11c)
                count=struct.unpack_from('<I',raw,0x114)[0]
                if count>0x114//4:raise ValueError('original fault list count exceeds captured entries')
                row.update(call_number=n,fault_list_hex=raw.hex(),fault_count=count,
                    fault_codes=list(struct.unpack_from('<'+str(count)+'I',raw)) if count else [])
                returned=0x404c59ac if name=='ui_fault_list_query_return' else 0x404c5a10
                self.points[returned]='ui_fault_list_boolean_return' if returned==0x404c59ac else 'ui_update_fault_list_boolean_return'
                self.g.rsp(f'Z1,{returned:x},4')
            if row['name'] in ('ui_fault_list_boolean_return','ui_update_fault_list_boolean_return'):
                row['returned_value']=regs['X00']&0xffffffff
                name='ui_fault_list_query_return' if row['name']=='ui_fault_list_boolean_return' else 'ui_update_fault_list_query_return'
                if self.ui_fault_queries.get(name,0)<8:
                    query_pc=0x404c5968 if name=='ui_fault_list_query_return' else 0x404c59d0
                    self.points[query_pc]=name
                    self.g.rsp(f'Z1,{query_pc:x},4')
            if row['name']=='ui_initial_request_selector':
                row['initial_request_index']=regs['X08']
                row['request_object_hex']=save(self.g,'zr-ui-initial-request-object',regs['X19'],0x40).hex()
            if row['name'].startswith('ui_alert_'):
                row['flag_address']='0xa034fb954'
                row['flag_hex']=save(self.g,'zr-'+self.capture_phase+'-'+row['name']+'-flag',0xa034fb954,1).hex()
                row['original_return']=hex(regs['X30'])
                if row['name']=='ui_alert_property2937_return':
                    row['property_id']='0x2937'
                    row['returned_value']=regs['X00']&0xffffffff
                    row['original_caller']=hex(struct.unpack('<Q',save(self.g,'zr-'+self.capture_phase+'-ui-alert-caller',regs['SP'],8))[0])
                    row['property_storage_address']='0xa03feaba8'
                    row['property_storage_hex']=save(self.g,'zr-'+self.capture_phase+'-ui-alert-property-storage',0xa03feaba8,4).hex()
                if row['name']=='ui_alert_flag76_store_entry':row['input_value']=regs['X01']&0xffffffff
                if row['name']=='ui_alert_flag76_predicate_return':row['returned_value']=regs['X00']&0xffffffff
                if row['name']=='ui_alert_resource_status_return':row['returned_value']=regs['X00']&0xffffffff
                if row['name']=='ui_alert_resource_status_publish':
                    row.update(event=hex(regs['X00']&0xffffffff),input_value=regs['X01']&0xffffffff)
                if row['name'].startswith('ui_alert_resource_check_'):
                    ident=int(row['name'].split('_')[-2],16)
                    label='zr-'+self.capture_phase+'-'+row['name']
                    item=save(self.g,label+'-item',0xa029414a8+ident*0x30,0x30)
                    group_id=struct.unpack_from('<I',item,0x24)[0]
                    if group_id>0x64:raise ValueError('resource group outside original bounded registry')
                    group=save(self.g,label+'-group',0xa02942798+group_id*0x28,0x28)
                    address,second,length=struct.unpack_from('<QQI',group)
                    row.update(resource_id=hex(ident),group_id=hex(group_id),
                        returned_value=regs['X00']&0xffffffff,item_hex=item.hex(),group_hex=group.hex(),
                        source_address=hex(address),secondary_address=hex(second),source_bytes=length)
                    # Only bounded identity-mapped ROM reads. Preserve metadata
                    # if this resource uses another storage class; never infer
                    # a missing trailer or silently cross a mapped boundary.
                    if 16<=length<=0x8000000 and 0x40000000<=address<=0x48000000-length:
                        row['source_head_hex']=self.g.read_rom_bytes(address,16).hex()
                        row['source_tail_hex']=self.g.read_rom_bytes(address+length-16,16).hex()
            if row['name']=='ui_component_request':
                row['request_code']=hex(regs['X01']&0xffffffff)
                row['previous_worker_hex']=save(self.g,'zr-ui-previous-worker',0xa0343b8b8,8).hex()
            if row['name'].startswith('ui_view_'):
                raw=save(self.g,'zr-ui-view-selector',0xa03537c00,4)
                selector=struct.unpack('<I',raw)[0]
                row['previous_selector']=selector
                if selector<=0x24:
                    slot=save(self.g,'zr-ui-view-slot',0xa03537ad8+selector*8,8)
                    obj=struct.unpack('<Q',slot)[0]
                    row['selected_object']=hex(obj)
                    if 0xa00000000<=obj<=0xa40000000-0x50:
                        row['view_hex']=save(self.g,'zr-ui-selected-view',obj,0x50).hex()
            if row['name']=='ui_selected_view_message' and 0xa00000000<=regs['X00']<=0xa40000000-0x50:
                row['view_hex']=save(self.g,'zr-ui-selected-view-message',regs['X00'],0x50).hex()
            if row['name']=='ui_popup_child_call':
                row['child_hex']=save(self.g,'zr-ui-popup-child',regs['X22'],0xc8).hex()
                callback=regs['X08']
                if not 0x40160000<=callback<0x41490000 or callback&3:
                    raise ValueError('popup child callback outside original executable prefix')
                row['actual_callback']=hex(callback)
                if callback not in self.points:
                    self.points[callback]='ui_popup_actual_child_callback'
                    self.g.rsp(f'Z1,{callback:x},4')
            if row['name']=='ui_popup_actual_child_callback':
                row['child_hex']=save(self.g,'zr-ui-popup-callback-object',regs['X00'],0xc8).hex()
            if row['name']=='ui_popup_request' and 0xa00000000<=regs['X00']<=0xa40000000-0x130:
                self.ui_popup_calls+=1
                row['call_number']=self.ui_popup_calls
                label=f'zr-ui-popup-{self.ui_popup_calls:02d}'
                row['object_hex']=save(self.g,label+'-object',regs['X00'],0x130).hex()
                row['stack_hex']=save(self.g,label+'-stack',regs['SP'],
                    min(0x400,0x1000-(regs['SP']&0xfff))).hex()
                if (self.g.data.get('diagnostic_mode_key_input') and
                        self.g.data.get('mode_start_gate','photo-modal')=='photo-modal' and
                        not self.g.data.get('mode_key_input_gate') and regs['X30']==0x403e0e28):
                    stack=bytes.fromhex(row['stack_hex'])
                    if len(stack)>=0x1a0 and struct.unpack_from('<Q',stack,0x170)[0]==0x40 and struct.unpack_from('<Q',stack,0x188)[0]==0xd6:
                        self.g.data['mode_key_input_gate']=dict(classification='host UI observation gate',
                            original_modal_index='0x40',original_message='0xd6',guest_state_modified=False)
                        if 0x40f398f8 in self.points:raise ValueError('initial key consumer must retire before mode waveform')
                        self.points[0x40f398f8]='ui_mode_key_consumer'
                        self.g.rsp('Z1,40f398f8,4')
                        if self.g.data.get('trace_mode_key_dispatch'):
                            for address,name in ((0x40f396e0,'ui_mode_key_diff_callback'),
                                                 (0x40f6bff0,'ui_mode_key_selected_callback'),
                                                 (0x40413418,'ui_mode_key_handler')):
                                if address in self.points:raise ValueError('mode dispatch observation collision')
                                self.points[address]=name
                                self.g.rsp(f'Z1,{address:x},4')
                        if self.g.data.get('trace_mode_view_dispatch'):
                            if 0x40412d5c in self.points:raise ValueError('initial view dispatch collision')
                            self.points[0x40412d5c]='ui_mode_view_dispatch';self.g.rsp('Z1,40412d5c,4')
                from capture_zr_ui_flow import capture as capture_ui
                # Full membership storage once, then only the group selector.
                # Repeated deep reads consumed the host observation window in134.
                row['collection']=capture_ui(self.g,label+'-collection',elements=self.ui_popup_calls==1)
                if self.ui_popup_calls<8:
                    return_pc=regs['X30']
                    if not 0x40160000<=return_pc<0x41490000 or return_pc&3:
                        raise ValueError('popup observation requires bounded original return')
                    if return_pc not in self.points:
                        self.points[return_pc]='ui_popup_request_return'
                        self.g.rsp(f'Z1,{return_pc:x},4')
            if row['name']=='ui_popup_request_return':
                row['call_number']=self.ui_popup_calls
                self.points[0x40406034]='ui_popup_request'
                self.g.rsp('Z1,40406034,4')
            if row['name']=='ui_collection_select':
                self.ui_collection_calls+=1
                row.update(call_number=self.ui_collection_calls,requested_key=regs['X00']&0xffffffff)
                from capture_zr_ui_flow import capture as capture_ui
                row['previous_collection']=capture_ui(self.g,f'zr-ui-collection-before-{self.ui_collection_calls:02d}')
                self.points[0x40439404]='ui_collection_select_return'
                self.g.rsp('Z1,40439404,4')
            if row['name']=='ui_collection_select_return':
                from capture_zr_ui_flow import capture as capture_ui
                row.update(call_number=self.ui_collection_calls,
                    collection=capture_ui(self.g,f'zr-ui-collection-after-{self.ui_collection_calls:02d}'))
                if self.ui_collection_calls<16:
                    self.points[0x404393bc]='ui_collection_select'
                    self.g.rsp('Z1,404393bc,4')
            if row['name']=='ui_state_notification':
                self.ui_notifications+=1
                row['call_number']=self.ui_notifications
                row['payload_hex']=save(self.g,'zr-ui-state-notification',regs['X03'],8).hex()
                row['worker_hex']=save(self.g,'zr-ui-state-worker',regs['X01'],0x130).hex()
                if self.ui_notifications<16:
                    return_pc=regs['X30']
                    if not 0x40160000<=return_pc<0x41490000 or return_pc&3:
                        raise ValueError('UI state notification requires bounded original return')
                    if return_pc not in self.points:
                        self.points[return_pc]='ui_state_notification_return'
                        self.g.rsp(f'Z1,{return_pc:x},4')
            if row['name']=='ui_state_notification_return':
                self.points[0x4039dcac]='ui_state_notification'
                self.g.rsp('Z1,4039dcac,4')
            if row['name'].startswith('ui_worker_'):
                row['worker_hex']=save(self.g,'zr-'+row['name']+'-object',0xa02835730,0xd0).hex()
                row['stack_hex']=save(self.g,'zr-'+row['name']+'-stack',regs['SP'],
                    min(0x180,0x1000-(regs['SP']&0xfff))).hex()
            if row['name'] in ('boot_ui_ready_message','boot_capture_ready_message'):
                row['payload_hex']=save(self.g,'zr-'+row['name'],regs['X20'],0x30).hex()
                row['message_hex']=save(self.g,'zr-'+row['name']+'-message',regs['X23'],0x70).hex()
                row['parent_hex']=save(self.g,'zr-'+row['name']+'-parent',regs['X21'],0x748).hex()
            if row['name']=='app_entry_ready_comparison':
                row.update(actual_mask=regs['X20']&0xffffffff,required_mask=regs['X00']&0xffffffff,
                           object_hex=save(self.g,'zr-entry-ready-state',regs['X19'],0x290).hex())
            if row['name']=='app_state_transition':
                self.transitions+=1
                raw=save(self.g,'zr-app-transition-parent',regs['X00'],0x748)
                row.update(parent_hex=raw.hex(),
                    call_number=self.transitions,
                    previous_state=struct.unpack_from('<I',raw,0x2d0)[0],
                    requested_state=regs['X01']&0xffffffff,
                    argument=regs['X02']&0xffffffff,detail=regs['X03'])
                requested=row['requested_state']
                if requested<=8:
                    table=self.g.read_rom_bytes(0x42bc00d8+requested*8,8)
                    obj=struct.unpack('<Q',table)[0]
                    state=save(self.g,'zr-selected-app-state',obj,0x290)
                    entry=struct.unpack_from('<Q',state,8)[0]
                    row.update(selected_object=hex(obj),selected_entry=hex(entry),state_hex=state.hex())
                    if not 0x40160000<=entry<0x41490000 or entry&3:
                        raise ValueError('selected original app entry outside executable prefix')
                    if entry not in self.points:
                        self.points[entry]='app_selected_state_entry'
                        self.g.rsp(f'Z1,{entry:x},4')
                if 0x40f6a650 not in self.points:
                    self.points[0x40f6a650]='app_state_transition_return'
                    self.g.rsp('Z1,40f6a650,4')
            if row['name']=='app_state_transition_return':
                raw=save(self.g,f'zr-{self.capture_phase}-app-transition-return-{self.transitions:02d}',
                         regs['X21'],0x748)
                row.update(call_number=self.transitions,parent_hex=raw.hex(),
                    current_state=struct.unpack_from('<I',raw,0x2d0)[0],
                    previous_state=struct.unpack_from('<I',raw,0x2d4)[0])
                if self.transitions<16:
                    self.points[0x40f6a5d0]='app_state_transition'
                    self.g.rsp('Z1,40f6a5d0,4')
            if row['name']=='app_ui_message':
                row['message']=hex(regs['X01']&0xffffffff)
                row['payload_hex']=save(self.g,'zr-app-ui-message',regs['X04'],
                    min(0x70,0x1000-(regs['X04']&0xfff))).hex()
                row['parent_hex']=save(self.g,'zr-app-ui-message-parent',regs['X00'],0x748).hex()
            if row['name']=='battery_manager_callback':
                row['payload_hex']=save(self.g,'zr-battery-manager-input',regs['X01'],0x94).hex()
                row['actual_callback']=hex(regs['X08'])
            if row['name']=='app_original_dispatch':
                self.dispatches+=1
                row['call_number']=self.dispatches
                row['parent_hex']=save(self.g,'zr-app-dispatch-parent',regs['X00'],0x740).hex()
                # A task stack can end before the next virtual page. Read
                # a translated in-page prefix, never its guard page.
                row['stack_hex']=save(self.g,'zr-app-dispatch-stack',regs['SP'],
                    min(0x180,0x1000-(regs['SP']&0xfff))).hex()
                if 0xa00000000 <= regs['X03'] <= 0xa40000000-0x30:
                    row['argument_hex']=save(self.g,'zr-app-dispatch-argument',regs['X03'],0x30).hex()
                if self.dispatches<16:
                    return_pc=regs['X30']
                    if not 0x40160000<=return_pc<0x41490000 or return_pc&3:
                        raise ValueError('bounded original dispatcher return required')
                    if return_pc not in self.points:
                        self.points[return_pc]='app_dispatch_return'
                        self.g.rsp(f'Z1,{return_pc:x},4')
            if row['name']=='app_dispatch_return':
                raw=save(self.g,f'zr-{self.capture_phase}-app-dispatch-return-{self.dispatches:02d}',
                         0xa0282f4b8,0x748)
                row.update(parent_hex=raw.hex(),current_state=struct.unpack_from('<I',raw,0x2d0)[0])
                self.points[0x40f6f5a8]='app_original_dispatch'
                self.g.rsp('Z1,40f6f5a8,4')
            if row['name'] in ('app_state_entry_candidate','app_selected_state_entry'):
                row['object_hex']=save(self.g,'zr-app-entry-object',regs['X00'],0x290).hex()
            if row['name']=='inline_path_producer':
                raw=save(self.g,'zr-inline-path-object',regs['X00'],0x80)
                row.update(datatype=struct.unpack_from('<I',raw,8)[0],
                    segments=struct.unpack_from('<I',raw,0x14)[0],
                    coordinates=struct.unpack_from('<I',raw,0x18)[0])
            if row['name']=='dsi_display_on_callback_returned':
                self.points[0x40eb11a0]='display_post_on_bus_wait'
                self.g.rsp('Z1,40eb11a0,4')
            if row['name']=='display_post_on_bus_wait':
                row['event_wrapper_hex']=save(self.g,'zr-display-bus-wait-wrapper',regs['X00'],0x30).hex()
                save(self.g,'zr-display-bus-descriptors',0xa02814bb0,15*0x28)
                # Task stacks can end at an unmapped guard page. Stay in
                # the current mapped page; do not remove or cross that guard.
                size=min(0x300,0x1000-(regs['SP']&0xfff))
                save(self.g,'zr-display-bus-request-stack',regs['SP'],size)
                row['stack_capture_bytes']=size
            if row['name'] in ('ui_display_message','ui_display_wait'):
                row['argument_hex']=save(self.g,'zr-'+row['name'],regs['X00'],0x38).hex()
            if row['name']=='sequence_wait_argument':
                row['event_wrapper_hex']=save(self.g,'zr-sequence-event-wrapper',regs['X00'],0x80).hex()
                save(self.g,'zr-resource-registry-at-wait',0xa029414a8,101*0x30)
                save(self.g,'zr-resource-groups-at-wait',0xa02942798,0x900)
            if row['name']=='sequence_wait_failure':
                row['stack_hex']=save(self.g,'zr-sequence-wait-failure-stack',regs['SP'],0x100).hex()
            if row['name']=='sequence_failure_event':
                row['payload_hex']=save(self.g,'zr-sequence-failure-event',regs['X01'],12).hex()
            if row['name']=='display_parameter_source' and cpu==0:
                address=regs['X00']
                if 0xa00000000 <= address < 0xa40000000-0x1000:
                    raw=save(self.g,'zr-display-parameter-source',address,0x1000)
                    row['source_capture_bytes']=len(raw)
                    row['source_nonzero_bytes']=sum(b!=0 for b in raw)
                    save(self.g,'zr-resource-registry-early',0xa029414a8,101*0x30)
                    save(self.g,'zr-resource-groups-early',0xa02942798,0x900)
                elif 0x40000000 <= address <= 0x48000000-0x700:
                    raw=self.g.read_rom_bytes(address,0x700)
                    (self.g.out/'zr-display-parameter-source.bin').write_bytes(raw)
                    row['source_capture_bytes']=len(raw)
                    row['source_nonzero_bytes']=sum(b!=0 for b in raw)
                    row['source_sha256']=__import__('hashlib').sha256(raw).hexdigest()
            if row['name']=='display_parameter_converted' and cpu==0:
                block=save(self.g,'zr-display-parameter-converted',regs['X19'],0xeac)
                row['bytes']=len(block)
                if 'display_parameter_rom_input' in self.g.data:
                    reference=(self.g.out/'zr-display-hardware-object.bin').read_bytes()
                    spans=self.g.data['display_parameter_rom_input']['spans']
                    differences=[]
                    for span in spans:
                        offset=int(span['object_offset'],0)
                        for i in range(span['bytes']):
                            if block[offset+i]!=reference[offset+i]:differences.append(hex(offset+i))
                    row['hardware_reference_differences']=differences
                    row['native_mapped_fields_match_hardware_reference']=not differences
            if row['name'] in ('dsi_orientation_argument','dsi_display_on_argument') and cpu==0:
                row['argument_hex']=save(self.g,row['name'],regs['X00'],0x40).hex()
            if row['name'].startswith('key_consumer_candidate') and 0xa00000000 <= regs['X00'] < 0xa40000000-52:
                row['argument_hex']=save(self.g,'startup-'+row['name'],regs['X00'],52).hex()
            if row['name']=='app_boot_notice':
                # ZR native getters 40f6a968/974/980 use object+2c8.
                # Capture the actual argument and pointer without assuming
                # Z9's AppMain global, state offset or enumeration layout.
                raw=save(self.g,'zr-app-object',regs['X00'],0x740)
                pointer=struct.unpack_from('<Q',raw,0x2c8)[0]
                row['state_pointer']=hex(pointer)
                if 0xa00000000 <= pointer < 0xa40000000-0x200:
                    row['state_capture_hex']=save(self.g,'zr-app-state',pointer,0x200).hex()
            if row['name']=='dsi_command_argument':
                self.dsi_calls+=1
                row['call_number']=self.dsi_calls
                address=regs['X00']
                capture=self.dsi_calls==1 or self.dsi_calls>=61
                if capture and 0xa00000000 <= address < 0xa40000000-0x40:
                    label='zr-dsi-command-argument' if self.dsi_calls==1 else f'zr-dsi-command-{self.dsi_calls:03d}'
                    row['argument_hex']=save(self.g,label,address,0x40).hex()
                    if self.dsi_calls==1 and regs['X30']==0x402e3880 and regs['X01']==3 and regs['X02']==1:
                        # 402e3878 derives this command list from the actual
                        # registered display parameter object plus 0x9fc.
                        row['parameter_object']=hex(address-0x9fc)
                        block=save(self.g,'zr-display-parameters',address-0x9fc,0x1200)
                        row['parameter_bytes']=len(block)
                        # Native 40f87664/648 encode these distinct ZR bases
                        # and strides. No Z9 global address is inherited.
                        save(self.g,'zr-resource-registry',0xa029414a8,101*0x30)
                        save(self.g,'zr-resource-groups',0xa02942798,0x900)
                elif capture:
                    from probe_zr_boot import MAIN, MAIN_BYTES, ENTRY
                    if ENTRY <= address < ENTRY+MAIN_BYTES-0x40:
                        row['translation']=self.g.qmp.hmp(f'gva2gpa {address:#x}',0)
                        if row['translation'].strip()!=f'gpa: {address:#x}':
                            raise ValueError('original ROM observation requires identity translation')
                        raw=super(type(self.g),self.g).read_bytes(address,0x40)
                        (self.g.out/'zr-dsi-command-argument.bin').write_bytes(raw)
                        row['argument_hex']=raw.hex()
            self.record['stops'].append(row)
            hits.append(pc)
        for pc in set(hits):
            self.g.rsp(f'z1,{pc:x},4');del self.points[pc]
        self.record['remaining']={hex(k):v for k,v in self.points.items()}
        return bool(hits)

    def begin_capture_recovery(self,phase='capture'):
        """Reuse the pinned application group after startup's one-shot reads.

        Keep pending entry/return pairs and their existing owners intact.
        No guest data is written; debugger stops still add observation overhead.
        """
        names=('capture_controller_', 'capture_completion_', 'capture_begin_',
               'capture_late_', 'capture_status_', 'front_prepare_',
               'front_submit_', 'front_pipeline_', 'front_followup_',
               'device_snapshot_', 'fault_')
        extra={'app_capture_transition_result','capture_ready_event',
               'app_state_entry_candidate','app_original_dispatch','app_state_transition','app_ui_message',
               'fault_reason9_report','fault_list_append','sequence_flow_watchdog_expired'}
        armed={pc:name for pc,name in POINTS.items() if name.startswith(names) or name in extra}
        if phase=='capture' and self.g.data.get('probe_arguments',{}).get('capture_raw_pipeline'):
            armed[0x40e0db90]='capture151_isr_after_w1c'
            if self.g.data.get('mode_burst_min_frames'):
                self.g.data['capture_source_boundary_waits']=0
                armed[0x412aab64]='primary_source_boundary_wait'
                armed[0x412aab68]='primary_source_boundary_wait_return'
        added={}
        for pc,name in armed.items():
            if pc not in self.points:
                self.points[pc]=name;self.g.rsp(f'Z1,{pc:x},4');added[hex(pc)]=name
        self.capture_phase=phase
        self.record.setdefault('capture_phase_rearms',[]).append(dict(points=added,phase=phase,
            scope='bounded original application and capture lifecycle observations only'))

    def close(self):
        for pc in self.points:self.g.rsp(f'z1,{pc:x},4')
        self.points.clear()
