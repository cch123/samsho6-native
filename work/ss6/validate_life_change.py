"""Compare pending damage and recovery against the complete PS2 routine at 14a8d0."""
import itertools
import subprocess
import tempfile
from pathlib import Path

from round_entry_oracle import ROOT, fixture
from validate_dash_motion import ELF, PIN, digest

DRIVER = r'''
#include "battle_round.hpp"
#include <iostream>
int main() {
    ss6::BattleRoundState battle;
    ss6::StateEntryActor recipient;
    int amount;
    unsigned opponent;
    while(std::cin>>battle.gameMode>>battle.timeOption13c>>battle.field08>>battle.timers.values[0]
                  >>recipient.flags23c>>opponent>>recipient.pendingDamageA38>>amount) {
        battle.queueLifeChange(recipient,opponent,amount);
        std::cout<<uint32_t(recipient.pendingDamageA38)<<'\n';
    }
}
'''

def main():
    assert digest(ELF) == PIN
    rows, expected = [], []
    for seat in range(2):
        original, a, _, b = fixture(seat)
        other = 0x1c00000 + (1-seat)*0xf2c
        original.write(0x43d061,100,1)
        # field08 == 1 suppresses the timeout query. A negative timer word
        # also differs from exactly zero even though normal countdown clamps.
        for mode,option,field,timer,ko,other_ko,amount in itertools.product(
                (0,3),(0,3),(0,1),(-1,0,1),(0,0x80),(0,0x80),(-16,1,20)):
            pending = 3
            for addr,value in ((0x4c3808,mode),(b+0x13c,option),(b+8,field),(b+0x114,timer),
                               (a+0x23c,ko),(other+0x23c,other_ko),(a+0xa38,pending)):
                original.write(addr,value,4)
            original.run(0x14a8d0,[a,amount])
            rows.append((mode,option,field,timer,ko,other_ko,pending,amount))
            expected.append(original.read(a+0xa38,4))
    with tempfile.TemporaryDirectory() as temp:
        driver, exe = Path(temp)/'probe.cpp', Path(temp)/'probe'
        driver.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',driver,
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        raw = '\n'.join(' '.join(map(str,row)) for row in rows)
        actual = subprocess.run([exe],input=raw,text=True,capture_output=True,check=True)
        observed = list(map(int,actual.stdout.split()))
        assert len(observed) == len(rows)
        for row,got,want in zip(rows,observed,expected):
            assert got == want, (row,got,want)
    print(len(rows),'life change requests matched 14a8d0 on both seats')

if __name__ == '__main__':
    main()
