"""Integrate finite-window dead proofs into a demand-driven DFS iterator.

This module deliberately does not import parametric_dag. The iterator supplies
its own exact key function and binding objects. Known facts are indexed within
one search instance; binding ordinals are never shared between searches.
"""
from collections import defaultdict
from types import SimpleNamespace
import time

from .cspace import bake_cspace
from .dead_window import DeadFacts, prove_dead_window


class _IndexedDead(set):
    """A bounded optional memo cache with a per-binding, per-tick fact index."""
    def __init__(self, existing, limit):
        super().__init__(existing)
        self.limit = limit
        self.skipped_additions = 0
        self.by_binding = defaultdict(lambda: defaultdict(set))
        for tick, identity, state in self:
            self.by_binding[identity][tick].add(state)

    def add(self, key):
        if key in self:
            return
        if len(self) >= self.limit:
            self.skipped_additions += 1
            return
        super().add(key)
        tick, identity, state = key
        self.by_binding[identity][tick].add(state)

    def update(self, *others):
        for other in others:
            for key in other:
                self.add(key)

    def clear(self):
        super().clear()
        self.by_binding.clear()

    def discard(self, key):
        if key in self:
            super().discard(key)
            tick, identity, state = key
            self.by_binding[identity][tick].discard(state)

    def remove(self, key):
        if key not in self:
            raise KeyError(key)
        self.discard(key)

    def pop(self):
        key = super().pop()
        tick, identity, state = key
        self.by_binding[identity][tick].discard(state)
        return key


def _key(search, binding, tick, state):
    return search._key(SimpleNamespace(binding=binding, tick=tick, state=state))


def try_known_dead_closure(search):
    """Return True only after proving and removing an ancestor's DFS subtree.

    Unknown leaves the stack, states, action cursors and dead contents intact.
    Only closure-attempt metadata and acceleration caches may change. Ordinary
    bindings consume facts scoped by the iterator's own identity map. With
    history/environment quotients, no old facts are consumed; full forward
    proof still works and memo publication uses the iterator's exact _key.

    Optional iterator attributes:
      closure_proof_max_states: cumulative representative budget (250,000).
      closure_dead_cache_limit: total optional dead-cache entries (500,000).
    The existing closure_window/trigger enable and schedule this mechanism.
    closure_max_states retains its separate per-frontier budget; it is never
    replaced by the cumulative proof-storage limit.
    """
    if (not search.closure_window or not search.closure_max_states or
            search.expansions-max(search._closure_last_progress,search._closure_last_attempt)
            < search.closure_trigger):
        return False
    proof_budget = getattr(search, 'closure_proof_max_states', 250000)
    cache_limit = getattr(search, 'closure_dead_cache_limit', 500000)
    if type(proof_budget) is not int or proof_budget < 0 or type(cache_limit) is not int or cache_limit < 0:
        raise ValueError('closure budgets must be nonnegative integers')
    search._closure_last_attempt = search.expansions
    target = max(0, search.furthest_tick-search.closure_window)
    index = 0
    for i, candidate in enumerate(search.stack):
        if candidate.tick <= target:
            index = i
        else:
            break
    if not search.stack:
        return False
    node = search.stack[index]
    if node.has_solution:
        return False
    binding, wave = node.binding, node.binding.wave
    stop = min(search.furthest_tick+8*search.decision_ticks, len(wave.env_schedule)-2)
    if binding.pending_target is not None:
        stop = min(stop, binding.pending_target['tick']-1)
    stop = node.tick+((stop-node.tick)//search.decision_ticks)*search.decision_ticks
    if stop <= node.tick:
        return False
    ancestor_key = search._key(node)
    attempt = (ancestor_key, stop)
    if attempt in search.closure_attempts:
        return False
    search.closure_attempts.add(attempt)
    first, _, space, _ = search._environment(binding)
    if first:
        # A binding-local baked payload uses relative tick indices. The new
        # proof operator and published dead facts always use full-wave ticks.
        cache = getattr(search, '_known_dead_full_cspace', None)
        if cache is None:
            cache = search._known_dead_full_cspace = {}
        if binding.identity not in cache:
            # Keep at most two full-wave payloads; eviction loses no facts.
            if len(cache) >= 2:
                cache.pop(next(iter(cache)))
            cache[binding.identity] = bake_cspace(wave, cell_size=8.)
        space = cache[binding.identity]
    if not isinstance(search.dead, _IndexedDead):
        search.dead = _IndexedDead(search.dead, cache_limit)
    else:
        search.dead.limit = cache_limit
    ordinary_binding = (not search.environment_state_quotient and search.future_history_key is None
                        and search.bindings.get(binding.identity) == ancestor_key[1])
    controls = tuple(range(search.mask_count))
    facts = None
    if ordinary_binding:
        facts = DeadFacts(binding.identity, search.decision_ticks, controls,
                          search.dead.by_binding.get(ancestor_key[1], {}))
    stats = search.closure_stats
    for name in ('known_dead_hits', 'peak_frontier', 'retained_representatives', 'proof_wall_seconds',
                 'cache_additions_skipped', 'last_start_tick', 'last_stop_tick'):
        stats.setdefault(name, 0)
    stats['attempts'] += 1
    began = time.perf_counter()
    proof = prove_dead_window(wave, node.tick, stop, node.state, binding_identity=binding.identity,
        known_dead=facts, controls=controls, hold=search.decision_ticks,
        max_states=proof_budget, max_frontier_states=search.closure_max_states, cspace=space)
    stats['proof_wall_seconds'] += time.perf_counter()-began
    stats['known_dead_hits'] += proof.known_dead_hits
    stats['expanded_states'] += proof.expanded_states
    stats['peak_frontier'] = max(stats['peak_frontier'], proof.peak_frontier)
    stats['retained_representatives'] += proof.retained_representatives
    stats['last_start_tick'], stats['last_stop_tick'] = node.tick, stop
    if proof.status != 'proven_dead':
        outcome = ('resource_limit' if proof.reason == 'resource_limit' else
                   'complete' if proof.reason == 'unproved_exit' else 'unsupported')
        stats[outcome] += 1
        return False
    old_size = len(search.dead)
    # Remember the ancestor first, but even a full cache cannot invalidate the
    # completed proof authorizing removal of its subtree.
    search.dead.add(ancestor_key)
    for layer in proof.memo_layers:
        if ordinary_binding:
            for packed in layer.keys:
                search.dead.add((layer.tick, ancestor_key[1], bytes(packed)))
        else:
            # These identities can vary by tick/history. Do not infer their
            # equivalence or reconstruct them from a shared integer ordinal.
            for state in layer.states:
                search.dead.add(_key(search, binding, layer.tick, state))
    stats['memoized_states'] += len(search.dead)-old_size
    stats['cache_additions_skipped'] = search.dead.skipped_additions
    stats['exhausted'] += 1
    del search.stack[index:]
    return True
