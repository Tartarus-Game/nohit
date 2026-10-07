// Source-driven ordinary-input controller for jcw BattleMenu/MenuBones.
// This observes state and returns keys. It never invokes gameplay functions,
// changes the heart, changes HP/KR, or writes menu state.
(() => {
    const SID={heart:5960708907117077,pad:9768267065126338,item:1630849692866887,
        buttons:9802428034038081,leftBone:5246535965326995,bottomBone:761861833921609,
        target:4243712716812677,menu:5359025861573384,bottomOn:9909730646709937,
        bottomTime:2101703704976127,bottomAlternate:9606556173175612};
    const BUTTON_SIDS=new Set([9683599283524679,9343233059165768,9790445263738264,3900276529955833]);
    const vars=i=>i?.instance_vars||i?.hb||[];
    const instanceList=t=>t?.instances||t?.d||[];
    function read(rt) {
        const types=rt.types_by_index||rt.p||[];
        const list=sid=>instanceList(types.find(t=>(t.sid??t.Y)===sid));
        const value=sid=>Number(rt.varsBySid?.[sid]?.data??rt.Vg?.[sid]?.data??0);
        const heart=list(SID.heart)[0],pad=vars(list(SID.pad)[0]);
        const buttons=types.filter(t=>BUTTON_SIDS.has(t.sid??t.Y)).flatMap(instanceList).map(i=>({
            id:vars(i)[0],action:vars(i)[1],x:i.x,y:i.y,w:i.width,h:i.height,
            hx:i.x+i.width*0.145454540848732,hy:i.y+i.height*.5})).sort((a,b)=>a.id-b.id);
        return {menu:value(SID.menu),dt:1/240,clockMs:rt.last_tick_time??rt.dk,heart:heart?{x:heart.x,y:heart.y}:null,
            keys:{left:!!pad[2],right:!!pad[3],confirm:!!pad[4],cancel:!!pad[5]},buttons,
            items:list(SID.item).map(i=>({x:i.x,y:i.y,id:vars(i)[0],action:vars(i)[2]})),
            target:list(SID.target).some(i=>vars(i)[0]===0),bottomOn:value(SID.bottomOn),
            bottomTimer:value(SID.bottomTime),bottomAlternate:value(SID.bottomAlternate),
            bones:[...list(SID.leftBone).map(i=>({kind:'left',x:i.x,y:i.y,w:i.width,h:i.height,
                damage:vars(i)[0],timer:vars(i)[2],destroy:vars(i)[3]})),
                ...list(SID.bottomBone).map(i=>({kind:'bottom',x:i.x,y:i.y,w:i.width,h:i.height,
                damage:vars(i)[0],state:vars(i)[2],button:vars(i)[3]}))]};
    }
    function advance(model) {
        let dt=model.dt;
        if(Number.isFinite(model.clockMs)) {
            const next=model.clockMs+1000/240;
            dt=(next-model.clockMs)/1000;
            model.clockMs=next;
        }
        for(const b of model.bones) if(b.kind==='left') {
            b.timer+=dt;
            const degrees=600*b.timer/Math.PI;
            b.x=-30+Math.abs(Math.sin(degrees*Math.PI/180))*105;
            if(b.x>64) b.timer-=dt*.72;
            if(b.destroy&&b.x<=-8) b.gone=true;
        }
        if(model.bottomOn) {
            model.bottomTimer+=dt;
            if(model.bottomTimer>=.6) {
                model.bottomTimer-=.6;
                for(const id of [model.bottomAlternate,2+model.bottomAlternate]) {
                    const button=model.buttons.find(b=>b.id===id);
                    if(button) model.bones.push({kind:'bottom',x:button.x+button.w,y:480,w:14,h:44,
                        damage:1,state:0,button:id});
                }
                model.bottomAlternate=1-model.bottomAlternate;
            }
        }
        for(const b of model.bones) if(b.kind==='bottom') {
            if(b.state===0) {b.y-=300*dt;if(b.y<=440){b.y=440;b.state=1;}}
            if(b.state===1) {
                b.x-=150*dt;
                const button=model.buttons.find(a=>a.id===b.button);
                if(button&&b.x<=button.x-14){b.x=button.x-14;b.state=2;}
            }
            if(b.state===2) b.y+=300*dt;
            if(b.y>480) b.gone=true;
        }
        model.bones=model.bones.filter(b=>!b.gone);
    }
    function collides(x,y,b) {
        if(!(b.damage>0)) return false;
        // Exact exported menu-bone rectangular collision polygon, not sprite AABB.
        const l=b.x+b.w*.1428570002317429,r=b.x+b.w*.857142984867096;
        const t=b.y+b.h*.04545449838042259,bottom=b.y+b.h*.9545450210571289;
        return x+2>=l&&x-2<=r&&y+2>=t&&y-2<=bottom;
    }
    function safe(model,x,y,ticks=1) {
        const copy={...model,bones:model.bones.map(b=>({...b}))};
        for(let i=0;i<ticks;i++) {
            advance(copy);
            if(copy.bones.some(b=>collides(x,y,b))) return false;
        }
        return true;
    }
    const result=(mask,confirm,reason,blocked=false)=>({keymask:mask,confirm,reason,blocked});
    function decide(model) {
        const {heart,keys,buttons}=model;
        if(!heart) return result(0,false,'waiting_for_heart');
        if(model.menu===0) return result(0,!keys.confirm,model.target?'confirm_strike':'advance_dialogue');
        if(model.menu===1) return result(0,false,'wait_for_menu_resize');
        const nearest=buttons.reduce((best,b)=>!best||Math.hypot(b.hx-heart.x,b.hy-heart.y)<Math.hypot(best.hx-heart.x,best.hy-heart.y)?b:best,null);
        if(model.menu===3) {
            const enemy=model.items.find(i=>i.action==='MenuFightEnemy');
            if(enemy) {
                if(!keys.confirm) return result(0,true,'select_fight_enemy');
                if(safe(model,enemy.x+8,enemy.y+12)) return result(0,false,'release_before_enemy_confirm');
                // Cancel is a normal input edge that invokes the native BackAction.
                const fight=buttons.find(b=>b.action==='MenuFight');
                if(fight&&!keys.cancel&&safe(model,fight.hx,fight.hy,2)) return result(16,false,'retreat_from_menu_bone');
                return result(0,false,'no_safe_enemy_release',true);
            }
            return result(keys.cancel?0:16,false,'return_to_fight_menu');
        }
        if(model.menu!==2||!nearest) return result(0,false,'unrecognized_menu');
        const fight=buttons.find(b=>b.action==='MenuFight');
        if(!fight) return result(0,false,'missing_fight_button',true);
        if(nearest.id===fight.id&&!keys.confirm&&safe(model,72,284,3)) {
            return result(0,true,'enter_enemy_during_safe_window');
        }
        const currentIndex=buttons.findIndex(b=>b.id===nearest.id),fightIndex=buttons.findIndex(b=>b.id===fight.id);
        const distance=i=>Math.min((i-fightIndex+buttons.length)%buttons.length,(fightIndex-i+buttons.length)%buttons.length);
        const options=[];
        if(safe(model,nearest.hx,nearest.hy,2)) options.push({mask:0,rank:distance(currentIndex)+.25});
        for(const [mask,delta,held] of [[1,-1,keys.left],[2,1,keys.right]]) {
            if(held) continue;
            const index=(currentIndex+delta+buttons.length)%buttons.length,b=buttons[index];
            if(safe(model,b.hx,b.hy,2)) options.push({mask,rank:distance(index)});
        }
        options.sort((a,b)=>a.rank-b.rank);
        if(!options.length) return result(0,false,'no_safe_menu_step',true);
        return result(options[0].mask,false,options[0].mask?'navigate_safe_button':'wait_for_enemy_window');
    }
    window.NoHitMenuController={read,advance,collides,safe,decide,step:rt=>decide(read(rt))};
})();
