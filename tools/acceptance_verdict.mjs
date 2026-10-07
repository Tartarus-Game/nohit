export function assertLiveRuns(runs, count) {
    if (!Number.isInteger(count) || count<1 || !Array.isArray(runs) || runs.length<count) throw Error('Incomplete live acceptance');
    for (const [index,r] of runs.slice(0,count).entries()) {
        if (r.startHP!==92 || r.minHP!==92 || r.endHP!==92 || r.maxKR!==0 || r.hits!==0 || r.endAttackObserved!==true || !(r.rows>0)) {
            throw Error(`Live round ${index+1} failed the HP 92 / KR 0 / hits 0 / EndAttack contract`);
        }
    }
}
