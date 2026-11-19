"""Exercise autonomous local VS through a complete 60-count set; no reference timing claim."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from itertools import product
from pathlib import Path
import json
import subprocess
import tempfile
from validate_dash_motion import ASSETS,ROOT,digest

DRIVER=r'''
#include "native_match.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
 unsigned left=std::stoul(argv[2]),right=std::stoul(argv[3]),s0=std::stoul(argv[4]),s1=std::stoul(argv[5]);
 unsigned cpu=std::stoul(argv[6]);VersusLineup lineup{{{left,s0,0},{right,s1,1}}};
 NativeMatch m(argv[1],60,VersusMode::Console,nullptr,{},lineup);
 for(unsigned i=0;i<2;++i)if(cpu&(1<<i))m.enableCpu(i,std::stoi(argv[7]));
 std::string failure;
 try {while(m.updates<40000&&!m.finished&&!m.characterSelect())m.tick({});}
 catch(const std::exception& e){failure=e.what();}
 const auto& score=m.battle().match.players;
 if(failure.empty()&&!m.finished)failure=m.characterSelect()?"early character select":"40000-update bound";
 if(failure.empty()&&!score[0].complete()&&!score[1].complete())failure="set ended without a winning score";
 if(failure.empty()&&!m.battle().consoleMenu.active)failure="console result menu missing";
 std::cout<<(failure.empty()?"OK":"FAIL")<<' '<<m.updates<<' '<<score[0].wins<<' '<<score[1].wins
          <<' '<<m.battle().match.roundIndex<<' '<<m.battle().matchEnd.winner08;
 for(unsigned i=0;i<2;++i) {
     const auto& f=m.fighter(i);const auto& a=f.actor;
     std::cout<<' '<<f.hits<<' '<<a.stateTable()<<'/'<<a.stateIndex()<<' '<<a.controlMotion38[1]<<'/'<<a.controlMotion38[3];
 }
 std::cout<<' '<<failure<<'\n';
}
'''
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--level',type=int,default=4)
    ap.add_argument('--workers',type=int,default=6)
    ap.add_argument('--all-spirits',action='store_true',help='exercise all 36 spirit pairs for each fighter pair and CPU seat choice')
    ap.add_argument('--case',nargs=5,type=int,metavar=('P1','P2','S1','S2','CPU_MASK'))
    ap.add_argument('--results',type=Path,help='optional per-case TSV outside the assets')
    args=ap.parse_args()
    cases=([tuple(args.case)] if args.case else [(i,j,si,sj,mask) for i,j,si in product(range(4),range(4),range(6))
           for sj in (range(6) if args.all_spirits else [(si+i+2*j)%6]) for mask in (1,2,3)])
    with tempfile.TemporaryDirectory() as temp:
        driver=Path(temp)/'probe.cpp';exe=Path(temp)/'probe';driver.write_text(DRIVER)
        library=ROOT/'work/ss6/build-native/libss6-runtime.a'
        library_hash=digest(library)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',driver,library,'-o',exe],check=True)
        assert digest(library)==library_hash, 'Runtime rebuilt while linking the verification driver'
        def run(case):
            proc=subprocess.run([exe,ASSETS,*map(str,case),str(args.level)],text=True,capture_output=True)
            if proc.returncode:return 'CRASH '+str(proc.returncode)+' '+proc.stderr.strip()
            return proc.stdout.strip()
        results={};failures=Counter();wins=Counter();completed_ticks=[]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(run,c):c for c in cases}
            for f in as_completed(futures):
                c=futures[f];row=f.result();results[c]=row
                if row.startswith('OK '):
                    parts=row.split();wins[c[-1],int(parts[5])]+=1;completed_ticks.append(int(parts[1]))
                else:
                    reason=' '.join(row.split()[12:]) if row.startswith('FAIL ') else row
                    failures[reason]+=1
                    if failures[reason]==1:print('First failure',c,row,flush=True)
                if len(results)%72==0:print(len(results),'/',len(cases),'sets checked',flush=True)
        if args.results:
            args.results.write_text('p1\tp2\tp1_spirit\tp2_spirit\tcpu_mask\tstatus updates p1_wins p2_wins round_index winner p1_hits p1_state p1_sequence/op p2_hits p2_state p2_sequence/op error\n'+
                                    ''.join('\t'.join(map(str,c))+'\t'+results[c]+'\n' for c in cases))
        print('Fighter level',args.level,'verified sets',len(results)-sum(failures.values()),'of',len(cases),'failures',dict(failures))
        outcomes={mask:{'P1':wins[mask,0],'P2':wins[mask,1],'draw':wins[mask,-1]} for mask in (1,2,3)}
        for mask in (1,2,3):print('CPU seat mask',mask,outcomes[mask])
        if args.all_spirits and not args.case:
            report=dict(scope='NativeMatch, default console local VS, 60-count clock and two wins, neutral physical input. Four fighters, every pair of six spirits and every nonempty CPU seat mask; completion requires reaching the console result menu. Whole-set reference input and frame timing are outside this test.',
                        rerun=f'python3 -B work/ss6/validate_cpu_whole_matches.py --all-spirits --level {args.level}',
                        runtime_archive_sha256=library_hash,fighter_level=args.level,total=len(cases),
                        completed=len(completed_ticks),all_completed=len(completed_ticks)==len(cases),failures=dict(failures),
                        failed_cases=[[*c,results[c]] for c in cases if not results[c].startswith('OK ')],
                        result_by_cpu_mask=outcomes,completed_update_range=[min(completed_ticks),max(completed_ticks)] if completed_ticks else [])
            path=ROOT/f'outputs/ss6-feasibility/cpu-whole-matches-level{args.level}.json'
            path.write_text(json.dumps(report,indent=2)+'\n')
        if args.case:print(results[cases[0]])
        if failures:raise SystemExit(1)
if __name__=='__main__':main()
