// Wall-clock paced TAS: render callbacks may stall; logical input steps may not
// be skipped. The unchanged original runtime computes dt from our timestamps.
(() => {
    class FixedStepClock {
        constructor({hz=240,maxSteps=48}={}) {
            this.stepMs=1000/hz;
            this.maxSteps=maxSteps;
            this.lastWall=null;
            this.debtMs=0;
            this.stats={logicalSteps:0,activeWallMs:0,catchUpSteps:0,maxBatch:0,maxDebtMs:0,stalls:0,droppedSteps:0};
        }
        pause() { this.lastWall=null; }
        advance(now,step,canStep=()=>true) {
            if(this.lastWall===null) {this.lastWall=now;return 0;}
            const elapsed=Math.max(0,now-this.lastWall);
            this.lastWall=Math.max(now,this.lastWall);
            this.debtMs+=elapsed;
            this.stats.activeWallMs+=elapsed;
            if(elapsed>25)this.stats.stalls++;
            this.stats.maxDebtMs=Math.max(this.stats.maxDebtMs,this.debtMs);
            let count=0;
            while(this.debtMs+1e-7>=this.stepMs&&count<this.maxSteps&&canStep()) {
                step();
                this.debtMs=Math.max(0,this.debtMs-this.stepMs);
                this.stats.logicalSteps++;
                count++;
            }
            this.stats.catchUpSteps+=Math.max(0,count-1);
            this.stats.maxBatch=Math.max(this.stats.maxBatch,count);
            return count;
        }
    }
    window.NoHitFixedStepClock=FixedStepClock;
    const query=new URLSearchParams(location.search);
    const csvMode=query.get('csvtas')==='1';
    if((query.get('compensate')!=='1'&&!csvMode)||query.has('oracle'))return;

    function install() {
        const rt=window.c2runtime||document.getElementById('c2canvas')?.c2runtime;
        if(!rt||!window.cr?.runtime)return;
        const physicsHz=csvMode?Number(query.get('fps')??30):240;
        const validHz=[30,60,120,240].includes(physicsHz);
        const clock=new FixedStepClock({hz:validHz?physicsHz:30});
        const clamp30=csvMode&&physicsHz===30;
        // Only 30Hz needs the offset that reaches the original native clamp.
        // Higher rates retain binary64 timestamp subtraction, including its
        // nonuniform dt sequence; no fixed dt is written into the runtime.
        const logicalStepMs=clamp30?1000/30+1e-6:clock.stepMs;
        const mode=csvMode?(clamp30?'fixed-30hz-native-clamp':'fixed-native-timestamps'):'fixed-240hz-realtime-catchup';
        const C=window.__TAS_CLOCK={enabled:true,mode,physicsHz,clock,logicalStepMs,
            stats:clock.stats,stepping:false,error:validHz?null:'Unsupported CSV fps: '+query.get('fps')};
        // Hidden tabs may emit no RAF at all. Reanchor at the actual pause /
        // resume boundary instead of charging that whole interval as lag.
        document.addEventListener('visibilitychange',()=>clock.pause());
        const suspend=window.cr_setSuspended;
        window.cr_setSuspended=function() {
            // Native resume rebases last_tick_time to wall time. Our driver
            // uses a logical timestamp; preserve its exact binary64 phase so
            // pausing to solve cannot move timer events by one physics tick.
            const logicalTimestamp=rt.last_tick_time;
            clock.pause();
            const result=suspend.apply(this,arguments);
            rt.last_tick_time=logicalTimestamp;
            return result;
        };
        // Suppress the runtime's self-scheduled variable-dt callbacks. The RAF
        // driver below invokes the current wrapper chain, so TAS inputs and
        // acceptance observers run for EVERY logical step, including catch-up.
        const proto=cr.runtime.prototype,inner=proto.tick;
        proto.tick=function() {
            if(!C.stepping)return;
            return inner.apply(this,arguments);
        };
        let indicator=null;
        function showClock(paused=false) {
            const hud=document.getElementById('tas-controller-overlay');
            if(!hud)return;
            if(!indicator) {
                indicator=document.createElement('div');
                indicator.id='tas-clock-status';
                indicator.style='color:#a9d8ff;font-size:11px';
                hud.appendChild(indicator);
            }
            const status=C.error?'停止：'+C.error:paused?'暂停':clock.debtMs>25?
                '追帧中，待补 '+Math.ceil(clock.debtMs)+' ms':'正常';
            indicator.textContent='卡顿补偿：'+status;
        }
        function frame(now) {
            requestAnimationFrame(frame);
            if(C.error){showClock();return;}
            if(rt.suspended||document.hidden||!rt.running_layout||!window.TASRunner?.isTickHooked()) {
                clock.pause();showClock(true);return;
            }
            const started=performance.now();
            try {
                const steps=clock.advance(now,()=>{
                    C.stepping=true;
                    try {rt.tick(true,rt.last_tick_time+logicalStepMs,true);}
                    finally {C.stepping=false;}
                },()=>!rt.suspended&&(!csvMode||window.__CSV_TAS?.canAdvance?.()!==false)&&performance.now()-started<8);
                if(steps) {
                    if(rt.glwrap)rt.drawGL();else rt.draw();
                }
            } catch(error) {
                C.error=String(error);
                window.TASRunner?.releaseAllKeys();
                cr_setSuspended(true);
            }
            showClock(rt.suspended);
        }
        requestAnimationFrame(frame);
    }
    if(window.cr?.runtime)install();
    else window.addEventListener('nohit-runtime-ready',install,{once:true});
})();
