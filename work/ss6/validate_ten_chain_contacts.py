#!/usr/bin/env python3
"""Run the four selectable fighters' CCD finishers, then compare each contact to the Japanese ELF."""
import argparse
from hashlib import sha256
import json
from itertools import groupby

from inspect_iso import Elf
from validate_nakoruru_combat import ACTORS, ELF, MixedContactOracle
from validate_selected_combat import BUILD, OUT, SOURCE, prefix
from validate_stage01_session import trace

# The first C is an edge after the opener connects. Every fighter's ACT has
# its own hitstop and cancel window; Nakoruru's final ACT hits three times.
EDGES = ((15, 31, 52), (18, 34, 52), (15, 31, 52), (15, 31, 47))
FINISH = ((63,), (56, 73, 64), (64,), (62,))


class TenContacts(MixedContactOracle):
    def __init__(self, roster, attacker):
        super().__init__(roster)
        self.attacker = attacker

    def install_player(self, row, slot):
        super().install_player(row, slot)
        self.probe.write(ACTORS + slot * 0xf2c + 0x10c, 3 if slot == self.attacker else 5, 4)


def case(assets, side, character, opponent, mode):
    def pair(own, other=0):
        return (other, own) if side else (own, other)

    lineup = pair(character, opponent)
    pad = prefix(lineup)
    for tick in (211, 225):
        pad[tick-1][side] = 64
    if mode == 'ko':
        # Deplete the sword gauge and HP through the regular pad path. The
        # 13th close heavy leaves Haohmaru at 9 HP, exactly 3 before the kick.
        pad += ([(128, 64)] * 44 + [pair(1024)] + [(0, 0)] * 90) * 13
    pad += [(128, 64)] * 43 + [(0, 0)] * 8
    start = len(pad)
    edges = (15, 24, 35) if mode == 'air-whiff' else EDGES[character]
    sequence = dict(zip((0, *edges), (768, 1024, 1024, 2048)))
    for tick in range(1150 if mode == 'ko' else 300):
        defend = 32 if mode == 'crouch' else 0
        if mode == 'guard' and tick < 80:
            defend = (128, 64)[side]
        elif mode == 'air-whiff' and tick == 6:
            defend = 16
        pad.append(pair(sequence.get(tick, 0), defend))

    rows = trace(assets, pad, '--contact-fields')
    assert len(rows) == len(pad)
    a, b = 3 + 10 * side, 3 + 10 * (1 - side)
    # At KO the round system resets contact counters and HP for the next
    # round. Resolve the Japanese routine through the final contact itself.
    end = next((i+1 for i in range(start, len(rows)) if rows[i][b+6] == '0'), len(rows))
    original = TenContacts(lineup, side)
    events = original.contacts(rows[start-6:end], side)
    attack_states = [int(state) for state, _ in groupby(row[a+1] for row in rows[start:end] if row[a] == '1')]
    reached = 49 in attack_states
    offset = int(rows[start][0])
    finisher = [event for event in events if rows[start+event['frame']-offset][a+2] == '252']
    if mode == 'guard':
        assert not reached and len(events) == 1 and events[0]['defense'] == 1
    elif mode == 'air-whiff':
        assert reached and len(events) == 1 and events[0]['target_state'] == 74 and not finisher
    else:
        assert attack_states == [39, 40, 47, 48, 49], (lineup, mode, attack_states)
        assert len(events) == 3 + len(FINISH[character])
        assert tuple(e['target_state'] for e in finisher) == FINISH[character]
        if character == 3:
            kick = finisher[0]
            assert (kick['frame']-offset, kick['raw'], kick['target_state']) == (56, 21, 62)
            assert rows[start+56][b:b+3] == ['2', '62', '380']
    if mode == 'ko':
        assert rows[start+55][b+6] == '3' and rows[end-1][b+6] == '0'
        assert any(row[1] == '8' and row[a+9] == '1' for row in rows[end:])
        assert any(row[1] == '4' and row[a+9] == '1' and row[b+6] == '200' for row in rows[end:])
    elif mode != 'crouch':
        assert rows[-1][a:a+3] == rows[-1][b:b+3] == ['0', '0', '0']
    return dict(lineup=lineup, seat=side+1, mode=mode, input_edges=sequence, events=events,
                attack_states=attack_states, ending_hp=int(rows[end-1][b+6]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', action='store_true')
    args = parser.parse_args()
    assets = OUT/'native-viewer/assets' if args.package else SOURCE
    elf = ELF.read_bytes()
    at = Elf(elf).offset(0x4d7f38 + 21*24)
    assert elf[at:at+24] == bytes([62])*24
    cases = []
    for side in (0, 1):
        cases.extend(case(assets, side, who, other, 'standing')
                     for who in range(4) for other in (range(4) if who == 3 else (0,)))
        cases.extend(case(assets, side, 3, 0, mode) for mode in ('crouch', 'guard', 'air-whiff', 'ko'))
    out = OUT/'mixed-ten-chain-contacts.json'
    out.write_text(json.dumps(dict(elf_sha256=sha256(elf).hexdigest(),
        replay_sha256=sha256((BUILD/'ss6-match-replay').read_bytes()).hexdigest(),
        raw21_reaction_table=list(elf[at:at+24]), cases=cases), indent=2)+'\n')
    print(len(cases), 'selected CCD routes matched original hit/guard handlers')


if __name__ == '__main__':
    main()
