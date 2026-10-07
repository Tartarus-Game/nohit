# Round 14: real-game bonesgap1, Codex internal browser

## Earlier single-round results (see latest ten-round acceptance at the end)

After reading BTS movement/CustomMovement source, introduced
`nohit/engine/source_vertical.py`. It models four 240Hz microticks per plan
frame, movement before event-sheet input/gravity, rollback on solid contact,
UP press/release edges, the 1px jump-contact probe and 0.2px gravity-contact
probe. It retains fractional y/velocity and previous UP state.

Real-game full-round acceptance in the Codex internal browser:

| Wave | Start/min/end HP | Max KR | HP decreases | Input frames |
|---|---|---|---|---|
| sans_bonegap1 | 92/92/92 | 0 | 0 | 40 |
| sans_bonegap1fast | 92/92/92 | 0 | 0 | 40 |
| sans_bluebone | 92/92/92 | 0 | 0 | 33 |

Bonegap1 trace: `tools/real-game/bonesgap1-20261004-050805-865154.json`.
Fast trace: `tools/real-game/bonesgap1-20261004-051050-910334.json`.
Blue trace and summary screenshot:
`tools/real-game/bonesgap1-20261004-051224-827252.json` and matching `.png`.
Filename prefix is historical; the JSON `wave` field is authoritative.
Candidate payloads are `bonesgap1-source-route.json`,
`sans_bonegap1fast-source-route.json`, `sans_bluebone-source-route.json` in
the same directory. These are generated routes, not hardcoded recordings.

Fast and Blue observations stop on the actual `EndAttack` function trigger.
The source planner checks blue hazards only when its candidate heart moves;
real-game HP/KR confirmed those two tested color rules survived the round.

Current limits: fixed X, blue gravity pointing down, no platforms/slams,
fixed nominal240Hz substeps, approximate floor polygon boundary, state merging
and a 6000-state frontier cap. Minimum inputs are the ranking objective, but
global optimality is NOT proved. This is a useful source-based calibration
module, not the completed universal simulator.
Bone Slide H returned no fixed-X candidate; it was NOT given a real-game
acceptance run and is not claimed impossible. Next: add horizontal search,
then RED mode, variable dt and platforms/slams before blasters/random waves.

The UI no longer calls generated routes "optimal", or playback exhaustion
"NO-HIT CLEAR". It uses route-loaded / HP-unverified status. Acceptance results
are separate real-engine observations. Displayed plan time now uses60Hz.
Dashboard PID43020 on8099; browser tab2 contains Blue Bone and an added results
panel, paused after measurement, marked for handoff. No local tests were run.

User constraint: no local tests or Python replay as proof. Only a full real-game
round with no HP decrease qualifies. Python is used solely to generate candidates.
No local tests were run in this round. Extend only within the measured model scope.

## Measured results

- Existing runner: first real hit at raw Timeline T=1.6043, clock frame 96.
  The initial observer mistakenly continued through multiple attack cycles; its
  final HP=0 is NOT a single-round result.
- After unwrapping the timeline clock: full round HP 92 -> 77, 13 observed
  HP-decrease ticks. Still failed.
- After correcting gravity and generating a new candidate: full round HP
  92 -> 53, 37 observed HP-decrease ticks, 1587 engine ticks recorded. Failed.

Saved actual trace and screenshot:
`tools/real-game/bonesgap1-20261004-050256-573436.json` and matching `.png`.
The game is paused AFTER measurement, and a clearly labelled result panel has
been added. It is not a screenshot of the exact ending tick. Trace is the
authority for the recorded round. Internal browser tab 2 is marked for handoff.

## Corrections to round 13's claims

1. Timeline T is NOT monotonic attack age. Timeline.xml action
   sid=98827945093618 subtracts the delay of each executed CSV line. The live
   trace shows T falling from 0.2001 to 0.0043 at bone generation. The previous
   runner discarded ~0.2 seconds (12 plan frames). `tas_runner.js` now unwraps
   these subtractions using the actual completed engine tick's dt.
2. The model's gravity transcription was wrong. Real trace median acceleration
   while falling faster than 15 px/s is 540 px/s^2. Model had used a 240 px/s
   threshold. Battle.xml bands are >15:540; (-30,15]:180;
   (-120,-30]:450; <=-120:180. Corrected c2spec.py, scalar/batch dynamics and
   mininput.py. These changes are NOT an assertion that dynamics now match.
3. Internal model self-consistency cannot prove agreement with the real game.
   The round-13 claim that remaining damage cannot originate in the model was
   unjustified: it compared a hazard predicate with the model's own geometry.
4. Runner displayed NO-HIT CLEAR after ordinary playback/attack termination
   even with damage. Replaced those labels with HP UNVERIFIED.

## Next deterministic discrepancy

With the new candidate, plan frame 114 expects the heart grounded at local y=0
and sends UP through frame 120. Real frame 114 is still falling at canvas
y=375.767 and dy=136.923. At frame 115 collision stops it near y=377.535, but
it does not fully settle until frame 120. The planned second jump never occurs:
real y remains ~377.979 while the model expects local y~20 at frame 132.
First hit is raw T=2.0083, clock frame132, HP92->91.

