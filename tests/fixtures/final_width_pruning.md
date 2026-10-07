This lossless fixture captures the real width-1000 retained layers at source
ticks 7600 through 7642 of the native campaign's Final request. Local tick 0
means source tick 7600; no player state or environment value was modified.
The source request, CSV, full original ancestry and independent 7680-frame
reference replay are recorded under
`scratch/campaign-csv-native-20261007/final-frontier-audit/`.

At local tick 1, the safe edge from row 103 with mask 10 survives exact dedup
but is discarded by width selection. All retained states fail at local tick
43, although the discarded continuation safely clears Slammed at local tick
34. The fixture contains the actual states, masks and parents at every retained
local layer, and original world arrays through local tick 80.

This proves a local search-retention failure. Holding mask 10 indefinitely is
not a complete solution: the same continuation is damaged by a later slam at
source tick 7790. No test treats this captured local fixture as a fabricated
frame-zero request or as native-game acceptance.
