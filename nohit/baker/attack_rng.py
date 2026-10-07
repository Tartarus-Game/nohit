"""Seeded attack-instruction stream, shared with attack_seed.js."""
class AttackRandom:
    def __init__(self, seed):
        self.state = (int(seed) & 0xffffffff) or 0x6d2b79f5

    def random(self):
        x = self.state
        x ^= (x << 13) & 0xffffffff
        x ^= x >> 17
        x ^= (x << 5) & 0xffffffff
        self.state = x & 0xffffffff
        return self.state / 4294967296.0

    def randint(self, a, b):
        return a + int(self.random() * (b - a + 1))
