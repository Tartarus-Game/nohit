"""Independent offline checks for the fresh headless continuous Normal record."""
import argparse
import hashlib
import json
from pathlib import Path

from tools.verify_full_game_acceptance import EXPECTED_ATTACKS

ROOT=Path(__file__).resolve().parents[1]


def verify(path):
    data=json.loads(Path(path).read_text())
    errors=[]
    def check(value,reason):
        if not value:errors.append(reason)
    check(data['protocol']=='continuous-normal-unchanged-c2-ordinary-keyboard','protocol')
    check(data['won'] and not data['failure'],'native Win2 absent or runtime failure')
    check(not data['damage'],'native DamagePlayer observed')
    for name,key in [('c2runtime.js','runtime_sha256'),('data.js','data_sha256')]:
        check(hashlib.sha256((ROOT/'c2-sans-fight'/name).read_bytes()).hexdigest()==data[key],name+' hash')
    for name,digest in data['solver_sha256'].items():
        check(hashlib.sha256((ROOT/'nohit/engine'/name).read_bytes()).hexdigest()==digest,name+' hash')
    ticks=data['ticks'];by_tick={row['tick']:row for row in ticks}
    check(len(by_tick)==len(ticks),'duplicate ticks')
    check(all(b['tick']==a['tick']+1 for a,b in zip(ticks,ticks[1:])),'non-continuous native ticks')
    check(all(row['HP']==92 and row['KR']==0 and row['mode']==0 for row in ticks),'native HP/KR/mode')
    check(all(b['clock_start_ms']>a['clock_start_ms'] and
              b['dt']==min((b['clock_start_ms']-a['clock_start_ms'])/1000,1/30)
              for a,b in zip(ticks,ticks[1:])),'native clock')
    rounds=data['rounds']
    check(tuple(r['wave'] for r in rounds)==EXPECTED_ATTACKS,'Normal attack sequence')
    components=0;inputs=0
    for number,r in enumerate(rounds):
        plan=r['plan'];entry=r['entry'];rows=r['rows'];word=plan['actions'];confirms=plan['confirm_sequence']
        check(r['completed'] and r['ended'] and r['cursor']==len(word),f'round {number} incomplete')
        check(plan['verified'] and plan['status']=='candidate_found',f'round {number} model witness')
        check(len(rows)==len(word)+1 and len(word)==len(confirms),f'round {number} row count')
        check(hashlib.sha256((ROOT/'c2-sans-fight'/(r['wave']+'.csv')).read_bytes()).hexdigest()==r['csv_sha256'],f'round {number} CSV hash')
        saved=Path(path).parent/(str(number).zfill(2)+'-'+r['wave']+'-plan.json')
        check(hashlib.sha256(saved.read_bytes()).hexdigest()==r['plan_sha256'],f'round {number} plan hash')
        check(json.loads(saved.read_text())==plan,f'round {number} plan bytes')
        check(rows[0]['initial']==entry['initial']==plan['trajectory'][0],f'round {number} frame zero')
        for index,row in enumerate(rows):
            tick=entry['tick']+index;actual=by_tick.get(tick)
            check(actual is not None and row['tick']==tick,f'round {number} coverage at {index}')
            if actual is None:continue
            check(row['initial']==actual['state'],f'round {number} independent player at {index}')
            check(row['dt']==actual['dt']==entry['dt_schedule'][index],f'round {number} source clock at {index}')
            if index:
                check(actual['input']==word[index-1]|(32 if confirms[index-1] else 0),f'round {number} input at {index}')
                inputs+=1
                check(plan['dt_sequence'][index-1]==actual['dt'],f'round {number} planned clock at {index}')
            if 0<index<len(word):
                check(row['initial']==plan['trajectory'][index],f'round {number} model state at {index}')
                components+=11
        check(r['end_tick']+1==rows[-1]['tick'],f'round {number} EndAttack boundary')
    ends=[e for e in data['events'] if e['fn']=='endattack']
    check(len(ends)==24,'native EndAttack count')
    check([e['tick'] for e in ends]==[r['end_tick'] for r in rounds],'native terminal events')
    check(any(e['fn']=='win1' for e in data['events']) and any(e['fn']=='win2' for e in data['events']),'native victory events')
    return dict(passed=not errors,errors=errors,continuous_native_ticks=len(ticks),
                completed_rounds=sum(r['completed'] for r in rounds),matched_inputs=inputs,
                compared_nonterminal_components=components,HP=92,KR=0,damage_calls=len(data['damage']),
                fps=data['fps'],source_record_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                scope='this fresh headless record; unchanged native C2 events with DOM/audio/render stubs')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();result=verify(args.record)
    args.out.write_text(json.dumps(result,indent=2));print(json.dumps(result))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