Calibrate real landing/contact and jump-trigger semantics before optimizing.
Do not move candidate jumps based only on local replay. Observe actual key
edges, floor-contact probes and velocity, and rerun the complete real round.

## Infrastructure

- Dashboard is running as hidden python process PID25732, port8099.
- Candidate generation after a server restart takes ~13 seconds. Warm
  `/api/tas?wave=sans_bonegap1.csv&physics_mode=c2` BEFORE reloading the game.
- Internal browser supports `tab.capabilities.get('cdp')`; read its docs.
  Runtime is on `document.getElementById('c2canvas').c2runtime`.
- Use `?mode=single&attack=sans_bonegap1&acceptance=1`. Opt-in
  `live_acceptance.js` records real HP, position, velocity and bone overlaps.
  It stops on EndAttack's T subtraction (previous T>6, current T lower),
  preventing multi-round contamination. It never modifies HP/position/input.
- POST `/api/acceptance` persists real observations and optional screenshot in
  `tools/real-game`. Saved trace is independent of Python verifier.
- Node ego scripts exist but are unnecessary for internal browser execution.

Remaining goals: one real no-hit bonesgap1 round, then minimal input objective,
then other waves. None of these goals is claimed complete.
## Blue Bone correction: XY search and repeated real-game failure

The first-round Blue result above does NOT establish a stable route. The user
observed subsequent damage. Continuous real-engine observation reproduced it.
Fixed X was a calibration simplification, not a game constraint; failed search
must never be interpreted as an impossible original attack.

A radius-36 XY candidate (40 input frames) with per-X-band beam diversity ran
in the internal browser: rounds 1 and 2 HP92->92, round3 HP92->87 (5 HP drops).
First hit at clock198: real heart x284.975,y375.159,dy13.542, overlapping white
bone x273.02,y366,w10,h20. This is an actual failed acceptance, not Python proof.
Trace/screenshot: tools/real-game/bonesgap1-20261004-052344-981992.json/.png.
The screenshot includes a summary added after measurement.

Latest code makes Blue Bone choose XY directly (no fixed-X first pass) and
removes the default horizontal radius restriction, using the full baked arena.
The beam retains candidates across X bands so immediate input cost cannot
remove every lateral alternative. State merging/capping remains approximate.
These latest full-arena changes have NOT yet been generated or accepted live.
Server PID40608 currently has the previous cached radius36 candidate; restart
and warm API before any next live run. No local tests were run.
## Latest: landing dwell and ten real Blue Bone rounds accepted

Added landing_wait_frames=4 to source_local.solve_source_local. Jump rising
edges require four entire 60Hz plan frames of y<0.2 and zero vertical speed;
count resets if any microtick is not settled or UP is held. State/key includes
the count. Initial heart starts already settled. Horizontal search remains
full-arena with X-band diversity. This is a feasibility buffer before cost
ranking; it is not a calibrated general physics guarantee.

Generated tools/real-game/sans_bluebone-wait4-route.json (35.96sec, 58 input
frames). Actual internal browser continuous run completed TEN rounds: every
start/end HP92, maxKR0, zero recorded HP decreases. In first real round, jumps
at clock65,112,157,221,266; measured resting time before later jump edges was
162,137,325,137ms. Thus those jumps did have measurable landing dwell.
Changes include full-arena XY AND the dwell constraint; no isolated causality
claim about which change cured the previous damage is justified.

Trace/screenshot: tools/real-game/bonesgap1-20261004-052706-682197.json/.png.
Screenshot contains an explicitly marked summary added after measurement.
Live observer now also records LEFT/RIGHT. No Python tests/replays were run.
Ten clean observed rounds are evidence for this candidate/environment, not a
proof of universal reliability or globally minimal input time.

Current hidden dashboard process PID26872 on8099 has the accepted candidate
cached. Browser tab2 URL cb=blue-wait4, suspended after measurement; marked for
handoff. Server-cache generation must be warmed before any game reload.

## Compiled search and clearance-first candidates (in progress)

Installed numba0.68.0 + llvmlite0.50.0 in .venv using uv, requirements-native.txt
records the dependency. source_compiled.py ports XY microticks into compiled
arrays, packed dedup keys, parent indices, X-band beam preservation. Server
precompiles before serving; compilation/startup is distinct from route search.
No local Python physics tests/replays were run: only candidate generation,
performance measurements, and actual game observation.

Initial native min-input Blue API606ms (final beam337ms; smaller failed beam
not originally included). SlideH512 search64.42ms, actual game first5 rounds
92->92 then round6 92->17. Failed trace 054010-936960.json. Prior Python
35.96sec->21.59sec identical-action Blue also later damaged: trace
053811-316002.json. First hit clock120 had actual local y9.534 versus planned
y15.539; dt33.333ms just before jump at clock111 skipped the planned112 frame.
Ten observed clean rounds were evidence, not universal stability.

