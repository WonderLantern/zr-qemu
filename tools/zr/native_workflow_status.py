# SPDX-License-Identifier: GPL-2.0-or-later
"""Retain original faults in native output; file qualification is separate."""
def native_fault_observations(data):
    """Retain native faults even when optional exception capture failed."""
    names={'sequence_flow_watchdog_expired','fault_reason9_report',
           'fault_list_append','fault_cpu_exception_context'}
    fields=('name','pc','failure_mask','fault_code','producer_return',
            'context_address','context_bytes','context_capture_error')
    observations=[]
    for phase,record in data.items():
        if not phase.endswith('observer') or not isinstance(record,dict):continue
        rows=record.get('stops',[])
        if not isinstance(rows,list):continue
        for row in rows:
            if isinstance(row,dict) and row.get('name') in names:
                observations.append(dict(phase=phase,**{k:row[k] for k in fields if k in row}))
    for row in data.get('fault_capture_failures',[]):
        if (isinstance(row,dict) and row.get('name')=='fault_cpu_exception_context'
                and row.get('context_capture_error') and not any(
                    old.get('name')==row['name'] and old.get('pc')==row.get('pc')
                    for old in observations)):
            observations.append(dict(phase='fault_capture_failures',
                **{k:row[k] for k in fields if k in row}))
    return observations
