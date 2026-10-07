// Names-only compatibility for the checked-in jcw87 minified Construct 2 export.
// Aliases forward to existing fields/functions; physics and event sheets are untouched.
(() => {
    if (window.cr?.runtime) return;
    if (typeof sc !== 'function' || typeof xc !== 'function' || typeof Yb !== 'function') {
        throw new Error('Unsupported C2 export: jcw87 runtime symbols do not match');
    }
    function aliases(object, names) {
        for (const [readable, minified] of Object.entries(names)) {
            if (readable in object) continue;
            Object.defineProperty(object, readable, {configurable:true,
                get() { return this[minified]; }, set(value) { this[minified]=value; }});
        }
    }
    for (const plugin of [sc, xc]) aliases(plugin.prototype, {Instance:'S', Type:'W', cnds:'c', acts:'e', exps:'g'});
    aliases(sc.prototype.c, {OnFunction:'Ui'});
    // The return-value object is part of the minified expression ABI too.
    sc.prototype.g.Param = function(ret, index) {
        return this.Gt({Kg:v=>ret.set_any(v), H:v=>ret.set_int(v), n:v=>ret.set_float(v), la:v=>ret.set_string(v)}, index);
    };
    aliases(sc.prototype.S.prototype, {runtime:'b', onCreate:'D'});
    Object.defineProperty(sc.prototype.S.prototype, 'exps', {get(){return sc.prototype.g;}});
    aliases(xc.prototype.S.prototype, {runtime:'b', keyMap:'qg', onCreate:'D'});
    const adapted=new WeakSet();
    function adaptType(type) {
        if (!adapted.has(type)) {
            aliases(type, {sid:'Y', instances:'d', is_family:'B', members:'yg', families:'Da', family_index:'Vd', family_var_map:'Hj', texture_file:'Yk'});
            adapted.add(type);
        }
        for (const inst of type.d || []) {
            if (!adapted.has(inst)) {
                aliases(inst, {runtime:'b', angle:'m', instance_vars:'hb', behavior_insts:'L', bbox:'Qa', bquad:'Xb',
                    update_bbox:'Aa', set_bbox_changed:'za', layer:'j', collision_poly:'Ua', collisionsEnabled:'$e'});
                adapted.add(inst);
            }
            for (const behavior of inst.L || []) {
                if (!adapted.has(behavior)) {
                    aliases(behavior, {dx:'xb', dy:'yb'});
                    adapted.add(behavior);
                }
            }
        }
        return type;
    }
    window.cr = {plugins_:{Function:sc, Keyboard:xc}, runtime:null, createRuntime:window.cr_createRuntime};
    const create=window.cr_createRuntime;
    window.cr_createRuntime=function(...args) {
        const rt=create(...args);
        const proto=Object.getPrototypeOf(rt);
        aliases(proto, {tick:'mb', saveToJSONString:'ry', loadFromJSONString:'tx', testOverlap:'Fy', drawGL:'Kb', draw:'ed',
            all_global_vars:'Gu', all_local_vars:'Hu', varsBySid:'Vg', tickcount:'Rg', dt:'De', dt1:'df', last_tick_time:'dk',
            kahanTime:'Bb', wallTime:'oe', running_layout:'ba', isloading:'Mh', glwrap:'k', suspended:'Ih'});
        Object.defineProperty(proto, 'types_by_index', {configurable:true,get(){return this.p.map(adaptType);}});
        aliases(rt.Bb, {sum:'Z', c:'Vk', t:'Il'});
        aliases(rt.oe, {sum:'Z', c:'Vk', t:'Il'});
        window.cr.runtime=rt.constructor;
        window.cr.createRuntime=window.cr_createRuntime;
        window.dispatchEvent(new Event('nohit-runtime-ready'));
        return rt;
    };
})();