Latest clearance candidates add 2px white hazard spatial margin and +/-2 plan
frames temporal margin, retain4 fully settled landing frames, and maximise
minimum clearance (capped8px beyond those expanded hazards) before input time.
Source/native beam remains approximate; no global optimality claim. Blue moving
clearance also considers blue hazards, stationary contact remains legal.
API fresh=1 bypasses route lookup and actually generates a new candidate.
Stats now include baking and every failed beam attempt. Measured clearance
Blue: API867ms, bake80.56/search653.68ms, input95. SlideH: API792ms,
bake67.94/search702.88ms, input230. Files *-clearance-route.json and
clearance-performance.json. Fast with hard safety margins returned no candidate
frame111; do not interpret as impossible; do not play deadlock output.

SlideH clearance candidate is currently running in browser cb=slideh-clearance1.
Native hash table optimisation was just written, not yet compiled/accepted.
Current server parent44268; listener child must be verified before restarting.
## Clearance ranking / execution identity update

Native search now maximises the minimum candidate clearance, capped8px,
before held-input cost. Dedup uses a preallocated native hash table. Measured
fresh generation after JIT startup: Blue API673ms (bake80.05, all search
attempts521.11); SlideH API604ms (bake65.88, attempts517.30). Performance artifact
clearance-hash-performance.json. These requests bypassed the route cache.
Startup/JIT compilation remains extra; this does not claim100ms end-to-end.

Observed a route/executor mismatch: URL SlideH, actual SingleAttack='sans_bluebone',
HUD route='sans_bonestab1.csv'. Wave dropdown had only fetched another route.
Fixed dropdown in single mode to navigate actual game attack too. Auto detection
now verifies the real SingleAttack sid9637412728316299, and attack starts
resynchronise the route to that variable. UI says SOLVE ROUTE, not OPTIMAL.
Recorder stores wave per run. The user-facing original tab2 is still theirs.
Separate internal tabs3(SlideH),4(Blue) are for isolated actual-engine acceptance.
As of latest read, clearance-hash SlideH7 clean rounds, Blue3 clean rounds.
Still observing to10. Earlier mixed-wave recording must not be presented as
continuous same-wave acceptance. Neither tests nor Python replay were run.

Compiled backend whitelist restored to Blue/SlideH only. Gap1/Fast retain
source_vertical until their safety-margin candidates are solved and measured.
The current server needs a restart after these latest metadata/whitelist edits;
verify parent34204 and actual listener child before stopping exact processes.
## Final latest state: three-round gate and conservative Blue settling

User explicitly set the current acceptance gate to THREE consecutive no-hit
rounds, not10. Do not keep extending repeat observations after three clean
rounds; record later timing deviations separately and continue other waves.
Only actual-game HP/KR establishes acceptance, never Python tests/replay.

Latest Blue candidate treats blue overlap as forbidden until SIX whole plan
frames of resting after landing (100ms). Four settled frames still gate the
next jump. This protects against residual falling velocity after the model
claims zero speed. Previous clearance candidate hit blue at clock244 with
real dy2.268 px/s after its first floor rollback; source code now retains the
blue forbidden predicate throughout the extra rest period.

Measured new Blue fresh request: API661ms, baking81.63ms, full search attempts
519.33ms (149.76+369.56), total600.95ms, input161. First JIT compilation/startup
is extra. This is sub-second new-route generation, not a route-cache claim;
100ms end-to-end is not achieved. Native whitelist is Blue/SlideH only;
Gap1/Fast keep the previous vertical generator. Returned planning metadata
states the clearance-first objective and all buffers.

Real acceptance at the user's THREE-round gate:
- SlideH compiled clearance/hash: first3 complete runs HP92->92, maxKR0, hits0.
  Saved trace/screenshot bonesgap1-20261004-055014-499162.json/.png.
- Blue compiled clearance/hash +6 rest frames: first3 complete runs HP92->92,
  maxKR0,hits0. Saved trace/screenshot bonesgap1-20261004-055208-203200.json/.png.
Both under tools/real-game. Their trace runs include wave identity. The latter
screenshot is an explicitly labelled summary added after measurement, listing
both accepted sets; it is not a screenshot at the ending tick.

TAS single-mode dropdown now reloads the selected ACTUAL attack, rather than
merely replacing the plan. Auto-detection consults SingleAttack only while
SimulatorMode=2. This fixed observed actual Blue vs planned Stab mismatch.

Current hidden server parent PID34524, port8099; get listener child PID before
stopping/restarting (venv launcher spawns a Python child). Accepted Blue route
is cached. Browser tab4 cb=blue-rest6-three is suspended after recording and
marked for handoff. Tab3 was closed after saving. Original tab2 was already
missing when attempting to mark it; do not reacquire a nonexistent handle.
Next: continue other waves using three-round acceptance, preserve safety
margin before optimising inputs, and extend red/platform/slam/random mechanics
against the real engine. No local tests were run in this round.
