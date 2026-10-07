// Opt-in deterministic RND instructions. Rendering/effects keep their own RNG.
(function installSeed() {
    if (!window.cr?.runtime) {
        window.addEventListener('nohit-runtime-ready', installSeed, {once:true});
        return;
    }
    const raw = new URLSearchParams(location.search).get('seed');
    if (raw === null) return;
    const seed = Number(raw);
    if (!Number.isInteger(seed) || seed < 0 || seed > 0xffffffff) return;
    const A = window.__TAS_SEED = { seed, algorithm: 'xorshift32', runs: [] };
    let state = seed >>> 0 || 0x6d2b79f5;
    let draws = [];
    A.checkpoint = () => ({ state, runs: A.runs.map(r => ({ seed: r.seed, draws: r.draws.slice() })) });
    A.restore = checkpoint => {
        state = checkpoint.state;
        A.runs = checkpoint.runs.map(r => ({ seed: r.seed, draws: r.draws.slice() }));
        draws = A.runs.length ? A.runs[A.runs.length - 1].draws : [];
    };
    const proto = cr.runtime.prototype, original = proto.trigger;
    proto.trigger = function (method, inst, value) {
        const fn = method === cr.plugins_.Function.prototype.cnds.OnFunction
            ? String(value).toLowerCase() : '';
        if (fn === 'tlplay') {
            state = seed >>> 0 || 0x6d2b79f5;
            draws = [];
            A.runs.push({ seed, draws });
        }
        if (fn !== 'rnd') return original.apply(this, arguments);
        const normalRandom = Math.random;
        Math.random = () => {
            state ^= state << 13;
            state ^= state >>> 17;
            state ^= state << 5;
            state >>>= 0;
            const result = state / 4294967296;
            draws.push(result);
            return result;
        };
        try { return original.apply(this, arguments); }
        finally { Math.random = normalRandom; }
    };
})();
