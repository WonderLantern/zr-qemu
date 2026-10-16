# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded external key states for the pinned ZR decoder and native UI.

These are synthetic MCU inputs, not verified electrical wiring. Consumption
requires a fresh original view dispatch and its return; no guest state writes.
"""
import struct


KEYS = {
    'menu': (67, 1, 0x8000), 'fn2': (60, 2, 0x4000),
    # Original337 names body0e/word0 bit11 ID_SW0_EXP_MODE. Synthetic
    # logical mode input; does not assert a physical dedicated ZR button.
    'exp-mode': (14, 0, 0x800),
    # Pinned original decoder/name table: body10 -> ID_SW1_RELEASE_MODE.
    # This exposes the native release-mode UI; it does not set burst state.
    'release-mode': (16, 1, 0x08000000),
    'i': (72, 1, 0x400),  # Original ID_SW1_I; native menu selection checked separately.
    'left': (35, 0, 0x40), 'right': (34, 0, 0x80),
    'up': (36, 0, 0x20), 'down': (37, 0, 0x10),
    'center': (42, 0, 0x8000),
    'half': (7, 0, 0x80000000),
    'full': (8, 0, 0x40000000),
    # Original decoder/name-table checks: zr-video-key-decoder-200.json.
    'movie': (9, 1, 0x2000), 'liveview': (88, 1, 0x10),
}
RELEASED = dict(switches=[0x200, 0, 0], dials=[0, 0, 0, 0])
# Whole original-decoder basis map: zr-complete-input-map-337.json.
# These are byte/enum candidates; names do not assert physical switch roles.
SELECTOR_FIELDS = {
    0x0f: 0x20, 0x11: 0x22, 0x19: 0x2a,
    0x36: 0x28, 0x57: 0x26, 0x59: 0x2c, 0x5a: 0x2e, 0x5b: 0x30,
}
SELECTORS = {f'selector{offset:02x}-{label}': (offset,value)
             for offset in SELECTOR_FIELDS for label,value in (('off',0),('on',1),('two',2))}
# Full native audio-menu navigation plus two recording/recovery cycles.
# This is a host recipe bound; it does not change any guest input semantics.
MAX_KEYS = 128


def consumer_rows(data):
    return [row for key,observer in data.items() if key.endswith('observer')
            for row in observer.get('stops',[]) if row['name'] in
            ('ui_mode_key_consumer','ui_mode_key_consumer_return')]


def consumer_watermark(data):
    return max((row['call_number'] for row in consumer_rows(data)),default=0)


def consumed_by_native_key(states,index,rows,*,after_call):
    """Confirm a fresh complete original key receiver, including submenus.

    This proves delivery and return, not UI selection or image completion.
    The pinned ZR parsed structure is13 words; these bounded button-only
    states have three actual switch words and explicitly retained selectors.
    Nonzero dial inputs remain outside this explicitly checked contract.
    """
    state=states[index]
    if any(state['dials']):raise ValueError('Native consumer pacing supports button-only states')
    expected=bytearray(struct.pack('<3I',*state['switches'])+bytes(40))
    # The pinned complete decoder basis map supplies these byte-to-halfword
    # fields. Retained selectors are part of the exact receipt, including
    # states whose three button words have not changed.
    body=bytes.fromhex(state['body_hex'])
    for offset, parsed_offset in SELECTOR_FIELDS.items():
        struct.pack_into('<H',expected,parsed_offset,body[offset])
    returned={row['call_number']:row for row in rows if row['name']=='ui_mode_key_consumer_return'}
    for row in rows:
        if row['name']!='ui_mode_key_consumer':continue
        number=row['call_number']
        if number<=after_call or number not in returned:continue
        if bytes.fromhex(row['parsed_status_hex'])==expected:
            return dict(kind='original-key-consumer-return',sequence_id=state['sequence_id'],
                call_number=number,handler_pc=row['pc'],pc=returned[number]['pc'],
                parsed_status_hex=row['parsed_status_hex'],
                scope='original button input consumed and returned; UI/file validation separate')
    return None


def parse_keys(text):
    keys = [part.strip() for part in text.split(',')]
    allowed=KEYS.keys() | SELECTORS.keys()
    if not 1 <= len(keys) <= MAX_KEYS or any(key not in allowed for key in keys):
        raise ValueError('1..'+str(MAX_KEYS)+' comma-separated keys required: '+','.join(sorted(allowed)))
    return keys


def parse_initial_selectors(text):
    """Explicit bounded external enum bytes, independent of button edges."""
    if text is None:return {}
    selectors={}
    for pair in text.split(','):
        try:
            field,value=pair.split(':')
            field=int(field.strip(),16);value=int(value.strip(),0)
        except (ValueError,AttributeError):
            raise ValueError('initial selectors require hex-field:enum pairs') from None
        if field not in SELECTOR_FIELDS or field in selectors or value not in (0,1,2):
            raise ValueError('unique pinned selector fields and enum values0..2 required')
        selectors[field]=value
    return selectors


def input_states(keys, *, continuous_shutter=False, initial_selectors=None):
    states = []
    if continuous_shutter:
        full=[i for i,key in enumerate(keys) if key=='full']
        if not 1<=len(full)<=8 or any(i==0 or i+1>=len(keys) or
                keys[i-1:i+2]!=['half','full','half'] for i in full):
            raise ValueError('continuous shutter requires 1..8 separate half/full/half sequences')
        held_indices={i for position in full for i in (position-1,position)}
    selectors = dict.fromkeys(SELECTOR_FIELDS, 0)
    if initial_selectors is not None:
        if not isinstance(initial_selectors,dict) or any(
                type(field) is not int or field not in SELECTOR_FIELDS or
                type(value) is not int or value not in (0,1,2)
                for field,value in initial_selectors.items()):
            raise ValueError('initial selectors require pinned integer fields and enum values0..2')
        selectors.update(initial_selectors)
    for index, key in enumerate(keys):
        if key in SELECTORS:
            offset,value=SELECTORS[key];selectors[offset]=value
            for suffix in ('set','held'):
                body=bytearray(124);body[0]=body[4]=1
                for offset,value in selectors.items():body[offset]=value
                states.append(dict(sequence_id=len(states)+1,key_index=index,key=key,
                    label=key+'-'+suffix,body_hex=body.hex(),
                    switches=list(RELEASED['switches']),dials=[0,0,0,0]))
            continue
        offset, group, mask = KEYS[key]
        for pressed in (True, False):
            body = bytearray(124)
            body[0] = body[4] = 1
            for selector_offset,value in selectors.items():body[selector_offset]=value
            switches = list(RELEASED['switches'])
            if pressed:
                body[offset] = 1
                switches[group] |= mask
                if key == 'full':
                    # A fully pressed shutter also holds the half contact.
                    body[7] = 1
                    switches[0] |= 0x80000000
            label=key+('-press' if pressed else '-release')
            held=(continuous_shutter and not pressed and index in held_indices)
            if held:
                # Reuse the physical0->half->full+half->half->0 sequence
                # already accepted on Z9, with this model's parsed structure.
                # Never drop and raise HALF together with the FULL edge.
                body[7]=1;switches[0]|=0x80000000
                if key=='half':label='half-held-before-full'
            states.append(dict(sequence_id=len(states)+1, key_index=index, key=key,
                label=label, body_hex=body.hex(),
                switches=switches, dials=[0, 0, 0, 0],half_held=bool(held)))
    return states


def recording_shutter_presses(states):
    """Check full contact travel and return the FULL press state indices.

    A recording input is a physical button press, not a MOVIE alias. These
    checks describe external inputs only; native START/STOP and files must
    still be observed independently. Duplicate HALF states are intentional
    because every bounded key has a press and release receipt.
    """
    contacts = []
    full = []
    for index, state in enumerate(states):
        body = bytes.fromhex(state['body_hex'])
        if len(body) != 124 or body[7] not in (0, 1) or body[8] not in (0, 1):
            raise ValueError('Complete binary shutter contact input required')
        half_on, full_on = body[7], body[8]
        expected = (half_on << 31) | (full_on << 30)
        if state['switches'][0] & 0xc0000000 != expected:
            raise ValueError('Shutter body and parsed contact bits disagree')
        if state['key'] == 'movie' or body[9] or state['switches'][1] & 0x2000:
            raise ValueError('Recording shutter cannot use the MOVIE alias')
        if full_on:
            if not half_on or state['label'] != 'full-press':
                raise ValueError('FULL requires the held HALF contact')
            full.append(index)
        contacts.append((half_on, full_on))
    if not full or len(full) % 2 or len(full) > 8:
        raise ValueError('Recording requires 1..4 paired full shutter presses')
    expected_travel = [(1, 0), (1, 0), (1, 1), (1, 0), (1, 0), (0, 0)]
    for index in full:
        if (index < 2 or contacts[index-2:index+4] != expected_travel or
                (index > 2 and contacts[index-3] != (0, 0))):
            raise ValueError('Recording shutter must travel released/HALF/FULL/HALF/released')
    return full


def consumed(states, index, rows, *, after_call, after_menu_call=None):
    """Find a completed view call newer than this state's enqueue watermark.

    A repeated press/release must not reuse a historical matching key state.
    Only the original switch difference and dial words count as consumption.
    """
    previous = states[index]
    before = states[index-1] if index else RELEASED
    expected = tuple((now, old, now ^ old, now & ~old, old & ~now)
                     for now, old in zip(previous['switches'], before['switches']))
    returns = {row['call_number']: row for row in rows if row['name'] == 'ui_mode_view_return'}
    for row in rows:
        if row['name'] != 'ui_mode_view_dispatch':
            continue
        number = row['call_number']
        if number <= after_call or number not in returns:
            continue
        raw = bytes.fromhex(row['normalized_key_hex'])
        if len(raw) != 0x198:
            raise ValueError('complete pinned normalized key snapshot required')
        if (all(struct.unpack_from('<5I', raw, 8+i*20) == words for i, words in enumerate(expected))
                and struct.unpack_from('<4i', raw, 0x58) == tuple(previous['dials'])):
            return dict(kind='original-view-return', sequence_id=previous['sequence_id'],
                pc=returns[number]['pc'], call_number=number,
                normalized_key_hex=row['normalized_key_hex'])
    # The native menu handler replaces APPLv kind3 consumption. Enable this
    # separate body-completed gate only after the observed native menu screen.
    if after_menu_call is not None:
        returns={row['call_number']:row for row in rows if row['name']=='ui_menu_key_handler_return'}
        for row in rows:
            if row['name']!='ui_menu_key_handler':continue
            number=row['call_number']
            if number<=after_menu_call or number not in returns:continue
            raw=bytes.fromhex(row['diff_hex'])
            if len(raw)!=0x190:raise ValueError('complete original menu key difference required')
            if (all(struct.unpack_from('<5I',raw,8+i*20)==words for i,words in enumerate(expected)) and
                    struct.unpack_from('<4i',raw,0x58)==tuple(previous['dials'])):
                return dict(kind='original-menu-handler-return',sequence_id=previous['sequence_id'],
                    pc=returns[number]['pc'],call_number=number,handler_pc=row['pc'],
                    original_caller=row['original_caller'],normalized_key_hex=row['diff_hex'])
    return None


def view_rows(data):
    return [row for key, observer in data.items() if key.endswith('observer')
            for row in observer.get('stops', [])
            if row['name'] in ('ui_mode_view_dispatch', 'ui_mode_view_return',
                               'ui_menu_key_handler','ui_menu_key_handler_return')]


def watermark(data):
    return max((row['call_number'] for row in view_rows(data)
                if row['name'].startswith('ui_mode_view_')), default=0)


def menu_watermark(data):
    return max((row['call_number'] for row in view_rows(data)
                if row['name'].startswith('ui_menu_key_handler')),default=0)


def parse_focus_gates(text,state_count):
    gates={}
    for pair in text.split(','):
        try:stage,row=(int(x) for x in pair.split(':'))
        except ValueError:raise ValueError('focus gates require state:visible-row pairs')
        if not 1<=stage<state_count or stage%2 or not 0<=row<=6 or stage in gates:
            raise ValueError('unique interior release states and visible rows0..6 required')
        gates[stage]=row
    return gates


def menu_focus_matches(raw,row):
    header=b'P6\n1280 800\n255\n'
    if not raw.startswith(header) or len(raw)!=len(header)+1280*800*3:
        raise ValueError('complete native 1280x800 RGB PPM required')
    y=144+96*row;pixels=memoryview(raw)[len(header):]
    # Compare the plain band at the right side, away from text/value glyphs.
    colors=[pixels[(y*1280+x)*3:(y*1280+x)*3+3] for x in range(1170,1190,2)]
    # The original menu also highlights disabled rows: run168 has the darker
    # yellow (147,128,45), whereas run162 has (246,215,80). It does not skip
    # a disabled row. Match chroma and contrast, without interpreting the
    # row's enabled state or changing the guest selection.
    return sum(c[0]>100 and c[1]>90 and c[2]<120 and
               c[0]>c[1] and c[1]>2*c[2] for c in colors)>=8


def menu_tab_matches(raw,tab):
    """Observe the native tab background, away from the icon strokes."""
    if not 0<=tab<=6:raise ValueError('native menu tab0..6 required')
    header=b'P6\n1280 800\n255\n'
    if not raw.startswith(header) or len(raw)!=len(header)+1280*800*3:
        raise ValueError('complete native 1280x800 RGB PPM required')
    pixels=memoryview(raw)[len(header):];y=60+112*tab
    colors=[pixels[(y*1280+x)*3:(y*1280+x)*3+3] for x in range(52,68,2)]
    return all(c[0]>100 and c[1]>90 and c[2]<120 and
               c[0]>c[1] and c[1]>2*c[2] for c in colors)
