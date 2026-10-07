// BGM mute. Keeps every sound effect, silences the music track only.
//
// The fight's music is a single file, `mus_zz_megalovania.ogg`, and the Construct 2
// Audio plugin plays it through an HTMLAudioElement (`new Audio(...)` in
// c2runtime.js). The only trigger in this build is the CSV row
// `2.4,sound,mus_zz_megalovania,0` in sans_final.csv, so the music is a pure
// cosmetic output and muting it cannot touch the simulation: the model already
// classifies `sound` as cosmetic, and nothing in physics or the clock reads it.
//
// This wraps HTMLMediaElement.play so a music source never starts; every other
// source falls through untouched. Opt back in with `?bgm=1`. What was muted is
// recorded in window.__BGM_MUTE so a recording can state it instead of guessing.
(() => {
    const query = new URLSearchParams(location.search);
    const M = window.__BGM_MUTE = { enabled: false, muted: [], reason: null };
    if (query.get('bgm') === '1') { M.reason = 'opted_in_by_query'; return; }

    const proto = window.HTMLMediaElement && window.HTMLMediaElement.prototype;
    if (!proto || typeof proto.play !== 'function') { M.reason = 'HTMLMediaElement.play unavailable'; return; }

    // Music files in this project are named `mus_*`; the speech and effect files
    // are named after the event (heartsplit, ding, warning, ...), so this cannot
    // swallow a sound effect.
    const isMusic = source => /(?:^|[\/\\_-])mus[_\-.]/i.test(String(source || ''));

    const original = proto.play;
    proto.play = function () {
        let source = '';
        try { source = this.currentSrc || this.src || ''; } catch (_) { source = ''; }
        if (isMusic(source)) {
            M.muted.push({ at: Date.now(), file: source.split('/').pop(), tick: mqTick() });
            try { this.pause(); } catch (_) {}
            try { this.volume = 0; } catch (_) {}
            return Promise.resolve();
        }
        return original.apply(this, arguments);
    };
    function mqTick() {
        try { return document.getElementById('c2canvas')?.c2runtime?.tickcount ?? null; } catch (_) { return null; }
    }
    // Music that started before this script ran (a menu theme) is stopped too.
    const stopExisting = () => {
        for (const element of document.querySelectorAll('audio,video')) {
            try {
                const source = element.currentSrc || element.src || '';
                if (isMusic(source) && !element.paused) { element.pause(); element.volume = 0; M.muted.push({ at: Date.now(), file: source.split('/').pop(), tick: mqTick(), late: true }); }
            } catch (_) {}
        }
    };
    stopExisting();
    document.addEventListener('DOMContentLoaded', stopExisting);
    M.enabled = true;
    M.label = 'BGM 已静音（音效保留）';
})();
