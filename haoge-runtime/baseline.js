// Whole-game no-damage criterion, expressed against the game's own baseline.
//
// Criterion: HP never falls below the build's own full value (MaxHP). That is
// what "no hit" means for this project, and it is checked on every observed tick.
//
// Two build-specific facts shape this file.
//
// 1. HP baseline. The vendored jcw87 build has MaxHP 92 and every observer used
//    to hardcode that literal; the haoge build of the same project ships 142.
//    Read it from the running game and cache the first successful read, so a
//    mid-run change of MaxHP cannot silently move the goalposts -- it would fail
//    the comparison instead.
//
// 2. KR is recorded, not required to be zero. The vendored build's observers
//    required KR == 0 as a proxy for "was hit", which was exact there because the
//    only DamagePlayer calls were real hits. The haoge scripts also call
//    DamagePlayer(-N, 1) as a *heal* that raises KR by one. In this build the
//    lowest KR drain bucket is `KR > 10` (every 0.5 s, one HP); the only `KR > 0`
//    branch sets the flavour text "* You felt your sins crawling on your back."
//    So a KR of 1 can never cost HP, and treating it as a hit would be a false
//    positive. Every excursion is recorded in `krInjections` by the observer so
//    the evidence states it instead of hiding it.
(() => {
    let cached = null;
    function read() {
        if (cached !== null) return cached;
        const rt = window.c2runtime || document.getElementById('c2canvas')?.c2runtime;
        if (!rt || !rt.all_global_vars) throw Error('NoHitBaseline: runtime is not ready');
        const globals = Object.fromEntries(rt.all_global_vars.map(v => [v.name, v.data]));
        const baseline = Number(globals.MaxHP);
        if (!Number.isFinite(baseline) || baseline <= 0) throw Error('NoHitBaseline: MaxHP is not a positive number');
        cached = baseline;
        return cached;
    }
    window.NoHitBaseline = Object.freeze({
        read,
        get value() { return read(); },
        criterion: 'HP-never-below-MaxHP; KR reported separately (this build drains HP only above KR 10)',
        // `kr` is accepted so existing call sites stay readable and is
        // deliberately not part of the criterion.
        matches(hp, kr) { return Number(hp) === read(); },
    });

    // Demo mode (`?demo=1`). A recorded demonstration must reach the end of the
    // run even where a route is known to take a hit, so the damage checks stop
    // being *abort* conditions -- they keep recording. This is an explicit,
    // visible mode, never a silent default: the badge says so, and every piece of
    // evidence written in this mode carries demo_mode: true. The criterion itself
    // is unchanged and still evaluated, so the record still reports minHP, maxKR
    // and the exact ticks where HP moved.
    const query = new URLSearchParams(location.search);
    window.NoHitDemo = Object.freeze({
        enabled: query.get('demo') === '1',
        label: '演示模式：掉血记录但不中止',
    });
    if (window.NoHitDemo.enabled) {
        const badge = document.getElementById('tas-status-badge');
        if (badge) badge.textContent = window.NoHitDemo.label;
    }
})();
