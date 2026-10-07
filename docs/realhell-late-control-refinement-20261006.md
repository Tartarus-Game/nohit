# Complete late one-tick control refinement

The resident four-tick relation from the fixed tick500 source exhausted at
1512. This is a statement about that source and control domain, not original
Real HELL unsatisfiability. To test whether late control coarsening caused the
failure, each complete retained frontier below was reconstructed from its full
saved witness chains, and then expanded with every legal mask 0 through 15 at
every physical tick. No representative entry was selected in these searches.

| Refinement begins | All entry classes | Peak retained classes | Exhausted tick |
| --- | ---: | ---: | ---: |
| 1504 | 1,537 | 3,393 | 1509 |
| 1500 | 85,251 | 85,251 | 1509 |
| 1496 | 319,089 | 319,089 | 1509 |
| 1492 | 952,601 | 972,846 | 1509 |

All searches completed without hitting the two-million-class resource limit.
Every reconstructed entry witness was replayed from the same tick500 state
with the full discrete operator and every microtick collision checked.
Expansions used bounded parent batches, exact axis transitions where certified,
and exact internal input-latch equivalence; no coordinate rounding was used.

The implication is restricted but useful: **retaining the old four-tick prefix
until tick1492 and only then allowing per-tick input cannot escape this local
failure**. A successful route must depart earlier from this restricted prefix
family, use a different tick500 source, or require a correction to the model.
This experiment does not eliminate any of those possibilities. In particular,
it does not prove the complete one-tick problem from the original start empty.

Evidence directories are `scratch/realhell-{tick}-refine-one-tick/` for the four
listed ticks. Each contains `initial.npz` with all exact states and saved prefix
words, complete layer parents and masks, and `result.json`. The driver is
`scratch/refine_joint_1504.py --start <tick>`. Later input refinement was stopped
here to prioritize newly found earlier source states.

An independent target-oriented relational-composition prototype also tested
all 1,145,772 frozen 640 exits. It reduced candidate input edges from about
8.6 million to 1.21 million but measured 0.312 seconds versus the existing
idempotent push kernel's 0.308 seconds. It is therefore not integrated as a
performance improvement. `scratch/joint-pull-benchmark.json` records exact
endpoint equality and full microtick validation of every pull witness.
