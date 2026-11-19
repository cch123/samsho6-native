#!/usr/bin/env python3
"""Catalog ACT -> JDG references without assigning speculative combat names."""
import collections
import json
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'


def main():
    entries=[]
    for path in sorted(ASSETS.glob('jdg_*.bin')):
        ident=path.stem[4:];data=path.read_bytes();act=(ASSETS/f'act_{ident}.bin').read_bytes()
        assert len(data)%16==0 and len(act)%60==0
        types=collections.Counter(struct.unpack_from('<I',data,i)[0]>>26 for i in range(0,len(data),16))
        references=0; unresolved=[]
        for off in range(0,len(act),60):
            flags,=struct.unpack_from('<H',act,off+0x1e)
            for index in struct.unpack_from('<8h',act,off+0x0e)[:flags&7]:
                if not 0<=index<len(data)//16:
                    # Keep anomalous source data visible. Resource 99 currently
                    # has one one-past-end reference; do not clamp it or invent
                    # a rectangle while its runtime loading context is unknown.
                    unresolved.append(dict(act_record=off//60,judgment_index=index))
                references+=1
        entries.append(dict(resource=ident,records=len(data)//16,act_records=len(act)//60,
                            references=references,raw_types=dict(sorted(types.items())),unresolved_references=unresolved))
    aid=(ASSETS/'aid_00.bin').read_bytes();act=(ASSETS/'act_00.bin').read_bytes();jdg=(ASSETS/'jdg_00.bin').read_bytes()
    action=185;start,=struct.unpack_from('<h',aid,action*2);count=aid[4096+action];steps=[];tick=0
    for i in range(count):
        off=(start+i)*60;flags,=struct.unpack_from('<H',act,off+0x1e);duration,=struct.unpack_from('<h',act,off+0x34)
        refs=struct.unpack_from('<8h',act,off+0x0e)[:flags&7]
        boxes=[]
        for ref in refs:
            meta,aux,x1,y1,x2,y2,tail=struct.unpack_from('<I6h',jdg,ref*16)
            boxes.append(dict(index=ref,type=meta>>26,metadata=f'0x{meta:08x}',aux=aux,rect=[x1,y1,x2,y2],tail=tail))
        steps.append(dict(step=i,first_update=tick,duration=duration,judgments=boxes));tick+=duration
    report=dict(resource_sets=len(entries),jdg_records=sum(e['records'] for e in entries),
                act_references=sum(e['references'] for e in entries),
                unresolved_reference_count=sum(len(e['unresolved_references']) for e in entries),
                resources=entries,action_185=dict(duration=tick,steps=steps),
                scope='Structural references and raw type fields. Geometry does not determine damage, block, invulnerability, cancellation or hitstop semantics.')
    (ROOT/'outputs/ss6-feasibility/judgment_catalog.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['resources','action_185']},indent=2))


if __name__=='__main__': main()
